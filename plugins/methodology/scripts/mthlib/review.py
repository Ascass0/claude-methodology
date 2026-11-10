"""Review records: proof that every configured reviewer approved the final HEAD.

Records live in ``.git/mth/reviews.json`` (local, never committed) and are
keyed by commit SHA, so any new commit invalidates previous approvals. The
summary of each review is copied into the PR body for traceability.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .errors import MthError


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
