"""Test labels (ADR-0015, SPEC-0019): every test says why it exists.

Pure functions over text: the caller reads files and chooses the opening-line regex of each language.
A label is ``verifies: SPEC-NNNN/AC-NN`` (or ``/FM-NN``), ``regression: <ref>`` or ``unit: <symbol>``
in a comment or docstring of the test's *region*: its contiguous leading comments and decorators up to
the line before the next test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import globs

KEYWORD = re.compile(r"\b(verifies|regression|unit)\s*:", re.IGNORECASE)
_LEADING = re.compile(r"^\s*(?:#|//|/\*|\*|@)")
NAME_GLOBS = ("**/test_*", "**/*_test.*", "**/*.test.*", "**/*.spec.*")
DATA_EXTENSIONS = (".md", ".json", ".toml", ".yaml", ".yml", ".txt", ".csv", ".snap")


@dataclass(frozen=True)
class Problem:
    line: int
    message: str


def pattern_for(path: str, test_patterns: dict[str, str]) -> str | None:
    """Regex of the line that opens a test in ``path``; None when the language has no pattern."""
    for glob, regex in test_patterns.items():
        if regex and globs.match(path, glob):
            return regex
    return None


def is_test_file(path: str) -> bool:
    """A file named like a test and written in code (not data)."""
    return globs.match_any(path, list(NAME_GLOBS)) and not path.lower().endswith(DATA_EXTENSIONS)


def _valid(match: re.Match[str], line: str, spec_pattern: str) -> bool:
    rest = line[match.end():].strip()
    if match.group(1).lower() == "verifies":
        return re.match(rf"(?:{spec_pattern})/(?:AC|FM)-\d{{2,3}}(?![\w-])", rest) is not None
    return bool(rest)


def _labels(lines: list[str], spec_pattern: str) -> tuple[bool, str | None]:
    """Whether the lines hold a valid label, and the first malformed one found."""
    malformed = None
    for line in lines:
        for m in KEYWORD.finditer(line):
            if _valid(m, line, spec_pattern):
                return True, None
            malformed = malformed or line[m.start():].strip()[:60]
    return False, malformed


def file_problems(text: str, opening: str | None, spec_pattern: str) -> list[Problem]:
    """Unlabelled tests of a test file; with no ``opening`` regex, the file needs at least one label."""
    lines = text.splitlines()
    if opening is None:
        ok, bad = _labels(lines, spec_pattern)
        if ok:
            return []
        detail = f" (etiqueta mal formada: «{bad}»)" if bad else ""
        return [Problem(1, f"fichero de tests sin ninguna etiqueta verifies:, regression: o unit:{detail}")]
    opens = re.compile(opening)
    starts = [i for i, line in enumerate(lines) if opens.match(line)]
    begins = []
    for i in starts:
        while i > 0 and _LEADING.match(lines[i - 1]):
            i -= 1
        begins.append(i)
    out = []
    for n, start in enumerate(starts):
        end = begins[n + 1] if n + 1 < len(begins) else len(lines)
        ok, bad = _labels(lines[begins[n]:end], spec_pattern)
        if not ok:
            title = lines[start].strip()[:60]
            detail = f"etiqueta mal formada «{bad}»" if bad else "sin etiqueta (verifies:, regression: o unit:)"
            out.append(Problem(start + 1, f"test {detail}: {title}"))
    return out
