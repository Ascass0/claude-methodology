"""Line limit per file (ADR-0016, SPEC-0020): measure, exceptions and the ratchet on a branch.

Pure functions: the caller supplies the counts and, when needed, a function that returns a file's
line count at the branch base, so the rules test without a repository.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from . import globs
from .errors import MthError

EXCEPTION_KEYS = {"path", "max_lines", "reason", "refs"}
CHUNK = 1 << 20


@dataclass(frozen=True)
class Exemption:
    """A declared exception: ``path`` may have up to ``max_lines`` lines because of ``reason``."""

    path: str
    max_lines: int
    reason: str
    refs: str = ""


@dataclass(frozen=True)
class Problem:
    path: str
    message: str


def count_lines(chunks: Iterable[bytes]) -> int | None:
    """Physical lines of a byte stream: newlines, plus one if the last line is not terminated.

    Returns:
        The count, or None when the stream holds a NUL byte (binary).
    """
    lines, last = 0, b"\n"
    for chunk in chunks:
        if not chunk:
            continue
        if b"\0" in chunk:
            return None
        lines += chunk.count(b"\n")
        last = chunk[-1:]
    return lines + (0 if last == b"\n" else 1)


def validate(section: dict[str, Any]) -> list[Exemption]:
    """Check the ``[limits]`` table and return its exceptions.

    Raises:
        MthError: A limit or an exception is incomplete or inconsistent (fail-fast).
    """
    limit = section["max_file_lines"]
    if isinstance(limit, bool) or limit < 1:
        raise MthError(f"'limits.max_file_lines' = {limit} debe ser un entero de 1 o más.")
    if not all(isinstance(p, str) and p for p in section["exclude"]):
        raise MthError("'limits.exclude' debe ser una lista de globs (textos no vacíos).")
    out = []
    for i, item in enumerate(section["exceptions"], 1):
        name = f"limits.exceptions #{i}"
        if not isinstance(item, dict):
            raise MthError(f"'{name}' debe ser una tabla con path, max_lines y reason.")
        path = item.get("path")
        name = f"limits.exceptions (path = {path!r})" if isinstance(path, str) and path else name
        if unknown := sorted(set(item) - EXCEPTION_KEYS):
            raise MthError(f"'{name}' tiene claves desconocidas: {', '.join(unknown)}.",
                           hint=f"Claves admitidas: {', '.join(sorted(EXCEPTION_KEYS))}.")
        if not isinstance(path, str) or not path:
            raise MthError(f"'{name}' necesita 'path' (texto no vacío).")
        ceiling = item.get("max_lines")
        if not isinstance(ceiling, int) or isinstance(ceiling, bool):
            raise MthError(f"'{name}' necesita 'max_lines' (entero): el techo propio del fichero.")
        if ceiling <= limit:
            raise MthError(f"'{name}': max_lines = {ceiling} no supera 'limits.max_file_lines' = {limit}; "
                           "la excepción no haría falta.")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise MthError(f"'{name}' necesita 'reason' (texto no vacío): por qué el fichero debe ser grande.")
        refs = item.get("refs", "")
        if not isinstance(refs, str):
            raise MthError(f"'{name}': 'refs' debe ser un texto.")
        out.append(Exemption(path, ceiling, reason.strip(), refs))
    return out


def evaluate(counts: dict[str, int], limit: int, exemptions: list[Exemption],
             base_lines: Callable[[str], int] | None, config_path: str) -> tuple[list[Problem], list[Problem]]:
    """Errors and warnings of the measured files.

    Args:
        counts: Lines of every measured file.
        limit: ``limits.max_file_lines``.
        exemptions: Declared exceptions.
        base_lines: Lines a file had at the branch base (0 if it did not exist), or None when the
            branch has no parent to compare with. Called only for files that need it.
        config_path: Where exceptions are declared, for the expired ones.
    """
    errors: list[Problem] = []
    warnings: list[Problem] = []
    for path, lines in sorted(counts.items()):
        if lines <= limit:
            continue
        exemption = next((e for e in exemptions if globs.match(path, e.path)), None)
        if exemption is not None:
            if lines > exemption.max_lines:
                errors.append(Problem(path, f"{lines} líneas superan el techo de su excepción ({exemption.max_lines}); "
                                            f"amplíala con su motivo o divide el fichero."))
            continue
        if base_lines is None:
            warnings.append(Problem(path, f"{lines} líneas superan el límite de {limit} (sin rama padre con la que comparar)"))
            continue
        before = base_lines(path)
        if lines > before:
            how = "supera el límite" if before <= limit else "crece estando ya por encima del límite"
            errors.append(Problem(path, f"la rama hace que {how}: {before} → {lines} líneas (límite {limit}). "
                                        "Divide el fichero o declara una excepción en [limits] con su techo y su motivo."))
        else:
            warnings.append(Problem(path, f"{lines} líneas superan el límite de {limit}; la rama no lo hace crecer"))
    for exemption in exemptions:
        matched = [p for p in counts if globs.match(p, exemption.path)]
        if not any(counts[p] > limit for p in matched):
            errors.append(Problem(config_path, f"excepción caducada: '{exemption.path}' ya no supera el límite de {limit} "
                                               "líneas o no existe; bórrala de [limits]."))
    return errors, warnings
