"""Registry of traceable identifiers (SPEC-NNNN, ADR-NNNN, F-001...).

An ID is *defined* where a markdown heading in one of its ``defined_in``
files starts with it (``# ADR-NNNN · Título`` or ``## F-001 · Runner``).
Everything else that mentions it is a *reference*.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import globs
from .config import Config
from .errors import MthError

_HEADING = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
_MAX_BYTES = 1_000_000


def read_text(path: Path) -> str | None:
    """Return the file as UTF-8 text, or None for binary/oversized files."""
    try:
        if path.stat().st_size > _MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


class IdRegistry:
    """Index of ID definitions built from the working tree.

    Args:
        cfg: Repository configuration.
        files: Repository files (relative POSIX paths).
    """

    def __init__(self, cfg: Config, files: list[str]) -> None:
        self.cfg = cfg
        self.kinds: dict[str, str] = {k: v["pattern"] for k, v in cfg["ids"].items()}
        self._any = re.compile(r"(?<![\w-])(?:" + "|".join(
            f"(?:{p})" for p in self.kinds.values()) + r")(?![\w])")
        self._exact = {k: re.compile(rf"^(?:{p})$") for k, p in self.kinds.items()}
        self.definitions: dict[str, list[tuple[str, int]]] = {}
        for kind, spec in cfg["ids"].items():
            start = re.compile(rf"^(?:{spec['pattern']})(?![\w])")
            for rel in files:
                if not globs.match_any(rel, spec["defined_in"]):
                    continue
                text = read_text(cfg.root / rel)
                for lineno, line in enumerate((text or "").splitlines(), 1):
                    heading = _HEADING.match(line)
                    if heading and (m := start.match(heading.group(1))):
                        self.definitions.setdefault(m.group(0), []).append((rel, lineno))

    def find(self, text: str) -> list[str]:
        """All ID references in ``text``, in order of appearance."""
        return [m.group(0) for m in self._any.finditer(text)]

    def finditer(self, text: str):
        return self._any.finditer(text)

    def kind_of(self, ident: str) -> str | None:
        return next((k for k, rx in self._exact.items() if rx.match(ident)), None)

    def is_defined(self, ident: str) -> bool:
        return ident in self.definitions

    def next_id(self, kind: str) -> str:
        """Next free identifier of ``kind`` (``SPEC-NNNN``).

        Raises:
            MthError: The pattern is not of the simple ``PREFIX\\d{N}`` form.
        """
        pattern = self.kinds[kind]
        m = re.fullmatch(r"([A-Za-z][A-Za-z_-]*)\\d\{(\d+)\}", pattern)
        if not m:
            raise MthError(f"No se puede numerar automáticamente '{kind}' (patrón {pattern}).",
                           hint="Usa un patrón de la forma PREFIJO-\\d{N} o crea el ID a mano.")
        prefix, width = m.group(1), int(m.group(2))
        numbers = [int(i[len(prefix):]) for i in self.definitions
                   if self.kind_of(i) == kind]
        return f"{prefix}{max(numbers, default=0) + 1:0{width}d}"
