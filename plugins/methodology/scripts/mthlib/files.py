"""File helpers shared by the commands that write configuration and hooks."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .errors import MthError


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    """Replace ``path`` with ``text`` atomically: readers see the old or the new file, never half.

    The file keeps its current permissions (0644 when new) unless ``mode`` is given. A symbolic
    link is replaced by a regular file.

    Raises:
        MthError: The file cannot be written (permissions, full disk); the operation can be re-run.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        raise MthError(f"No se pudo escribir {path}: {exc}.",
                       hint="Comprueba permisos y espacio en disco y vuelve a ejecutar: la operación es reanudable.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mode is None:
            mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as exc:
        Path(tmp).unlink(missing_ok=True)
        raise MthError(f"No se pudo escribir {path}: {exc}.",
                       hint="Comprueba permisos y espacio en disco y vuelve a ejecutar: la operación es reanudable.") from exc
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
