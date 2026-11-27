"""Baseline packs and audit-report verification (SPEC-0027, ADR-0024).

A pack is a versioned TOML file of controls; a report is checked against it so that an auditor can only cite real
controls and must give a result to every mandatory one. Pure functions over text and dates: the CLI does the I/O.
"""
from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errors import MthError

PACKS_DIR = Path(__file__).resolve().parents[2] / "audit" / "packs"
LEVELS = ("minimo", "recomendado")
RESULTS = ("cumple", "no cumple", "no evaluable")
_DECIDED = ("cumple", "no cumple")
_BASELINE = re.compile(r"^\s*Línea base:\s*([\w.-]+)@(\S+)\s+sha256=([0-9a-f]{64})\s*$", re.MULTILINE)
_ROW = re.compile(r"^\s*-\s*([\w.-]+)\s*\|\s*([^|]*?)\s*\|\s*(.*?)\s*$")
_CERTIFIES = re.compile(r"\bcertific(?:ado|ada|a|amos)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Control:
    id: str
    title: str
    level: str
    url: str
    tool: str
    rule: str


@dataclass(frozen=True)
class Pack:
    id: str
    title: str
    version: str
    reviewed: date
    review_months: int
    source_name: str
    source_version: str
    source_url: str
    controls: tuple[Control, ...]
    sha256: str

    def expires(self) -> date:
        months = self.reviewed.month - 1 + self.review_months
        year, month = self.reviewed.year + months // 12, months % 12 + 1
        return date(year, month, min(self.reviewed.day, 28))

    def expired(self, today: date) -> bool:
        return today > self.expires()


def _text(table: dict, key: str, where: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MthError(f"{where}: falta el campo «{key}».")
    return value.strip()


def parse_pack(raw: bytes, name: str) -> Pack:
    """Validated pack from the bytes of its file; ``name`` is only used in messages."""
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise MthError(f"{name}: TOML no válido ({exc}).") from exc
    source = data.get("source")
    if not isinstance(source, dict):
        raise MthError(f"{name}: falta la tabla «source».")
    try:
        reviewed = date.fromisoformat(_text(data, "reviewed", name))
    except ValueError as exc:
        raise MthError(f"{name}: «reviewed» no es una fecha ISO.") from exc
    months = data.get("review_months")
    if not isinstance(months, int) or isinstance(months, bool) or months < 1:
        raise MthError(f"{name}: «review_months» debe ser un entero positivo.")
    controls, seen = [], set()
    for position, row in enumerate(data.get("control", []), 1):
        where = f"{name}: control {position}"
        control = Control(_text(row, "id", where), _text(row, "title", where), _text(row, "level", where),
                          _text(row, "url", where), str(row.get("tool", "")), str(row.get("rule", "")))
        if control.level not in LEVELS:
            raise MthError(f"{where} ({control.id}): «level» debe ser {' o '.join(LEVELS)}.")
        if control.id in seen:
            raise MthError(f"{name}: el control {control.id} está repetido.")
        seen.add(control.id)
        controls.append(control)
    if not controls:
        raise MthError(f"{name}: el pack no tiene controles.")
    return Pack(_text(data, "id", name), _text(data, "title", name), _text(data, "version", name), reviewed, months,
                _text(source, "name", name), _text(source, "version", name), _text(source, "url", name),
                tuple(controls), hashlib.sha256(raw).hexdigest())


def load_packs(directory: Path = PACKS_DIR) -> dict[str, Pack]:
    """Every pack of ``directory`` by id; the first invalid one raises."""
    packs: dict[str, Pack] = {}
    for path in sorted(directory.glob("*.toml")):
        pack = parse_pack(path.read_bytes(), path.name)
        if pack.id in packs:
            raise MthError(f"{path.name}: el pack {pack.id} está repetido.")
        packs[pack.id] = pack
    return packs


def verify_report(text: str, packs: dict[str, Pack]) -> list[str]:
    """Problems of an audit report against its baseline pack (ADR-0024, decision 4); empty means valid."""
    header = _BASELINE.search(text)
    if header is None:
        return ["falta la línea «Línea base: <pack>@<versión> sha256=<hash>»"]
    pack = packs.get(header.group(1))
    if pack is None:
        return [f"la línea base cita el pack {header.group(1)}, que no existe"]
    problems = []
    if header.group(2) != pack.version or header.group(3) != pack.sha256:
        problems.append(f"la línea base no coincide con {pack.id}@{pack.version} sha256={pack.sha256}")
    known = {c.id: c for c in pack.controls}
    results: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if _CERTIFIES.search(line):
            problems.append(f"línea {number}: un informe no certifica cumplimiento")
        if not (row := _ROW.match(line)) or line.lstrip().startswith("- Línea base"):
            continue
        ident, result, evidence = row.groups()
        if ident not in known:
            problems.append(f"línea {number}: el control {ident} no existe en {pack.id}")
        elif result not in RESULTS:
            problems.append(f"línea {number}: {ident} tiene el resultado «{result}» (válidos: {', '.join(RESULTS)})")
        elif result in _DECIDED and not evidence:
            problems.append(f"línea {number}: {ident} es «{result}» y no lleva evidencia")
        else:
            results[ident] = result
    problems += [f"el control mínimo {c.id} no tiene resultado" for c in pack.controls if c.level == "minimo" and c.id not in results]
    return problems
