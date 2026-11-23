"""Read-only SQLite queries for the ``lector-estado`` agent: ``mth db-query`` (SPEC-0012, ADR-0008).

Three independent layers keep the database untouched, whatever the agent's guard allows:

1. The file is opened with the URI ``mode=ro``: SQLite rejects any write to it.
2. ``PRAGMA query_only = ON`` rejects writes even to temporary tables.
3. An authorizer admits only reads (SELECT, READ, functions except ``load_extension`` and the
   file functions, recursive CTEs, a few schema PRAGMAs); ATTACH, DETACH and every write are denied before
   they run.

On top: one statement per call, a row limit and a time limit (PRINCIPLES §2). Aliases come
from ``[agents.lector-estado].databases``: the agent never passes paths. A WAL database needs
its directory to allow creating or reading the ``-shm`` file even with ``mode=ro``.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import MthError

AGENT = "lector-estado"
SCHEMA_SQL = "SELECT name, sql FROM sqlite_schema WHERE type IN ('table', 'view') ORDER BY name"
_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_PRAGMA,
            sqlite3.SQLITE_RECURSIVE}  # WITH RECURSIVE only reads
_PRAGMAS = {"table_info", "table_list", "index_list", "index_info", "foreign_key_list"}
_FORBIDDEN_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
MAX_VALUE_BYTES = 1_000_000  # SQLITE_LIMIT_LENGTH: no string or blob grows beyond this
MAX_CELL_CHARS = 2_000       # each cell is cut in the output


class QueryError(MthError):
    """The query was rejected, failed or timed out; the database was not modified."""


@dataclass(frozen=True)
class Result:
    """Columns and at most ``max_rows`` rows; ``truncated`` when more rows existed."""

    columns: list[str]
    rows: list[tuple]
    truncated: bool


def _authorizer(action: int, arg1, arg2, _db, _trigger) -> int:
    if action not in _ALLOWED:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() not in _PRAGMAS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _FORBIDDEN_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def query(databases: dict[str, str], root: Path, alias: str, sql: str | None, *,
          max_rows: int, timeout_s: float) -> Result:
    """Run one read-only statement (the schema listing when ``sql`` is None).

    Args:
        databases: Alias → path, relative to ``root`` unless absolute.
        root: Repository root.
        alias: Declared alias of the database to query.
        sql: A single SQL statement, or None for the schema.
        max_rows: Maximum rows returned.
        timeout_s: The statement is interrupted after this many seconds.

    Raises:
        QueryError: Unknown alias, missing file, rejected or invalid statement, timeout.
    """
    if max_rows <= 0 or timeout_s <= 0:
        raise QueryError(f"Límites inválidos en [agents.{AGENT}]: max_rows y timeout_s deben ser positivos.")
    if alias not in databases:
        raise QueryError(f"Alias desconocido: '{alias}'. Disponibles: {', '.join(sorted(databases)) or 'ninguno'}.",
                         hint=f"Los alias se declaran en [agents.{AGENT}].databases.")
    path = (root / databases[alias]).resolve()
    if not path.is_relative_to(root.resolve()):  # the repo config is not trusted to point elsewhere
        raise QueryError(f"La base de '{alias}' está fuera del repositorio: {databases[alias]}.",
                         hint="mth db-query solo abre bases dentro del repositorio.")
    if not path.is_file():
        raise QueryError(f"No existe la base de '{alias}': {path}.")
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=timeout_s)
    try:
        con.execute("PRAGMA query_only = ON")
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
        con.set_authorizer(_authorizer)
        deadline = time.monotonic() + timeout_s
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cursor = con.execute(sql if sql is not None else SCHEMA_SQL)  # one statement per call
            rows = cursor.fetchmany(max_rows + 1)
        except (sqlite3.Error, sqlite3.Warning) as exc:
            if time.monotonic() > deadline:
                raise QueryError(f"La consulta superó el límite de {timeout_s} s y se ha cortado.") from exc
            raise QueryError(f"Consulta rechazada o inválida: {exc}.",
                             hint="mth db-query solo admite una sentencia de lectura por llamada.") from exc
        columns = [d[0] for d in (cursor.description or [])]
        return Result(columns, rows[:max_rows], len(rows) > max_rows)
    finally:
        con.close()


def _cell(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    text = str(value)
    if len(text) > MAX_CELL_CHARS:
        text = f"{text[:MAX_CELL_CHARS]}… <{len(text) - MAX_CELL_CHARS} caracteres más>"
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def format_result(result: Result, max_rows: int) -> str:
    """Tab-separated output for the agent, with an explicit truncation notice."""
    lines = ["\t".join(result.columns)] + ["\t".join(_cell(v) for v in row) for row in result.rows]
    if result.truncated:
        lines.append(f"… resultado truncado a {max_rows} filas: agrega o filtra la consulta.")
    return "\n".join(lines)


def run(cfg_agents: dict, defaults: dict, root: Path, alias: str, sql: str | None) -> str:
    """``mth db-query``: query with the limits of ``[agents.lector-estado]`` and format the result.

    Raises:
        QueryError: See :func:`query`.
    """
    settings = {**defaults, **cfg_agents.get(AGENT, {})}
    max_rows, timeout_s = settings["max_rows"], settings["timeout_s"]
    result = query(settings["databases"], root, alias, sql, max_rows=max_rows, timeout_s=timeout_s)
    return format_result(result, max_rows)
