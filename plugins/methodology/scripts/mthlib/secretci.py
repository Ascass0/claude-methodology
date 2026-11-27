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
SAFE_BASELINE = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/-]*")  # the value comes from the repo and ends inside a CI script


def check_baseline(baseline: str) -> None:
    """Fail unless ``baseline`` is safe to put inside the workflow script.

    Raises:
        MthError: ``baseline`` has characters that could change the script around it.
    """
    if not SAFE_BASELINE.fullmatch(baseline) or ".." in baseline.split("/"):
        raise MthError(f"'secrets.baseline' = {baseline!r} tiene caracteres que no se admiten en el workflow.",
                       hint="Usa solo letras, cifras, '.', '_', '-' y '/', sin empezar por '-' ni usar '..'.")


def render(baseline: str) -> str:
    """The workflow text for ``baseline``.

    Raises:
        MthError: ``baseline`` is unsafe (see :func:`check_baseline`).
    """
    check_baseline(baseline)
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, baseline)


def state(root: Path, baseline: str) -> str:
    """``current``, ``stale`` (ours, outdated), ``foreign`` (no mark), ``absent`` or ``invalid`` (unreadable or unsafe baseline)."""
    path = root / WORKFLOW
    if not path.is_file():
        return "absent"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        wanted = render(baseline)
    except (OSError, MthError):
        return "invalid"  # unreadable file or unsafe baseline: report it, never stop the diagnosis
    if not text.startswith(MARK):
        return "foreign"
    return "current" if text == wanted else "stale"


def install(root: Path, baseline: str) -> str:
    """Write the workflow unless the file is foreign. Returns the previous state (``foreign`` and ``invalid`` = left alone).

    Raises:
        MthError: ``baseline`` is unsafe (nothing is written).
    """
    previous = state(root, baseline)
    if previous in ("absent", "stale"):
        atomic_write(root / WORKFLOW, render(baseline))
    return previous
