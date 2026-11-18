"""Gitignore-like glob matching on POSIX relative paths (``**`` crosses directories)."""
from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def match(path: str, pattern: str) -> bool:
    return bool(_compile(pattern).match(path))


def match_any(path: str, patterns: list[str]) -> bool:
    return any(match(path, p) for p in patterns)


def valid_path(path: str) -> bool:
    """Normalised relative POSIX path (or glob) that stays inside the repository.

    ``./a``, ``a//b`` or ``a/`` are rejected rather than normalised: two
    spellings of one file would defeat the overlap check.
    """
    parts = path.split("/")
    return bool(path) and "\\" not in path and all(p not in ("", ".", "..") for p in parts)
