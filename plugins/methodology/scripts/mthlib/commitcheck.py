"""The commit-msg hook: read the message file git hands over and validate it (``mth check-msg``)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import commits
from .config import load
from .errors import EXIT_ERROR
from .git import Git
from .ids import IdRegistry


def check_file(message_file: str) -> int:
    """Validate the message in ``message_file`` and return the exit code of ``mth check-msg``.

    Raises:
        MthError: Not a repository, or invalid configuration.
    """
    git = Git.discover(Path.cwd())
    cfg = load(git.root)
    errors = commits.validate(Path(message_file).read_text(encoding="utf-8"), cfg, IdRegistry(cfg, git.files()))
    if errors:
        print("✗ Mensaje de commit inválido:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return EXIT_ERROR
    return 0
