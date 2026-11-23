"""Subprocess helpers with uniform error reporting."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import MthError

_TAIL_LINES = 15


def _tail(text: str) -> str:
    lines = text.strip().splitlines()
    return "\n".join(lines[-_TAIL_LINES:])


def run(args: list[str], cwd: Path | None = None, check: bool = True,
        input_text: str | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a command capturing its output.

    Args:
        args: Command and arguments (never passed through a shell).
        cwd: Working directory.
        check: Raise on non-zero exit.
        input_text: Data sent to stdin.
        timeout: Seconds before the command is killed (None: no limit).

    Raises:
        MthError: The executable is missing, it timed out, or it failed and ``check`` is true.
    """
    try:
        proc = subprocess.run(args, cwd=cwd, input=input_text,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MthError(f"'{' '.join(args)}' no respondió en {timeout} s.") from exc
    except FileNotFoundError as exc:
        raise MthError(f"No se encuentra el ejecutable '{args[0]}'.",
                       hint="Instálalo y comprueba el PATH.") from exc
    if check and proc.returncode != 0:
        raise MthError(f"Falló: {' '.join(args)}",
                       hint=_tail(proc.stderr or proc.stdout) or None)
    return proc


def run_shell(command: str, cwd: Path) -> int:
    """Run a repo-configured shell command, streaming its output.

    Returns:
        The exit code.
    """
    return subprocess.run(command, shell=True, cwd=cwd).returncode
