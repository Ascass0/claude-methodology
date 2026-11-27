"""Commit message format: Conventional Commits + body + ``Refs:`` trailer.

Example::

    feat(runner): create and destroy one container per task

    Each delegated task gets its own sandbox; teardown runs on success,
    error, timeout and cancellation.

    Refs: F-001, ADR-NNNN
"""
from __future__ import annotations

import re

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .ids import IdRegistry

TYPES = ("feat", "fix", "refactor", "perf", "docs", "test", "build", "ci", "chore", "revert")
MAX_HEADER = 72
NO_REFS = "n/a"
_HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9][a-z0-9._/-]*)\))?"
                     r"(?P<bang>!)?: (?P<summary>\S.*)$")
_TRAILER = re.compile(r"^(?P<key>BREAKING CHANGE|[A-Za-z][A-Za-z-]*): (?P<value>\S.*)$")
_ISSUE = re.compile(r"^(?:[\w.-]+/[\w.-]+)?#\d+$")
_REWRITE = ("fixup!", "squash!", "amend!")


def validate_header(header: str) -> list[str]:
    """Errors in a Conventional Commits header (also used for PR titles)."""
    errors = []
    m = _HEADER.match(header)
    if not m:
        return [f"cabecera inválida: '{header}'. Formato: tipo(ámbito)!: resumen"]
    if m.group("type") not in TYPES:
        errors.append(f"tipo '{m.group('type')}' no permitido. Tipos: {', '.join(TYPES)}")
    if len(header) > MAX_HEADER:
        errors.append(f"cabecera de {len(header)} caracteres (máximo {MAX_HEADER})")
    if header.endswith("."):
        errors.append("la cabecera no termina en punto")
    return errors


def _split(message: str) -> list[str]:
    lines = [ln.rstrip() for ln in message.splitlines() if not ln.startswith("#")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _paragraphs(lines: list[str]) -> list[list[str]]:
    paras, current = [], []
    for ln in lines:
        if ln:
            current.append(ln)
        elif current:
            paras.append(current)
            current = []
    if current:
        paras.append(current)
    return paras


def parse_trailers(message: str) -> dict[str, list[str]]:
    """Trailers of the last paragraph, when every line in it is a trailer."""
    paras = _paragraphs(_split(message)[2:])
    if paras and all(_TRAILER.match(ln) for ln in paras[-1]):
        out: dict[str, list[str]] = {}
        for ln in paras[-1]:
            m = _TRAILER.match(ln)
            out.setdefault(m.group("key"), []).append(m.group("value"))
        return out
    return {}


def refs_of(message: str) -> list[str]:
    """Identifiers listed in the ``Refs:`` trailer(s), excluding ``n/a``."""
    values = parse_trailers(message).get("Refs", [])
    tokens = [t.strip() for v in values for t in v.split(",")]
    return [t for t in tokens if t and t.lower() != NO_REFS]


def validate(message: str, cfg: Config, registry: IdRegistry) -> list[str]:
    """All format errors in ``message`` (empty list = valid)."""
    lines = _split(message)
    if not lines:
        return ["mensaje vacío"]
    header = lines[0]
    if header.startswith("Merge "):
        return []
    if header.startswith(_REWRITE):
        return ["los commits fixup!/squash!/amend! implican reescribir historia: no se permiten"]
    errors = validate_header(header)
    m = _HEADER.match(header)
    if len(lines) > 1 and lines[1]:
        errors.append("la segunda línea debe estar vacía")
    paras = _paragraphs(lines[2:] if len(lines) > 1 and not lines[1] else lines[1:])
    trailers = parse_trailers(message)
    body = paras[:-1] if trailers else paras
    ctype = m.group("type") if m else None
    if ctype != "revert" and not body:
        errors.append("falta el cuerpo: explica qué cambia y por qué")

    raw_refs = [t.strip() for v in trailers.get("Refs", []) for t in v.split(",") if t.strip()]
    required = ctype in cfg["commits"]["require_refs"]
    if not raw_refs:
        if ctype and ctype != "revert":
            errors.append("falta el trailer 'Refs:'" + ("" if required else f" (usa 'Refs: {NO_REFS}' si no aplica)"))
    elif [r.lower() for r in raw_refs] == [NO_REFS]:
        if required:
            errors.append(f"los commits '{ctype}' deben referenciar al menos una spec, ADR o issue")
    else:
        for token in raw_refs:
            if _ISSUE.match(token):
                continue
            if token.lower() == NO_REFS:
                errors.append(f"'{NO_REFS}' no se combina con otras referencias")
            elif registry.kind_of(token) is None:
                errors.append(f"referencia con formato desconocido: '{token}'")
            elif not registry.is_defined(token):
                errors.append(f"referencia a {token}, que no está definido en el repositorio")
    if m and m.group("bang") and "BREAKING CHANGE" not in trailers:
        errors.append("una cabecera con '!' exige el trailer 'BREAKING CHANGE: <descripción>'")
    return errors


def build(ctype: str, scope: str | None, summary: str, body: str,
          refs: list[str], breaking: str | None = None) -> str:
    """Compose a message in the canonical format."""
    header = f"{ctype}({scope})" if scope else ctype
    header += ("!" if breaking else "") + f": {summary.strip()}"
    trailers = [f"Refs: {', '.join(refs) if refs else NO_REFS}"]
    if breaking:
        trailers.append(f"BREAKING CHANGE: {breaking.strip()}")
    return f"{header}\n\n{body.strip()}\n\n" + "\n".join(trailers) + "\n"
