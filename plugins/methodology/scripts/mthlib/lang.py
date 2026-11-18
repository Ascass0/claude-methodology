"""Keywords and templates of each documentation language (SPEC-0008, ADR-0005).

`mth` recognises only the keywords of the configured language, so a document
cannot mix languages unnoticed. Code and commits are always in English.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


@dataclass(frozen=True)
class Vocabulary:
    code: str
    name: str  # in Spanish, for the session rules
    status_label: str
    implemented: str
    plan_section: str
    plan_columns: tuple[str, str, str, str]
    model_column: str
    changelog_sections: tuple[str, ...]  # Keep a Changelog order
    default_section: dict[str, str]
    fallback_section: str
    fragment_placeholder: str
    templates: Path


ES = Vocabulary(
    code="es", name="español", status_label="Estado", implemented="implementada",
    plan_section="Plan de trabajo", plan_columns=("Tarea", "Oleada", "Ficheros", "Criterios"),
    model_column="Modelo",
    changelog_sections=("Añadido", "Cambiado", "Obsoleto", "Eliminado", "Corregido", "Seguridad"),
    default_section={"feat": "Añadido", "fix": "Corregido", "hotfix": "Corregido", "security": "Seguridad"},
    fallback_section="Cambiado", fragment_placeholder="<describe el cambio para quien usa el proyecto>",
    templates=TEMPLATES,
)

EN = Vocabulary(
    code="en", name="inglés", status_label="Status", implemented="implemented",
    plan_section="Work plan", plan_columns=("Task", "Wave", "Files", "Criteria"),
    model_column="Model",
    changelog_sections=("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"),
    default_section={"feat": "Added", "fix": "Fixed", "hotfix": "Fixed", "security": "Security"},
    fallback_section="Changed", fragment_placeholder="<describe the change for the project's users>",
    templates=TEMPLATES / "en",
)

LANGUAGES: dict[str, Vocabulary] = {v.code: v for v in (ES, EN)}


def vocabulary(code: str) -> Vocabulary:
    """Vocabulary of a validated ``language.docs`` value."""
    return LANGUAGES[code]
