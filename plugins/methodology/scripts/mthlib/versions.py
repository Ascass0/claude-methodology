"""Files that declare the project version, rewritten on every release (SPEC-0003)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import globs
from .errors import MthError

_KEYS = {"path", "pattern"}


@dataclass(frozen=True)
class VersionFile:
    path: str
    pattern: re.Pattern[str]


def validate(entries: list[Any]) -> None:
    """Check ``release.version_files`` (fail-fast at configuration load).

    Raises:
        MthError: An entry is not a table with exactly a normalised ``path`` and a
            regex ``pattern`` with one capture group, or two entries are identical.
    """
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        where = f"release.version_files[{index}]"
        if not isinstance(entry, dict) or set(entry) != _KEYS or not all(isinstance(entry[k], str) for k in _KEYS):
            raise MthError(f"'{where}' debe tener exactamente 'path' y 'pattern' (textos).")
        if not globs.valid_path(entry["path"]):
            raise MthError(f"'{where}.path' = '{entry['path']}' debe ser una ruta relativa normalizada, sin '..'.")
        try:
            groups = re.compile(entry["pattern"]).groups
        except re.error as exc:
            raise MthError(f"'{where}.pattern' no es una expresión regular válida: {exc}.") from exc
        if groups != 1:
            raise MthError(f"'{where}.pattern' debe tener exactamente un grupo de captura (tiene {groups}).",
                           hint="El grupo es la versión: '\"version\": \"(\\d+\\.\\d+\\.\\d+)\"'.")
        key = (entry["path"], entry["pattern"])
        if key in seen:
            raise MthError(f"'{where}' está repetida.")
        seen.add(key)


def from_config(entries: list[dict[str, str]]) -> list[VersionFile]:
    return [VersionFile(e["path"], re.compile(e["pattern"])) for e in entries]


def _text(path: Path) -> str:
    # Decoded from bytes, not read_text(): universal newlines would turn CRLF into LF on write (AC-07).
    return path.read_bytes().decode("utf-8")


def _match(root: Path, item: VersionFile) -> tuple[Path, str, re.Match[str]]:
    """The file, its text and the single match of ``item.pattern`` in it.

    Raises:
        MthError: The file is missing, the pattern does not match exactly once or
            its capture group does not take part in the match.
    """
    path = root / item.path
    if not path.is_file():
        raise MthError(f"No existe el fichero de versión {item.path}.",
                       hint="Corrige release.version_files o crea el fichero.")
    text = _text(path)
    matches = list(item.pattern.finditer(text))
    if len(matches) != 1:
        raise MthError(f"El patrón de versión de {item.path} aparece {len(matches)} veces (debe aparecer una).",
                       hint="Ajusta release.version_files.pattern para que identifique una sola versión.")
    if matches[0].group(1) is None:  # AC-08: an optional group that matched nothing has no position
        raise MthError(f"El grupo de captura del patrón de versión de {item.path} no captura nada.",
                       hint="El grupo de la versión no puede ser opcional.")
    return path, text, matches[0]


def read(root: Path, item: VersionFile) -> str:
    """Version currently declared by ``item``.

    Raises:
        MthError: Same conditions as :func:`_match`.
    """
    return _match(root, item)[2].group(1)


def write(root: Path, items: list[VersionFile], version: str) -> list[str]:
    """Set ``version`` in every file. Returns the paths that changed.

    Every file is checked before any is written, so a broken entry leaves all of them untouched.

    Raises:
        MthError: Same conditions as :func:`_match`.
    """
    found = [_match(root, item) for item in items]
    changed = []
    for item, (path, text, match) in zip(items, found):
        if match.group(1) == version:
            continue
        path.write_bytes((text[:match.start(1)] + version + text[match.end(1):]).encode("utf-8"))
        changed.append(item.path)
    return changed
