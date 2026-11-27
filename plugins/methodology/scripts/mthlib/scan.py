"""Authorized network scans for the execution auditor (SPEC-0028, ADR-0025).

The only network path of the auditor: a target must equal an ``audit.targets`` entry, the tool runs without a shell
with fixed arguments, and the output is kept as untrusted data under ``.work/security-report/``.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import MthError

REPORT_DIR = Path(".work") / "security-report"
TIMEOUT_S = 600
MAX_OUTPUT = 5 * 1024 * 1024
_TARGET = re.compile(r"^(?P<host>[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::(?P<port>\d{1,5}))?$")


@dataclass(frozen=True)
class ScanTool:
    """A scan tool: executable names, default port and fixed arguments with ``{host}``, ``{port}`` and ``{hostport}`` placeholders."""

    name: str
    executables: tuple[str, ...]
    default_port: int
    arguments: tuple[str, ...]  # fixed arguments; ``{host}``/``{port}``/``{hostport}`` are replaced by the validated target


TOOLS: dict[str, ScanTool] = {t.name: t for t in (
    ScanTool("testssl", ("testssl.sh", "testssl"), 443,
             ("--quiet", "--color", "0", "--warnings", "batch", "{hostport}")),
    ScanTool("ssh-audit", ("ssh-audit",), 22, ("--json", "--timeout", "10", "--port", "{port}", "{host}")),
)}


def normalize(target: str) -> tuple[str, int | None]:
    """Host (lower case) and port of a ``host`` or ``host:port`` text; raises ``MthError`` on anything else."""
    match = _TARGET.fullmatch(target) if isinstance(target, str) else None
    if match is None or match["host"].startswith("-"):
        raise MthError(f"Destino no válido: {target!r}.", hint="Usa host o host:puerto, sin esquema, ruta, espacios ni comodines.")
    port = int(match["port"]) if match["port"] else None
    if port is not None and not 1 <= port <= 65535:
        raise MthError(f"Puerto fuera de rango en el destino {target!r}.")
    return match["host"].lower(), port


def validate(targets: object) -> None:
    """Validate ``audit.targets`` when the configuration loads (SPEC-0028/AC-01)."""
    if not isinstance(targets, list):
        raise MthError("'audit.targets' debe ser una lista de textos.")
    for entry in targets:
        try:
            normalize(entry)
        except MthError as exc:
            raise MthError(f"'audit.targets' tiene una entrada no válida: {entry!r}.", hint=exc.hint) from exc


def authorize(target: str, targets: list[str]) -> tuple[str, int | None]:
    """The normalized target when it equals an entry of ``targets``; otherwise ``MthError`` and nothing runs."""
    wanted = normalize(target)
    if wanted not in {normalize(entry) for entry in targets}:
        raise MthError(f"El destino {target} no está autorizado.",
                       hint="Un destino se autoriza añadiéndolo a audit.targets en .claude/methodology.toml (cambio revisado en PR).")
    return wanted


def _executable(tool: ScanTool, which: Callable[[str], str | None]) -> str:
    for name in tool.executables:
        if found := which(name):
            return found
    raise MthError(f"No se encuentra {tool.executables[0]} en el PATH.",
                   hint="Instálalo tú: mth no lo descarga. Los controles que dependen de él quedan `no evaluable`.")


def run_to_file(argv: list[str], output: Path, timeout: float, limit: int) -> int:
    """Run ``argv`` (no shell) with stdout going to ``output``; kills the whole process group on timeout or when ``output`` passes ``limit``."""
    with output.open("wb") as sink:
        proc = subprocess.Popen(argv, stdout=sink, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                return proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                over = time.monotonic() > deadline or output.stat().st_size > limit
                if over:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise MthError(f"{argv[0]} superó el tiempo ({timeout:.0f} s) o el tamaño ({limit} bytes) máximos: sin resultado, "
                                   "el control queda `no evaluable`.") from None


Runner = Callable[[list[str], Path, float, int], int]


def scan(tool_name: str, target: str, targets: list[str], root: Path, *, which: Callable[[str], str | None] = shutil.which,
         runner: Runner = run_to_file, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[Path, int]:
    """Run ``tool_name`` against an authorized ``target``; returns the output file and the tool's exit code."""
    tool = TOOLS.get(tool_name)
    if tool is None:
        raise MthError(f"Herramienta de escaneo desconocida: {tool_name}.", hint=f"Disponibles: {', '.join(TOOLS)}.")
    host, port = authorize(target, targets)
    port = port or tool.default_port
    values = {"host": host, "port": str(port), "hostport": f"{host}:{port}"}
    argv = [_executable(tool, which), *(arg.format(**values) for arg in tool.arguments)]
    path = root / REPORT_DIR / f"scan-{tool.name}-{host}-{port}-{now().strftime('%Y%m%dT%H%M%SZ')}.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        code = runner(argv, path, TIMEOUT_S, MAX_OUTPUT)
        if path.stat().st_size > MAX_OUTPUT:
            raise MthError(f"La salida de {tool.name} supera {MAX_OUTPUT} bytes y no se guarda.")
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise MthError(f"No se pudo ejecutar o guardar {tool.name}: {exc}.", hint="Comprueba permisos y espacio en .work/security-report/.") from exc
    except MthError:
        path.unlink(missing_ok=True)
        raise
    return path, code
