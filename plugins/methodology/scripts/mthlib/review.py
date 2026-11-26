"""Review records: proof that every configured reviewer approved the final HEAD.

Records live in ``.git/mth/reviews.json`` (local, never committed) and are
keyed by commit SHA, so any new commit invalidates previous approvals. The
summary of each review is copied into the PR body for traceability.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from contextlib import contextmanager
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


class ReviewError(MthError):
    """A failure of the recording itself, tagged with the stage that failed for the trace.

    ``archived`` is the path of a report already copied when the failure came later (orphan file).
    """

    def __init__(self, stage: str, message: str, hint: str | None = None, archived: Path | None = None) -> None:
        super().__init__(message, hint)
        self.stage = stage
        self.archived = archived


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
    """Count the findings of a reviewer report and check the figure the reviewer declared.

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
    for number, line in enumerate(lines[starts[0] + 1:], start=1):
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
            raise ReportError(f"línea {number} de HALLAZGOS no admitida (ni hallazgo numerado ni «ninguno»)")
    marks = len(re.findall(r"\[bloqueante\]", text, re.IGNORECASE))
    if marks != counts["bloqueante"]:
        raise ReportError(f"hay {marks} marcas [bloqueante] y solo {counts['bloqueante']} son líneas de "
                          "hallazgo de HALLAZGOS (sangradas, fuera de la sección o en otro texto)")
    if said_none and any(counts.values()):
        raise ReportError("HALLAZGOS dice 'ninguno' y lista hallazgos")
    if declared != counts["bloqueante"]:
        raise ReportError(f"el revisor declara {declared} bloqueantes y mth cuenta {counts['bloqueante']}")
    return Parsed(counts["bloqueante"], declared, counts)


def read_report(path: Path) -> bytes:
    """Bytes of the report, or a ``ReportError`` if it cannot be used."""
    try:
        # O_NONBLOCK: opening a FIFO must not wait for a writer; the type is checked on the open descriptor.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                raise ReportError("no es un fichero regular")
            data = fh.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        raise ReportError(f"no se puede leer el informe ({exc.strerror or exc})") from exc
    if len(data) > MAX_REPORT_BYTES:
        raise ReportError(f"el informe supera {MAX_REPORT_BYTES} bytes")
    if not data.strip():
        raise ReportError("el informe está vacío")
    return data


def require_inside(root: Path, path: Path, what: str) -> None:
    """Refuse a path that resolves outside the repository (symbolic links, ``..``, absolute paths)."""
    try:
        inside = path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError) as exc:  # a symbolic-link loop
        raise ReviewError("rejected", f"No se puede resolver {path}: {exc}.",
                          hint="Usa una ruta real dentro del repo; no se ha registrado nada.") from exc
    if not inside:
        raise ReviewError("rejected", f"{path} queda fuera de {root}: {what}.",
                          hint="Los informes van en .work/tmp/ (o .work/reviews/); no se ha registrado nada.")


_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def archive(root: Path, directory: Path, sha: str, agent: str, first: int, data: bytes) -> tuple[Path, int]:
    """Write the verbatim report to ``<sha>-<agent>-<n>.md`` and never overwrite one.

    Returns:
        The path and the attempt number actually used (>= ``first``).

    Raises:
        MthError: The name is unsafe, the directory resolves outside ``root`` (a symbolic link in
            a repository one does not trust), or it cannot be written; nothing is recorded.
    """
    if not (_SAFE.fullmatch(sha) and _SAFE.fullmatch(agent)) or ".." in agent:
        raise ReviewError("rejected", f"Nombre no válido para archivar el informe ({agent}, {sha[:12]}).",
                          hint="El agente y el commit solo pueden llevar letras, dígitos, '.', '_' y '-'.")
    require_inside(root, directory, "no se archiva el informe")
    n = first
    try:
        directory.mkdir(parents=True, exist_ok=True)
        while True:
            target = directory / f"{sha}-{agent}-{n}.md"
            try:
                fh = open(target, "xb")
            except FileExistsError:
                n += 1
                continue
            try:
                with fh:
                    fh.write(data)
            except OSError:
                target.unlink(missing_ok=True)  # a truncated file must not pass as the literal report
                raise
            return target, n
    except OSError as exc:
        raise ReviewError("archive", f"No se pudo archivar el informe de {agent} en {directory}: {exc}.",
                          hint="Comprueba permisos y espacio y repite el registro: no se ha registrado nada.") from exc


LOCK_TIMEOUT = 30.0  # seconds a record waits for another one before giving up


@contextmanager
def _locked(git_dir: Path, timeout: float | None = None):
    """Exclusive lock around the read-modify-write of ``reviews.json`` (parallel ``record`` calls).

    Raises:
        ReviewError: The lock file cannot be opened or another record holds it past ``timeout``.
    """
    try:
        import fcntl
    except ImportError:  # no flock (Windows): records are sequential there (SPEC-0013)
        yield
        return
    lock = _store(git_dir).with_name("reviews.lock")
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock, "a")
    except OSError as exc:
        raise ReviewError("lock", f"No se pudo abrir el bloqueo {lock}: {exc}.",
                          hint="Comprueba permisos y espacio; no se ha registrado nada.") from exc
    with fh:
        deadline = time.monotonic() + (LOCK_TIMEOUT if timeout is None else timeout)
        delay = 0.01
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:  # held by another record; any other OSError is a real failure
                if time.monotonic() >= deadline:
                    raise ReviewError("lock", "Otro `mth review record` tiene el registro bloqueado.",
                                      hint="Espera a que termine y repite; no se ha registrado nada.") from None
                time.sleep(delay)
                delay = min(delay * 2, 0.5)
            except OSError as exc:
                raise ReviewError("lock", f"No se pudo tomar el bloqueo {lock}: {exc}.",
                                  hint="El sistema de ficheros no admite flock; no se ha registrado nada.") from exc
        yield


MAX_SUMMARY = 4096


def record_report(git_dir: Path, root: Path, reviews_dir: Path, branch: str, sha: str, agent: str,
                  report: Path, summary: str) -> dict:
    """Record a review computed from the report; failures are recorded as ``failed``.

    Returns:
        The stored entry. ``status`` is ``ok`` or ``failed``.

    Raises:
        MthError: The report cannot be archived (nothing is recorded).
    """
    if len(summary.encode("utf-8")) > MAX_SUMMARY:
        raise ReviewError("rejected", f"El resumen supera {MAX_SUMMARY} bytes.",
                          hint="Resume en una línea; el informe completo se archiva aparte.")
    require_inside(root / ".work", report, "el informe no se lee")  # not any file of the repository
    with _locked(git_dir):
        try:
            previous = results(git_dir, branch, sha).get(agent, {})
            if not isinstance(previous, dict):
                raise TypeError("la entrada no es un objeto")
            counters = (int(previous.get("attempts", 0)), int(previous.get("failures", 0)))
        except MthError as exc:
            raise ReviewError("store", exc.message, exc.hint) from exc
        except (TypeError, ValueError, AttributeError) as exc:
            raise ReviewError("store", f"{_store(git_dir)} tiene una entrada inesperada para {agent}: {exc}.",
                              hint="Bórralo y repite las revisiones; no se ha registrado nada.") from exc
        attempt = counters[0] + 1
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
                path, attempt = archive(root, reviews_dir, sha, agent, attempt, data)
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
        # Consecutive failures drive the "stop" advice; an approved record in between resets them.
        entry["failures"] = counters[1] + 1 if entry["status"] == "failed" else 0
        if previous:  # the overwritten entry stays visible in the trace and in the record
            entry["previous_status"] = previous.get("status", "ok")
        try:
            record(git_dir, branch, sha, agent, entry)
        except MthError as exc:
            raise ReviewError("store", exc.message, exc.hint, archived=Path(entry["report"]) if "report" in entry else None) from exc
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
                       hint="Pide una corrección al mismo agente con SendMessage y registra de nuevo.")
    blocking = [a for a in agents if found[a]["blocking"] > 0]
    if blocking:
        raise MthError(f"Hay hallazgos bloqueantes sin resolver: {', '.join(blocking)}.",
                       hint="Corrige, haz commit y vuelve a revisar.")
    return {a: found[a] for a in agents}
