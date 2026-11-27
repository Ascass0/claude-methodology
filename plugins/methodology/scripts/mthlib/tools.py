"""External tools manager (ADR-0023, SPEC-0025): pinned manifest, resolver, verified download and user cache.

The manifest is data, so adding a tool adds no code. Nothing here downloads unless ``install`` is called, and
nothing is executed that was not verified: the archive sum is checked before extracting and the executable sum is
checked before every use of a managed copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any

from .errors import MthError
from .files import atomic_write
from .proc import run

MANIFEST = Path(__file__).resolve().parents[2] / "tools" / "manifest.toml"
CACHE_ENV = "MTH_TOOLS_DIR"
SYSTEMS = ("linux", "darwin", "windows")
ARCHITECTURES = ("x64", "arm64")
FORMATS = ("tar.gz", "zip")
SHA256 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
DOWNLOAD_TIMEOUT = 60  # seconds per socket operation
DOWNLOAD_TOTAL = 300  # seconds for a whole attempt
VERSION_TIMEOUT = 30  # seconds: a tool that does not print its version counts as unrecognised
MAX_DOWNLOAD = 200 * 1024 * 1024
MAX_MEMBERS = 5000
MAX_EXTRACTED = 1024 * 1024 * 1024
ATTEMPTS = 3
META = "installed.json"
TREE = "tree"
Fetch = Callable[[str, Path, int, float], None]


class NotFound(MthError):
    """The tool is neither on the PATH nor installed as a managed copy."""


@dataclass(frozen=True)
class Platform:
    url: str
    sha256: str
    format: str
    entry: str


@dataclass(frozen=True)
class Tool:
    name: str
    version: str
    version_args: tuple[str, ...]
    platforms: dict[str, Platform]


@dataclass(frozen=True)
class Resolved:
    path: Path
    origin: str  # "PATH" or "gestionada"
    version: tuple[int, int, int] | None
    warning: str = ""


# -- manifest ------------------------------------------------------------------
def _field(tool: str, where: str, table: dict[str, Any], key: str, kind: type) -> Any:
    value = table.get(key)
    if not isinstance(value, kind) or (kind is str and not value):
        raise MthError(f"Manifiesto de herramientas: '{tool}' {where}: el campo '{key}' falta o no es válido.")
    return value


def _platform(tool: str, key: str, table: Any) -> Platform:
    where = f"en la plataforma {key}"
    system, _, arch = key.partition("_")
    if system not in SYSTEMS or arch not in ARCHITECTURES or not isinstance(table, dict):
        raise MthError(f"Manifiesto de herramientas: '{tool}': la plataforma '{key}' no es válida.",
                       hint=f"Usa <sistema>_<arquitectura> con sistema {', '.join(SYSTEMS)} y arquitectura {', '.join(ARCHITECTURES)}.")
    url = _field(tool, where, table, "url", str)
    digest = _field(tool, where, table, "sha256", str)
    fmt = _field(tool, where, table, "format", str)
    entry = _field(tool, where, table, "entry", str)
    if not url.startswith("https://"):
        raise MthError(f"Manifiesto de herramientas: '{tool}' {where}: el campo 'url' debe ser https.")
    if not SHA256.fullmatch(digest):
        raise MthError(f"Manifiesto de herramientas: '{tool}' {where}: el campo 'sha256' debe tener 64 hexadecimales en minúsculas.")
    if fmt not in FORMATS:
        raise MthError(f"Manifiesto de herramientas: '{tool}' {where}: el campo 'format' debe ser {' o '.join(FORMATS)}.")
    parts = PurePosixPath(entry).parts
    if PurePosixPath(entry).is_absolute() or ".." in parts or "\\" in entry or ":" in entry:
        raise MthError(f"Manifiesto de herramientas: '{tool}' {where}: el campo 'entry' debe ser una ruta relativa sin '..'.")
    return Platform(url, digest, fmt, entry)


def parse_manifest(text: str) -> dict[str, Tool]:
    """Tools of a manifest text.

    Raises:
        MthError: The text is not valid TOML or a field is missing or invalid (names tool, platform and field).
    """
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise MthError(f"Manifiesto de herramientas ilegible: {exc}.") from exc
    out: dict[str, Tool] = {}
    for name, table in raw.items():
        if not isinstance(table, dict):
            raise MthError(f"Manifiesto de herramientas: '{name}' debe ser una tabla.")
        version = _field(name, "", table, "version", str)
        args = _field(name, "", table, "version_args", list)
        if not VERSION.fullmatch(version) or not args or not all(isinstance(a, str) for a in args):
            raise MthError(f"Manifiesto de herramientas: '{name}': 'version' (X.Y.Z) o 'version_args' no son válidos.")
        platforms = _field(name, "", table, "platforms", dict)
        out[name] = Tool(name, version, tuple(args), {k: _platform(name, k, v) for k, v in platforms.items()})
    return out


def load_manifest(path: Path = MANIFEST) -> dict[str, Tool]:
    """The tools declared by the plugin manifest (``MthError`` if it cannot be read or is invalid)."""
    try:
        return parse_manifest(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MthError(f"No se puede leer el manifiesto de herramientas ({path}): {exc}.") from exc


def tool_named(name: str, manifest: dict[str, Tool] | None = None) -> Tool:
    """One tool of the manifest.

    Raises:
        MthError: The manifest has no such tool.
    """
    tools = manifest if manifest is not None else load_manifest()
    if name not in tools:
        raise MthError(f"'{name}' no está en el manifiesto de herramientas.", hint=f"Disponibles: {', '.join(tools) or 'ninguna'}.")
    return tools[name]


# -- platform and cache ----------------------------------------------------------
def platform_key() -> str:
    """``<sistema>_<arquitectura>`` of this machine (for example ``linux_x64``)."""
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("x86_64", "amd64") else machine
    return f"{system}_{arch}"


def cache_root(env: dict[str, str] | None = None) -> Path:
    """The user cache for managed tools: ``$MTH_TOOLS_DIR`` or the system cache directory."""
    env = os.environ if env is None else env
    if env.get(CACHE_ENV):
        return Path(env[CACHE_ENV])
    if sys.platform == "win32":
        base = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(env.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "claude-methodology" / "tools"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- resolution --------------------------------------------------------------------
def parse_version(text: str) -> tuple[int, int, int] | None:
    found = VERSION.search(text)
    return (int(found[1]), int(found[2]), int(found[3])) if found else None


def tool_version(path: Path, tool: Tool) -> tuple[int, int, int] | None:
    """Version the executable prints, or None when it fails, does not finish or prints nothing recognisable."""
    try:
        return parse_version(run([str(path), *tool.version_args], check=False, timeout=VERSION_TIMEOUT).stdout)
    except MthError:
        return None


def managed_path(tool: Tool, root: Path) -> Path | None:
    """The verified executable of the managed copy, or None when it is not installed.

    Raises:
        MthError: The copy exists but was altered after installing it (fail closed).
    """
    folder = root / tool.name / tool.version
    meta_file = folder / META
    if not meta_file.is_file():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        executable = folder / TREE / meta["entry"]
        intact = executable.is_file() and not executable.is_symlink() and _sha256(executable) == meta["entry_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        intact = False
    if not intact:
        raise MthError(f"La copia gestionada de {tool.name} {tool.version} se alteró o está incompleta ({folder}).",
                       hint=f"Reinstálala con `mth tools install {tool.name} --force`.")
    return executable


def resolve(tool: Tool, minimum: tuple[int, int, int] | None = None, root: Path | None = None) -> Resolved:
    """Where to run ``tool`` from: the PATH if recent enough, else the verified managed copy (SPEC-0025).

    Never downloads.

    Raises:
        NotFound: Neither the PATH nor a managed copy has the tool.
        MthError: The managed copy was altered.
    """
    root = root or cache_root()
    on_path = shutil.which(tool.name)
    version = tool_version(Path(on_path), tool) if on_path and minimum else None
    if on_path and (minimum is None or (version is not None and version >= minimum)):
        return Resolved(Path(on_path), "PATH", version)
    managed = managed_path(tool, root)
    if managed is not None:
        return Resolved(managed, "gestionada", parse_version(tool.version))
    if on_path:
        wanted = ".".join(map(str, minimum or ()))
        return Resolved(Path(on_path), "PATH", version, f"{tool.name} del PATH es anterior a {wanted} o su versión no se reconoce")
    raise NotFound(f"No se encuentra '{tool.name}' en el PATH ni como copia gestionada.",
                   hint=f"Instálalo con `mth tools install {tool.name}` o ponlo en el PATH.")


# -- download --------------------------------------------------------------------------
class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 — stdlib signature
        if not newurl.startswith("https://"):
            raise urllib.error.URLError(f"redirección a un destino que no es https: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, dest: Path, limit: int, timeout: float) -> None:
    """Fetch ``url`` into ``dest`` (https only, at most ``limit`` bytes).

    Raises:
        MthError: The body is larger than ``limit``.
        OSError: Network failure or timeout (the caller retries).
    """
    opener = urllib.request.build_opener(_HttpsOnly)
    request = urllib.request.Request(url, headers={"User-Agent": "claude-methodology"})
    total = 0
    deadline = time.monotonic() + DOWNLOAD_TOTAL
    with opener.open(request, timeout=timeout) as response, dest.open("wb") as out:
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise MthError(f"La descarga supera el tamaño máximo ({limit} bytes): {url}")
        for chunk in iter(lambda: response.read(1 << 16), b""):
            total += len(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError(f"La descarga supera el tiempo máximo ({DOWNLOAD_TOTAL} s): {url}")
            if total > limit:
                raise MthError(f"La descarga supera el tamaño máximo ({limit} bytes): {url}")
            out.write(chunk)


def _fetch_with_retries(fetch: Fetch, url: str, dest: Path, sleep: Callable[[float], None], name: str) -> None:
    for attempt in range(ATTEMPTS):
        try:
            fetch(url, dest, MAX_DOWNLOAD, DOWNLOAD_TIMEOUT)
            return
        except OSError as exc:  # URLError and timeouts are OSError: retry with growing waits
            permanent = isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code not in (408, 429)
            if permanent or attempt == ATTEMPTS - 1:
                raise MthError(f"No se pudo descargar {url}: {exc}.",
                               hint=f"Comprueba la red o el proxy, o instala {name} a mano en el PATH.") from exc
            sleep(2 ** attempt)


# -- extraction --------------------------------------------------------------------------
def _target(base: Path, name: str) -> Path:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in name or not path.parts:
        raise MthError(f"El archivo trae una ruta que sale del destino: {name!r}.")
    target = (base / Path(*path.parts)).resolve()
    if not target.is_relative_to(base.resolve()):
        raise MthError(f"El archivo trae una ruta que sale del destino: {name!r}.")
    return target


def _copy(source: IO[bytes], target: Path, executable: bool, budget: list[int]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        for chunk in iter(lambda: source.read(1 << 16), b""):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise MthError("El archivo descomprimido supera el tamaño máximo.")
            out.write(chunk)
    target.chmod(0o755 if executable else 0o644)


def _extract_tar(archive: Path, dest: Path) -> None:
    budget = [MAX_EXTRACTED]
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            if len(members) > MAX_MEMBERS:
                raise MthError("El archivo tiene demasiados ficheros.")
            for member in members:
                if member.isdir():
                    _target(dest, member.name).mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    source = tar.extractfile(member)
                    if source is None:
                        raise MthError(f"No se puede leer {member.name!r} del archivo.")
                    _copy(source, _target(dest, member.name), bool(member.mode & 0o111), budget)
                else:
                    raise MthError(f"El archivo trae un enlace o un fichero especial: {member.name!r}.")
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise MthError(f"El archivo descargado no se puede extraer: {exc}.") from exc


def _extract_zip(archive: Path, dest: Path) -> None:
    budget = [MAX_EXTRACTED]
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) > MAX_MEMBERS:
                raise MthError("El archivo tiene demasiados ficheros.")
            for info in infos:
                kind = stat.S_IFMT(info.external_attr >> 16)
                if info.is_dir():
                    _target(dest, info.filename).mkdir(parents=True, exist_ok=True)
                elif kind in (0, stat.S_IFREG):
                    with bundle.open(info) as source:
                        _copy(source, _target(dest, info.filename), bool((info.external_attr >> 16) & 0o111), budget)
                else:
                    raise MthError(f"El archivo trae un enlace o un fichero especial: {info.filename!r}.")
    except (zipfile.BadZipFile, EOFError, OSError, NotImplementedError) as exc:
        raise MthError(f"El archivo descargado no se puede extraer: {exc}.") from exc


# -- install and prune ----------------------------------------------------------------------
def _make_cache(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        for level in (folder, folder.parent):
            level.chmod(0o700)
        probe = tempfile.TemporaryDirectory(dir=folder)
        probe.cleanup()
    except OSError as exc:
        raise MthError(f"No se puede escribir en la caché de herramientas ({folder}): {exc}.",
                       hint=f"Define {CACHE_ENV} con un directorio donde puedas escribir.") from exc


def install(tool: Tool, root: Path | None = None, system: str | None = None, force: bool = False,
            fetch: Fetch | None = None, sleep: Callable[[float], None] = time.sleep) -> str:
    """Download, verify and publish the managed copy of ``tool``. Returns ``instalada`` or ``ya instalada``.

    Raises:
        MthError: No entry for this platform, the cache is not writable, the download fails, the sum differs,
            the archive is unsafe or lacks the entry, or an existing copy was altered and ``force`` is not set.
    """
    fetch = fetch or download
    key = system or platform_key()
    if key not in tool.platforms:
        raise MthError(f"{tool.name} {tool.version} no tiene entrada para la plataforma '{key}'.",
                       hint=f"Plataformas del manifiesto: {', '.join(tool.platforms)}. Instálalo a mano en el PATH.")
    entry = tool.platforms[key]
    root = root or cache_root()
    parent = root / tool.name
    _make_cache(parent)
    final = parent / tool.version
    if final.exists() and not force:
        managed_path(tool, root)  # raises if altered
        return "ya instalada"
    staging = Path(tempfile.mkdtemp(prefix=f"{tool.version}.tmp-", dir=parent))
    try:
        archive = staging / "archive"
        _fetch_with_retries(fetch, entry.url, archive, sleep, tool.name)
        if _sha256(archive) != entry.sha256:
            raise MthError(f"La suma SHA-256 de {entry.url} no coincide con la del manifiesto.",
                           hint="No se ha instalado nada. Si la release cambió, actualiza el manifiesto; si no, repite la descarga.")
        tree = staging / TREE
        tree.mkdir()
        (_extract_tar if entry.format == "tar.gz" else _extract_zip)(archive, tree)
        executable = _target(tree, entry.entry)
        if not executable.is_file():
            raise MthError(f"El archivo no contiene el ejecutable '{entry.entry}'.")
        executable.chmod(executable.stat().st_mode | 0o111)
        archive_sum = _sha256(archive)
        archive.unlink()
        atomic_write(staging / META, json.dumps({"version": tool.version, "entry": entry.entry,
                                                 "archive_sha256": archive_sum, "entry_sha256": _sha256(executable)}))
        _publish(staging, final, tool, root, force)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return "instalada"


def _publish(staging: Path, final: Path, tool: Tool, root: Path, force: bool) -> None:
    """Rename ``staging`` to ``final`` atomically; a concurrent winner is verified and kept."""
    old = None
    if force and final.exists():
        old = final.with_name(f"{final.name}.old-{os.getpid()}")
        final.rename(old)
    try:
        staging.rename(final)
    except OSError as exc:  # another install may have published first: keep it only if it is valid
        if managed_path(tool, root) is None:
            if old is not None:
                old.rename(final)
                old = None
            raise MthError(f"No se pudo publicar la copia gestionada de {tool.name}: {exc}.") from exc
    finally:
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)


def _is_ours(folder: Path) -> bool:
    """A managed install (it has its metadata) or a leftover of one; anything else is not ours to delete."""
    if not folder.is_dir() or folder.is_symlink():
        return False
    return (folder / META).is_file() or ".tmp-" in folder.name or ".old-" in folder.name


def prune(manifest: dict[str, Tool], root: Path | None = None) -> list[Path]:
    """Delete managed versions the manifest no longer lists and half-finished installs. Returns what was removed."""
    root = root or cache_root()
    removed: list[Path] = []
    if not root.is_dir():
        return removed
    for tool_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        keep = manifest[tool_dir.name].version if tool_dir.name in manifest else None
        for version_dir in sorted(tool_dir.iterdir()):
            if version_dir.name != keep and _is_ours(version_dir):
                shutil.rmtree(version_dir, ignore_errors=True)
                removed.append(version_dir)
        if keep is None and not any(tool_dir.iterdir()):
            tool_dir.rmdir()
    return removed


def other_versions(tool: Tool, root: Path | None = None) -> list[str]:
    """Versions of ``tool`` installed in the cache other than the one the manifest pins."""
    folder = (root or cache_root()) / tool.name
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.name != tool.version and (p / META).is_file())


def status(tool: Tool, root: Path | None = None) -> tuple[str, str]:
    """``(origen, versión encontrada)`` for the listing: PATH, gestionada, gestionada alterada or ausente."""
    root = root or cache_root()
    on_path = shutil.which(tool.name)
    if on_path:
        found = tool_version(Path(on_path), tool)
        return "PATH", ".".join(map(str, found)) if found else "versión no reconocida"
    try:
        return ("gestionada", tool.version) if managed_path(tool, root) else ("ausente", "-")
    except MthError:
        return "gestionada alterada", tool.version
