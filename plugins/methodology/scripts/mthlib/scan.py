"""Authorized network scans for the execution auditor (SPEC-0028, ADR-0025).

The only network path of the auditor: a target must equal an ``audit.targets`` entry, the tool runs without a shell
with fixed arguments, and the output is kept as untrusted data under ``.work/security-report/``.
"""
from __future__ import annotations

import re
import shutil
import subprocess
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
    match = _TARGET.match(target) if isinstance(target, str) else None
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


def scan(tool_name: str, target: str, targets: list[str], root: Path, *,
         which: Callable[[str], str | None] = shutil.which,
         runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[Path, int]:
    """Run ``tool_name`` against an authorized ``target``; returns the output file and the tool's exit code."""
    tool = TOOLS.get(tool_name)
    if tool is None:
        raise MthError(f"Herramienta de escaneo desconocida: {tool_name}.", hint=f"Disponibles: {', '.join(TOOLS)}.")
    host, port = authorize(target, targets)
    port = port or tool.default_port
    executable = _executable(tool, which)
    values = {"host": host, "port": str(port), "hostport": f"{host}:{port}"}
    argv = [executable, *(arg.format(**values) for arg in tool.arguments)]
    try:
        done = runner(argv, capture_output=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MthError(f"{tool.name} no terminó en {TIMEOUT_S} s: sin resultado, el control queda `no evaluable`.") from exc
    except OSError as exc:
        raise MthError(f"No se pudo ejecutar {tool.name}: {exc}.") from exc
    if len(done.stdout) > MAX_OUTPUT:
        raise MthError(f"La salida de {tool.name} supera {MAX_OUTPUT} bytes y no se guarda.")
    directory = root / REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"scan-{tool.name}-{host}-{port}-{stamp}.txt"
    path.write_bytes(done.stdout)
    return path, done.returncode
