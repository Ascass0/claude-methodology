"""Security surface header and [SEG] criteria in specs (SPEC-0026)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import compact, lang  # noqa: E402
from test_compact import EN_CONFIG, SPEC, findings  # noqa: E402

PATH = "specs/features/SPEC-0001-a.md"
TAGGED = "\n    - **AC-02** [SEG]: SI la entrada no es válida, ENTONCES el sistema DEBE rechazarla."


def spec(header: str, extra: str = "") -> str:
    text = SPEC.replace("- Formato: compacto\n", f"- Formato: compacto\n    {header}\n" if header else "- Formato: compacto\n")
    return text + extra


class SecurityHeaderTests(unittest.TestCase):
    def test_none_needs_no_security_criteria(self):
        # verifies: SPEC-0026/AC-01
        self.assertEqual(findings({PATH: spec("- Seguridad: ninguna")}), "")

    def test_a_declared_surface_without_a_tagged_criterion_is_an_error_on_the_header_line(self):
        # verifies: SPEC-0026/AC-02
        # verifies: SPEC-0026/FM-01
        out = findings({PATH: spec("- Seguridad: entrada externa, autenticación")})
        self.assertIn(f"{PATH}:4:", out)
        self.assertIn("[SEG]", out)
        self.assertEqual(findings({PATH: spec("- Seguridad: entrada externa", TAGGED)}), "")

    def test_an_empty_header_counts_as_a_declared_surface(self):
        # verifies: SPEC-0026/AC-03
        # verifies: SPEC-0026/FM-02
        self.assertIn("[SEG]", findings({PATH: spec("- Seguridad:")}))

    def test_only_valid_ears_ac_lines_count_as_security_criteria(self):
        # verifies: SPEC-0026/AC-04
        # verifies: SPEC-0026/FM-03
        header = "- Seguridad: datos sensibles"
        prose = "\n    Nota: [SEG] aquí no hay criterio."
        self.assertIn("[SEG]", findings({PATH: spec(header, prose)}))
        broken = findings({PATH: spec(header, "\n    - **AC-02** [SEG]: rechaza todo.")})
        self.assertIn("AC-02 no sigue ningún patrón EARS", broken)
        self.assertIn("[SEG]", broken)

    def test_a_tagged_line_inside_a_code_fence_is_not_a_criterion(self):
        # verifies: SPEC-0026/AC-04
        fenced = "\n    ```\n    - **AC-02** [SEG]: SI la entrada no es válida, ENTONCES el sistema DEBE rechazarla.\n    ```"
        self.assertIn("[SEG]", findings({PATH: spec("- Seguridad: entrada externa", fenced)}))

    def test_english_vocabulary_requires_the_sec_tag(self):
        # verifies: SPEC-0026/AC-02
        en = (SPEC.replace("Estado", "Status").replace("Formato: compacto", "Format: compact\n    - Security: external input")
              .replace("Modos de fallo", "Failure modes").replace("Criterios de aceptación", "Acceptance criteria")
              .replace("CUANDO pasa algo, el sistema DEBE responder", "WHEN something happens, the system SHALL answer"))
        self.assertIn("[SEC]", findings({PATH: en}, EN_CONFIG))
        tagged = "\n    - **AC-02** [SEC]: IF the input is invalid, THEN the system SHALL reject it."
        self.assertEqual(findings({PATH: en + tagged}, EN_CONFIG), "")

    def test_a_body_bullet_named_like_the_header_is_not_a_declaration(self):
        # verifies: SPEC-0026/AC-05
        body = "\n    ## Notas\n    - Seguridad: entrada externa"
        self.assertEqual(findings({PATH: spec("- Seguridad: ninguna", body)}), "")

    def test_a_spec_without_the_header_is_not_checked(self):
        # verifies: SPEC-0026/AC-05
        self.assertEqual(findings({PATH: spec("")}), "")


class TemplateAndDocsTests(unittest.TestCase):
    def test_templates_declare_none_in_each_language(self):
        # verifies: SPEC-0026/AC-06
        for vocab in (lang.ES, lang.EN):
            text = (vocab.templates / "spec.md").read_text(encoding="utf-8")
            self.assertIn(f"- {vocab.security_label}: {vocab.security_none}", text)
            self.assertEqual(compact.security_problems(text, vocab), [])

    def test_skill_and_reviewer_document_the_header_and_the_tag(self):
        # verifies: SPEC-0026/AC-07
        plugin = HERE.parent / "plugins" / "methodology"
        for rel in ("skills/mth-spec/SKILL.md", "catalog/revisor-seguridad/agent.md.tmpl"):
            text = (plugin / rel).read_text(encoding="utf-8")
            self.assertIn("- Seguridad:", text, rel)
            self.assertIn("[SEG]", text, rel)


if __name__ == "__main__":
    unittest.main()
