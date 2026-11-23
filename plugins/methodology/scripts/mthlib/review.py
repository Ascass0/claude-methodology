"""Review records: proof that every configured reviewer approved the final HEAD.

Records live in ``.git/mth/reviews.json`` (local, never committed) and are
keyed by commit SHA, so any new commit invalidates previous approvals. The
summary of each review is copied into the PR body for traceability.
"""
from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import globs
from .errors import MthError
from .files import atomic_write

MAX_REPORT_BYTES = 256 * 1024
_BLOCKING_LINE = re.compile(r"^BLOQUEANTES:\s*(\d+)$")


def _matches(path: str, patterns: list[str]) -> bool:
    """Gitignore-like evaluation: the last matching pattern wins; '!' negates."""
    matched = False
    for pattern in patterns:
        negate = pattern.startswith("!")
        if globs.match(path, pattern[1:] if negate else pattern):
            matched = not negate
    return matched


def required(agents: list[str], paths: dict[str, list[str]], changed: list[str]) -> list[str]:
    """Agents that must review a change, in precedence order.

    Agents without ``paths`` always review; the rest only when a changed file matches.
    """
    return [a for a in agents if a not in paths or any(_matches(f, paths[a]) for f in changed)]


def _store(git_dir: Path) -> Path:
    return git_dir / "mth" / "reviews.json"


def _load(git_dir: Path) -> dict:
    path = _store(git_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MthError(f"{path} está corrupto.", hint="Bórralo y repite las revisiones.") from exc


class ReportError(Exception):
    """A report ``mth`` cannot trust: unreadable, malformed or inconsistent."""


_HEADERS = re.compile(r"^(FUERA DE ALCANCE|RESUMEN:|BLOQUEANTES:|TESTS:|CRITERIOS|ALCANCE:)")
_FINDING = re.compile(r"^\d+\.\s*\[(bloqueante|importante|sugerencia)\]", re.IGNORECASE)
_NONE = re.compile(r"^ninguno\.?$", re.IGNORECASE)
SEVERITIES = ("bloqueante", "importante", "sugerencia")


@dataclass(frozen=True)
class Parsed:
    blocking: int
    declared: int
    findings: dict[str, int]


def parse_report(text: str) -> Parsed:
    """Count the findings of a reviewer report and check the figure the reviewer declared (SPEC-0013).

    Raises:
        ReportError: No single HALLAZGOS section, a line that is not a finding, 'ninguno'
            next to findings, no final ``BLOQUEANTES: <n>`` line, or a declared figure
            different from the count.
    """
    lines = text.splitlines()
    non_empty = [line.strip() for line in lines if line.strip()]
    m = _BLOCKING_LINE.match(non_empty[-1]) if non_empty else None
    if m is None:
        raise ReportError("no termina en 'BLOQUEANTES: <n>'")
    declared = int(m.group(1))
    starts = [i for i, line in enumerate(lines) if line.strip() == "HALLAZGOS"]
    if len(starts) != 1:
        raise ReportError("debe tener exactamente una sección HALLAZGOS" if starts
                          else "no tiene sección HALLAZGOS")
    counts = dict.fromkeys(SEVERITIES, 0)
    said_none = False
    for line in lines[starts[0] + 1:]:
        stripped = line.strip()
        if not stripped or line[0] in " \t":
            continue
        if _HEADERS.match(stripped):
            break
        found = _FINDING.match(stripped)
        if found:
            counts[found.group(1).lower()] += 1
        elif _NONE.match(stripped):
            said_none = True
        else:
            raise ReportError(f"línea no admitida en HALLAZGOS: «{stripped[:60]}»")
    if said_none and any(counts.values()):
        raise ReportError("HALLAZGOS dice 'ninguno' y lista hallazgos")
    if declared != counts["bloqueante"]:
        raise ReportError(f"el revisor declara {declared} bloqueantes y mth cuenta {counts['bloqueante']}")
    return Parsed(counts["bloqueante"], declared, counts)


def read_report(path: Path) -> bytes:
    """Bytes of the report, or a ``ReportError`` if it cannot be used."""
    try:
        size = path.stat().st_size
        if size > MAX_REPORT_BYTES:
            raise ReportError(f"el informe ocupa {size} bytes (máximo {MAX_REPORT_BYTES})")
        data = path.read_bytes()
    except OSError as exc:
        raise ReportError(f"no se puede leer el informe ({exc.strerror or exc})") from exc
    if not data.strip():
        raise ReportError("el informe está vacío")
    return data


def archive(directory: Path, sha: str, agent: str, first: int, data: bytes) -> tuple[Path, int]:
    """Write the verbatim report to ``<sha>-<agent>-<n>.md`` and never overwrite one.

    Returns:
        The path and the attempt number actually used (>= ``first``).

    Raises:
        MthError: The directory or file cannot be written; nothing is recorded.
    """
    n = first
    try:
        directory.mkdir(parents=True, exist_ok=True)
        while True:
            target = directory / f"{sha}-{agent}-{n}.md"
            try:
                with open(target, "xb") as fh:
                    fh.write(data)
                return target, n
            except FileExistsError:
                n += 1
    except OSError as exc:
        raise MthError(f"No se pudo archivar el informe de {agent} en {directory}: {exc}.",
                       hint="Comprueba permisos y espacio y repite el registro: no se ha registrado nada.") from exc


def record_report(git_dir: Path, reviews_dir: Path, branch: str, sha: str, agent: str,
                  report: Path, summary: str) -> dict:
    """Record a review computed from the report; failures are recorded as ``failed`` (SPEC-0013).

    Returns:
        The stored entry. ``status`` is ``ok`` or ``failed``.

    Raises:
        MthError: The report cannot be archived (nothing is recorded).
    """
    previous = results(git_dir, branch, sha).get(agent, {})
    attempt = int(previous.get("attempts", 0)) + 1
    entry: dict = {"summary": summary.strip()}
    try:
        data = read_report(report)
    except ReportError as exc:
        data, entry["reason"] = None, str(exc)
    if data is not None:
        # An archive already at that path (--report points at it) is kept as is.
        same = report.resolve() == (reviews_dir / f"{sha}-{agent}-{attempt}.md").resolve()
        if same:
            path = report
        else:
            path, attempt = archive(reviews_dir, sha, agent, attempt, data)
        entry["report"] = str(path)
        entry["report_sha256"] = hashlib.sha256(data).hexdigest()
        try:
            parsed = parse_report(data.decode("utf-8"))
            entry.update(blocking=parsed.blocking, declared=parsed.declared, findings=parsed.findings)
        except UnicodeDecodeError:
            entry["reason"] = "el informe no es UTF-8"
        except ReportError as exc:
            entry["reason"] = str(exc)
    entry["status"] = "failed" if "reason" in entry else "ok"
    entry["attempts"] = attempt
    record(git_dir, branch, sha, agent, entry)
    return entry


def record(git_dir: Path, branch: str, sha: str, agent: str, entry: dict) -> None:
    data = _load(git_dir)
    entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data.setdefault(branch, {}).setdefault(sha, {})[agent] = entry
    atomic_write(_store(git_dir), json.dumps(data, ensure_ascii=False, indent=2))


def results(git_dir: Path, branch: str, sha: str) -> dict[str, dict]:
    return _load(git_dir).get(branch, {}).get(sha, {})


def describe(entry: dict | None) -> tuple[bool, str]:
    """Approved flag and status text of a review record, for ``mth review status``."""
    if not entry:
        return False, "pendiente"
    if entry.get("status", "ok") == "failed":
        return False, f"fallida (intento {entry.get('attempts', 1)}): {entry.get('reason', '?')}"
    return not entry["blocking"], f"{entry['blocking']} bloqueantes"


def check(git_dir: Path, branch: str, sha: str, agents: list[str]) -> dict[str, dict]:
    """Return the records when every agent approved ``sha``.

    Raises:
        MthError: No reviewers configured, missing reviews or blocking findings.
    """
    if not agents:
        raise MthError("La revisión es obligatoria pero review.agents está vacío.",
                       hint="Declara los agentes revisores del repo en .claude/methodology.toml.")
    found = results(git_dir, branch, sha)
    missing = [a for a in agents if a not in found]
    if missing:
        raise MthError(f"Faltan revisiones del HEAD actual ({sha[:8]}): {', '.join(missing)}.",
                       hint="Ejecuta la skill mth-review. Un commit nuevo invalida las revisiones previas.")
    failed = [a for a in agents if found[a].get("status", "ok") == "failed"]
    if failed:
        detail = "; ".join(f"{a}: {found[a].get('reason', '?')} (intento {found[a].get('attempts', 1)})" for a in failed)
        raise MthError(f"Revisión fallida, no aprobada: {detail}.",
                       hint="Pide una corrección al mismo agente con SendMessage y registra de nuevo (SPEC-0013).")
    blocking = [a for a in agents if found[a]["blocking"] > 0]
    if blocking:
        raise MthError(f"Hay hallazgos bloqueantes sin resolver: {', '.join(blocking)}.",
                       hint="Corrige, haz commit y vuelve a revisar.")
    return {a: found[a] for a in agents}
