"""SessionStart hook: inject the core rules and the repository state into context."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import branches
from .config import load
from .errors import MthError
from .git import Git
from .setup import install_hook

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
MTH = PLUGIN_ROOT / "scripts" / "mth.py"


def _state(cwd: Path) -> list[str]:
    try:
        git = Git.discover(cwd)
    except MthError:
        return ["Estado: fuera de un repositorio git."]
    try:
        cfg = load(git.root)
    except MthError as exc:
        return [f"Estado: {exc.message} → {exc.hint or ''}".strip()]
    lines = []
    hook = install_hook(git)
    if hook == "foreign":
        lines.append("⚠ Hay un hook commit-msg ajeno: la validación de mensajes no está activa (mth doctor).")
    try:
        branch = git.current_branch()
        info = branches.parse(branch, cfg)
        if info is None:
            lines.append(f"Rama actual: {branch} (rama protegida: crea una rama de trabajo antes de cambiar nada).")
        else:
            lines.append(f"Rama actual: {branch} → se integra en {branches.target_of(info, cfg)}.")
    except MthError as exc:
        lines.append(f"Rama actual: {exc.message}")
    changes = git.root / cfg["paths"]["changes"]
    pending = len(list(changes.glob("*.md"))) if changes.is_dir() else 0
    lines.append(f"Fragmentos de changelog pendientes de publicar: {pending}.")
    return lines


def main() -> int:
    """Print context for Claude. Never fails: a broken hook must not block the session."""
    try:
        core = (PLUGIN_ROOT / "context" / "core.md").read_text(encoding="utf-8")
        cmd = f'python3 "{MTH}"'
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"export MTH='{cmd}'\n")
        print(core.replace("{{MTH}}", cmd).replace("{{PRINCIPLES}}", str(PLUGIN_ROOT / "PRINCIPLES.md")))
        print("\n".join(_state(Path.cwd())))
    except Exception as exc:  # noqa: BLE001 — hook boundary.
        print(f"[claude-methodology] contexto no disponible: {exc}", file=sys.stderr)
    return 0
