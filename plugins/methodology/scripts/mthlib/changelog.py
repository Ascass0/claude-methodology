"""Changelog fragments (``changes/<kind>-<slug>.md``) and their aggregation.

Each top-level branch owns one fragment, so parallel branches never conflict.
A release folds every fragment into ``CHANGELOG.md`` (Keep a Changelog) and
deletes them. Fragment format::

    ---
    bump: minor
    refs: SPEC-0003, ADR-0007
    ---
    ### Añadido
    - Descripción del cambio orientada a quien usa el proyecto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .errors import MthError
from .ids import IdRegistry

SECTIONS = ("Añadido", "Cambiado", "Obsoleto", "Eliminado", "Corregido", "Seguridad")
BUMPS = ("patch", "minor", "major")
MARKER = "<!-- mth:releases -->"
DEFAULT_BUMP = {"feat": "minor", "fix": "patch", "hotfix": "patch"}
DEFAULT_SECTION = {"feat": "Añadido", "fix": "Corregido", "hotfix": "Corregido"}
_PLACEHOLDER = re.compile(r"<[^>\n]+>")
_FRONT = re.compile(r"^---\n(?P<meta>.*?)\n---\n(?P<body>.*)$", re.DOTALL)


@dataclass
class Fragment:
    path: Path
    bump: str
    refs: list[str]
    sections: dict[str, list[str]] = field(default_factory=dict)


def template(kind: str, refs: list[str]) -> str:
    bump = DEFAULT_BUMP.get(kind, "patch")
    section = DEFAULT_SECTION.get(kind, "Cambiado")
    return (f"---\nbump: {bump}\nrefs: {', '.join(refs)}\n---\n"
            f"### {section}\n- <describe el cambio para quien usa el proyecto>\n")


def parse(path: Path) -> Fragment:
    """Parse a fragment file.

    Raises:
        MthError: Missing file or malformed content.
    """
    if not path.is_file():
        raise MthError(f"Falta el fragmento de changelog {path.name}.",
                       hint="Se crea al iniciar la rama; recréalo con `mth changes new`.")
    m = _FRONT.match(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
    if not m:
        raise MthError(f"{path.name}: falta la cabecera '---' con bump y refs.")
    meta = dict(line.split(":", 1) for line in m.group("meta").splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    frag = Fragment(path=path, bump=meta.get("bump", ""),
                    refs=[r.strip() for r in meta.get("refs", "").split(",") if r.strip()])
    current = None
    for raw in m.group("body").splitlines():
        if raw.startswith("### "):
            current = raw[4:].strip()
            frag.sections.setdefault(current, [])
        elif raw.startswith("- "):
            if current is None:
                raise MthError(f"{path.name}: hay una viñeta fuera de una sección '### '.")
            frag.sections[current].append(raw[2:].strip())
        elif raw.startswith("  ") and current and frag.sections[current]:
            frag.sections[current][-1] += " " + raw.strip()
        elif raw.strip():
            raise MthError(f"{path.name}: línea no reconocida: '{raw}'.",
                           hint="Usa solo encabezados '### <sección>' y viñetas '- '.")
    return frag


def validate(frag: Fragment, registry: IdRegistry, refs_required: bool) -> list[str]:
    """Content errors of a parsed fragment (empty list = valid)."""
    name, errors = frag.path.name, []
    if frag.bump not in BUMPS:
        errors.append(f"{name}: bump debe ser uno de {', '.join(BUMPS)}")
    if refs_required and not frag.refs:
        errors.append(f"{name}: refs vacío; referencia la spec o el ADR que motiva el cambio")
    for ref in frag.refs:
        if registry.kind_of(ref) is None or not registry.is_defined(ref):
            errors.append(f"{name}: la referencia {ref} no existe")
    if not frag.sections:
        errors.append(f"{name}: no tiene ninguna sección")
    for section, bullets in frag.sections.items():
        if section not in SECTIONS:
            errors.append(f"{name}: sección '{section}' no válida ({', '.join(SECTIONS)})")
        if not bullets:
            errors.append(f"{name}: la sección '{section}' está vacía")
        if any(_PLACEHOLDER.search(b) for b in bullets):
            errors.append(f"{name}: contiene texto de plantilla '<...>' sin completar")
    return errors


def load_all(directory: Path) -> list[Fragment]:
    return [parse(p) for p in sorted(directory.glob("*.md"))]


def next_version(current: tuple[int, int, int], bump: str) -> str:
    major, minor, patch = current
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def highest_bump(fragments: list[Fragment]) -> str:
    return max((f.bump for f in fragments), key=BUMPS.index)


def render(version: str, fragments: list[Fragment], today: date | None = None) -> str:
    """Release section in Keep a Changelog format."""
    lines = [f"## [{version}] - {(today or date.today()).isoformat()}"]
    for section in SECTIONS:
        bullets = [f"- {b}" + (f" ({', '.join(f.refs)})" if f.refs else "")
                   for f in fragments for b in f.sections.get(section, [])]
        if bullets:
            lines += ["", f"### {section}", *bullets]
    return "\n".join(lines) + "\n"


def insert(changelog: str, section: str) -> str:
    """Insert a release section right after the marker (newest first).

    Raises:
        MthError: The changelog lacks the marker.
    """
    if MARKER not in changelog:
        raise MthError(f"El CHANGELOG no contiene el marcador {MARKER}.",
                       hint="Añádelo donde deben empezar las versiones (mth init lo crea).")
    head, _, tail = changelog.partition(MARKER)
    tail = tail.lstrip("\n")
    out = f"{head}{MARKER}\n\n{section}" + (f"\n{tail}" if tail else "")
    return out.rstrip() + "\n"


def section_of(changelog: str, version: str) -> str:
    """Body of the ``version`` section (used as tag and release notes)."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
                  changelog, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""
