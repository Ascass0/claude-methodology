"""Secrets workflow for GitHub Actions (ADR-0022, SPEC-0024): render it from the plugin template and keep it current.

The file is deterministic, so ``mth`` writes it; it carries a mark on its first line and a file without
the mark is the person's own and is never overwritten.
"""
from __future__ import annotations

import re
from pathlib import Path

from .errors import MthError
from .files import atomic_write

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "workflows" / "secrets.yml"
WORKFLOW = Path(".github") / "workflows" / "secrets.yml"
MARK = "# claude-methodology:secrets-workflow"
PLACEHOLDER = "@BASELINE@"
SAFE_BASELINE = re.compile(r"[A-Za-z0-9._/-]+")  # the value comes from the repo and ends inside a CI script


def render(baseline: str) -> str:
    """The workflow text for ``baseline``.

    Raises:
        MthError: ``baseline`` has characters that could change the script around it.
    """
    if not SAFE_BASELINE.fullmatch(baseline):
        raise MthError(f"'secrets.baseline' = {baseline!r} tiene caracteres que no se admiten en el workflow.",
                       hint="Usa solo letras, cifras, '.', '_', '-' y '/'.")
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, baseline)


def state(root: Path, baseline: str) -> str:
    """``current``, ``stale`` (ours, outdated), ``foreign`` (no mark) or ``absent``."""
    path = root / WORKFLOW
    if not path.is_file():
        return "absent"
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith(MARK):
        return "foreign"
    return "current" if text == render(baseline) else "stale"


def install(root: Path, baseline: str) -> str:
    """Write the workflow unless the file is foreign. Returns the previous state (``foreign`` = left alone).

    Raises:
        MthError: ``baseline`` is unsafe (nothing is written).
    """
    previous = state(root, baseline)
    if previous in ("absent", "stale"):
        atomic_write(root / WORKFLOW, render(baseline))
    return previous
