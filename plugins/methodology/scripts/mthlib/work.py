"""Local working directory ``.work/``, excluded from git (SPEC-0010, ADR-0006).

Claude keeps there what is not part of the repository: plans, PR bodies,
review and security reports, notes and temporary files. It is excluded in
``.git/info/exclude`` so no versioned file of the target repository changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import MthError
from .git import Git

WORK_DIR = ".work"
DEFAULT_DIRS = ("plans", "merge-request", "security-report", "reviews", "notes", "tmp")
EXCLUDE_LINE = f"/{WORK_DIR}/"
EXCLUDE_COMMENT = "# claude-methodology: directorio de trabajo local (SPEC-0010)"
_EXCLUDING = {WORK_DIR, f"{WORK_DIR}/", f"/{WORK_DIR}", EXCLUDE_LINE}
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate(dirs: list[Any]) -> None:
    """Check ``work.dirs`` (fail-fast at configuration load).

    Raises:
        MthError: A name is not a single lowercase segment, is repeated or is a default one.
    """
    seen: set[str] = set()
    for index, name in enumerate(dirs):
        where = f"work.dirs[{index}]"
        if not isinstance(name, str) or not _NAME.match(name):
            raise MthError(f"'{where}' = {name!r} debe ser un único segmento en minúsculas ({_NAME.pattern}).")
        if name in DEFAULT_DIRS:
            raise MthError(f"'{where}' = '{name}' ya es un subdirectorio de serie de {WORK_DIR}/.")
        if name in seen:
            raise MthError(f"'{where}' = '{name}' está repetido.")
        seen.add(name)


def subdirs(extra: list[str]) -> list[str]:
    return [*DEFAULT_DIRS, *extra]


@dataclass(frozen=True)
class Status:
    tracked: list[str]
    not_a_directory: bool
    missing: list[str] = field(default_factory=list)
    excluded: bool = False

    @property
    def blocked(self) -> str | None:
        """Why ``.work/`` cannot be prepared, or None."""
        if self.tracked:
            shown = ", ".join(self.tracked[:5]) + (" …" if len(self.tracked) > 5 else "")
            return f"git versiona ficheros bajo {WORK_DIR}/: {shown}"
        if self.not_a_directory:
            return f"{WORK_DIR} existe y no es un directorio"
        return None

    @property
    def ready(self) -> bool:
        return self.blocked is None and not self.missing and self.excluded


def _exclude_file(git: Git) -> Path:
    path = Path(git.out("rev-parse", "--git-path", "info/exclude"))
    return path if path.is_absolute() else git.root / path


def _is_excluded(text: str) -> bool:
    return any(line.strip() in _EXCLUDING for line in text.splitlines())


def inspect(git: Git, extra: list[str]) -> Status:
    """Current state of ``.work/`` (read only)."""
    root = git.root / WORK_DIR
    tracked = [f for f in git.out("ls-files", "--", WORK_DIR).splitlines() if f]
    exclude = _exclude_file(git)
    excluded = exclude.is_file() and _is_excluded(exclude.read_text(encoding="utf-8", errors="replace"))
    if tracked or (root.exists() and not root.is_dir()):
        return Status(tracked, not tracked, excluded=excluded)
    missing = [d for d in subdirs(extra) if not (root / d).is_dir()]
    return Status([], False, missing, excluded)


def ensure(git: Git, extra: list[str]) -> list[str]:
    """Create ``.work/`` and its subdirectories and exclude it from git. Returns what changed.

    Raises:
        MthError: ``.work`` is versioned or is not a directory (nothing is touched), or a
            directory or the exclude file cannot be written.
    """
    status = inspect(git, extra)
    if status.blocked:
        raise MthError(f"No se prepara {WORK_DIR}/: {status.blocked}.",
                       hint=f"Saca {WORK_DIR}/ del control de versiones (git rm -r --cached {WORK_DIR}) o renómbralo.")
    changed = []
    try:
        if not status.excluded:
            exclude = _exclude_file(git)
            exclude.parent.mkdir(parents=True, exist_ok=True)
            text = exclude.read_text(encoding="utf-8", errors="replace") if exclude.is_file() else ""
            separator = "" if not text or text.endswith("\n") else "\n"
            exclude.write_text(f"{text}{separator}{EXCLUDE_COMMENT}\n{EXCLUDE_LINE}\n", encoding="utf-8")
            changed.append(str(exclude.relative_to(git.root)) if exclude.is_relative_to(git.root) else str(exclude))
        for name in status.missing:
            (git.root / WORK_DIR / name).mkdir(parents=True, exist_ok=True)
            changed.append(f"{WORK_DIR}/{name}/")
    except OSError as exc:
        raise MthError(f"No se puede preparar {WORK_DIR}/: {exc}.") from exc
    return changed
