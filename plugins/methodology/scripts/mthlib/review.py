"""Review records: proof that every configured reviewer approved the final HEAD.

Records live in ``.git/mth/reviews.json`` (local, never committed) and are
keyed by commit SHA, so any new commit invalidates previous approvals. The
summary of each review is copied into the PR body for traceability.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import globs
from .errors import MthError

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


def blocking_from_report(path: Path, agent: str) -> int:
    """Number of blocking findings stated on the last line of a reviewer report (SPEC-0001).

    A reviewer that crashed, timed out or stopped early leaves no such line, so
    its review must stay pending instead of being recorded as approved.

    Raises:
        MthError: Missing, unreadable, oversized or empty report, or no final
            ``BLOQUEANTES: <n>`` line.
    """
    hint = "Relanza el revisor una vez con contexto limpio; si vuelve a fallar, detente (PRINCIPLES §11)."
    try:
        size = path.stat().st_size
        if size > MAX_REPORT_BYTES:
            raise MthError(f"El informe de {agent} ocupa {size} bytes (máximo {MAX_REPORT_BYTES}): "
                           "revisor no ejecutado, no se registra nada.", hint=hint)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MthError(f"No se puede leer el informe de {agent} ({path}): revisor no ejecutado, "
                       "no se registra nada.", hint=hint) from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    m = _BLOCKING_LINE.match(lines[-1]) if lines else None
    if m is None:
        raise MthError(f"El informe de {agent} no termina en 'BLOQUEANTES: <n>': revisor no ejecutado, "
                       "no se registra nada.", hint=hint)
    return int(m.group(1))


def record(git_dir: Path, branch: str, sha: str, agent: str, blocking: int, summary: str) -> None:
    data = _load(git_dir)
    data.setdefault(branch, {}).setdefault(sha, {})[agent] = {
        "blocking": blocking, "summary": summary.strip(),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = _store(git_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def results(git_dir: Path, branch: str, sha: str) -> dict[str, dict]:
    return _load(git_dir).get(branch, {}).get(sha, {})


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
    blocking = [a for a in agents if found[a]["blocking"] > 0]
    if blocking:
        raise MthError(f"Hay hallazgos bloqueantes sin resolver: {', '.join(blocking)}.",
                       hint="Corrige, haz commit y vuelve a revisar.")
    return {a: found[a] for a in agents}
