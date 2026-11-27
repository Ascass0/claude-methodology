"""The git hooks mth manages (commit-msg, pre-commit) and the launcher record of the agent-guard shim.

Kept apart from ``setup`` so that the SessionStart hook, which refreshes them on every session, does not
load the adoption machinery (SPEC-0006, SPEC-0024, SPEC-0012).
"""
from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import MthError
from .files import atomic_write

if TYPE_CHECKING:
    from .config import Config
    from .git import Git

MTH = Path(__file__).resolve().parents[1] / "mth"  # launcher: picks a Python >= 3.11
HOOK_MARK = "# managed-by: claude-methodology"


@dataclass(frozen=True)
class HookKind:
    """A git hook that mth manages: the file name, its ``[hooks]`` key and what its script runs."""
    name: str
    key: str
    command: str  # mth subcommand and arguments
    argument: str  # what the foreign hook it chains to receives
    instruction: str  # what a versioned hooks directory needs by hand


COMMIT_MSG = HookKind("commit-msg", "commit_msg", 'check-msg "$1"', ' "$1"',
                      'Añade `mth check-msg "$1"` al hook commit-msg de tu gestor de hooks.')
PRE_COMMIT = HookKind("pre-commit", "pre_commit", "secrets --staged", "",
                      "Añade `mth secrets --staged` al hook pre-commit de tu gestor de hooks.")


def chained_name(kind: HookKind) -> str:
    """Where the foreign hook is kept when ``hooks.<key>`` is ``chain``."""
    return f"{kind.name}.local"


def replaced_name(kind: HookKind) -> str:
    """Where the foreign hook is kept when ``hooks.<key>`` is ``replace``."""
    return f"{kind.name}.pre-mth"


def hook_script(chain: bool = False, kind: HookKind = COMMIT_MSG) -> str:
    mth = shlex.quote(str(MTH))
    chained = ""
    if chain:  # SPEC-0006: the repo's own hook runs first and can reject the message
        chained = ('chained="$(dirname "$0")/' + chained_name(kind) + '"\n'
                   'if [ ! -x "$chained" ]; then\n'
                   f"  echo '✗ falta el hook encadenado {chained_name(kind)} o no es ejecutable: restáuralo o cambia hooks.{kind.key}' >&2\n"
                   "  exit 1\nfi\n"
                   f'"$chained"{kind.argument} || exit $?\n')
    return ("#!/bin/sh\n" f"{HOOK_MARK}\n"
            f"if [ ! -f {mth} ]; then\n"
            "  echo '✗ claude-methodology no encontrado: abre una sesión de Claude Code o ejecuta mth doctor' >&2\n"
            "  exit 1\nfi\n"
            f"{chained}"
            f"exec sh {mth} {kind.command}\n")


def _versioned_hooks(git: Git) -> bool:
    hooks = git.hooks_dir().resolve()
    return hooks.is_relative_to(git.root.resolve()) and not hooks.is_relative_to(git.git_dir().resolve())


def check_hook_mode(git: Git, mode: str, kind: HookKind = COMMIT_MSG) -> None:
    """Fail before any change when ``mode`` cannot be applied to a foreign hook.

    Raises:
        MthError: Same conditions as :func:`install_hook`.
    """
    path = git.hooks_dir() / kind.name
    if mode == "own" or not path.exists() or HOOK_MARK in path.read_text(encoding="utf-8", errors="replace"):
        return
    if _versioned_hooks(git):
        raise MthError(f"El directorio de hooks ({git.hooks_dir()}) está versionado: lo gestiona otra herramienta.",
                       hint=kind.instruction)
    backup = git.hooks_dir() / (chained_name(kind) if mode == "chain" else replaced_name(kind))
    if backup.exists():
        raise MthError(f"No se puede guardar el hook {kind.name} ajeno: {backup.name} ya existe.",
                       hint="Revisa ese fichero y bórralo o renómbralo antes de volver a instalar.")


def install_hook(git: Git, mode: str = "own", kind: HookKind = COMMIT_MSG) -> str:
    """Install or refresh a hook according to ``hooks.<key>``. Returns a status word.

    ``own`` never touches a foreign hook (``foreign``); ``replace`` keeps it as
    ``<name>.pre-mth`` (``replaced``); ``chain`` keeps it as ``<name>.local``
    and runs it first (``chained``).

    Raises:
        MthError: ``replace``/``chain`` on a versioned hooks directory, or the backup name is taken.
    """
    hooks = git.hooks_dir()
    path = hooks / kind.name
    desired = hook_script(chain=mode == "chain", kind=kind)
    status = "installed"
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARK in current:
            if current == desired:
                return "current"
        elif mode == "own":
            return "foreign"
        else:
            check_hook_mode(git, mode, kind)
            path.rename(hooks / (chained_name(kind) if mode == "chain" else replaced_name(kind)))
            status = "chained" if mode == "chain" else "replaced"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desired, encoding="utf-8")
    path.chmod(0o755)
    return status


def hook_state(git: Git, mode: str = "own", kind: HookKind = COMMIT_MSG) -> str:
    """Read-only state of a hook: ``current``, ``stale`` (ours, outdated), ``foreign`` or ``absent``."""
    path = git.hooks_dir() / kind.name
    if not path.exists():
        return "absent"
    current = path.read_text(encoding="utf-8", errors="replace")
    if HOOK_MARK not in current:
        return "foreign"
    return "current" if current == hook_script(chain=mode == "chain", kind=kind) else "stale"


def remove_hook(git: Git, kind: HookKind) -> bool:
    """Delete our hook (never a foreign one nor the saved copies). True when something was removed."""
    path = git.hooks_dir() / kind.name
    if path.is_file() and HOOK_MARK in path.read_text(encoding="utf-8", errors="replace"):
        path.unlink()
        return True
    return False


def sync_secrets_hook(git: Git, cfg: Config) -> str | None:
    """Apply ``secrets.hook`` to the pre-commit hook (SPEC-0024): install on ``on``, retire ours on ``off``.

    Returns the install status, ``removed``, or None when there is nothing to do (undecided).

    Raises:
        MthError: Same conditions as :func:`install_hook`.
    """
    switch = cfg["secrets"]["hook"]
    if switch == "on":
        return install_hook(git, cfg["hooks"]["pre_commit"], PRE_COMMIT)
    if switch == "off" and remove_hook(git, PRE_COMMIT):
        return "removed"
    return None


LAUNCHER = Path("mth") / "launcher"
MTH_PY = MTH.parent / "mth.py"


def register_launcher(git: Git) -> Path:
    """Record the interpreter and ``mth.py`` in ``<git-common-dir>/mth/launcher`` for the agent-guard shim.

    The plugin path changes with every version, like the commit-msg hook. The interpreter is
    the one already validated for this session (>= 3.11): the shim runs it directly, skipping
    the launcher's interpreter search on every subagent tool call (SPEC-0012).
    """
    path = git.common_dir() / LAUNCHER
    record = f"{sys.executable}\n{MTH_PY}\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != record:
        atomic_write(path, record)  # concurrent sessions never leave a half-written record
    return path
