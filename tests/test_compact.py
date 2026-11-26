"""Tests of the compact document format (SPEC-0018, ADR-0014)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import compact, lang, trace  # noqa: E402
from mthlib.config import parse  # noqa: E402

EN_CONFIG = 'version = 1\n[commands]\ntest = ""\n[language]\ndocs = "en"\n'

SPEC = """
    # SPEC-0001 · A
    - Estado: aprobada
    - Formato: compacto
    ## Modos de fallo
    | ID | Causa | Respuesta | Cubierto por |
    |---|---|---|---|
    | FM-01 | x | y | AC-01 |
    ## Criterios de aceptación
    - **AC-01**: CUANDO pasa algo, el sistema DEBE responder.
    """


def findings(files: dict[str, str], config: str | None = None) -> str:
    root = Path(tempfile.mkdtemp())
    try:
        for rel, text in files.items():
            test_mth._write(root / rel, text)
        names = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
        cfg = parse(root, config) if config else test_mth._cfg(root)
        return "\n".join(str(f) for f in trace.check(cfg, names))
    finally:
        shutil.rmtree(root)


def ref(spec: str, mode: str) -> str:
    return f"{spec}/{mode}"  # built at runtime: the literal would be a dangling reference of this file


class TemplateTests(unittest.TestCase):
    def test_generated_documents_declare_the_format_and_pass_trace(self):
        # verifies: SPEC-0018/AC-01
        for vocab, config in ((lang.ES, None), (lang.EN, EN_CONFIG)):
            files = {}
            for name, path, header in (("spec.md", "specs/features/SPEC-0001-a.md", "SPEC-0001"),
                                       ("adr.md", "specs/adr/process/ADR-0001-a.md", "ADR-0001")):
                text = (vocab.templates / name).read_text(encoding="utf-8")
                text = text.replace("{{ID}}", header).replace("{{TITLE}}", "A").replace("{{DATE}}", "2026-01-01").replace("{{CATEGORY}}", "process")
                self.assertTrue(compact.is_compact(text, vocab), f"{vocab.code}/{name}")
                files[path] = text
            with self.subTest(language=vocab.code):
                self.assertEqual(findings(files, config), "")


class OptInTests(unittest.TestCase):
    def test_documents_without_the_marker_are_not_validated(self):
        # verifies: SPEC-0018/AC-02
        # verifies: SPEC-0018/AC-10
        legacy = SPEC.replace("- Formato: compacto\n", "").replace("CUANDO pasa algo, el sistema DEBE responder", "responde")
        legacy += "\n    | FM-01 | repetido | z | AC-01 |\n    | sin id | x | y | z |\n"
        adr = "# ADR-0001 · X\n- Estado: aceptado\n## Alternativas consideradas\n"
        self.assertEqual(findings({"specs/features/SPEC-0001-a.md": legacy, "specs/adr/p/ADR-0001-x.md": adr}), "")
        self.assertEqual(findings({"specs/features/SPEC-0001-a.md": SPEC}), "")


class EarsTests(unittest.TestCase):
    def test_patterns_in_both_languages(self):
        # verifies: SPEC-0018/AC-03
        # verifies: SPEC-0018/AC-07
        valid = [
            (lang.ES, ["CUANDO llega x, el sistema DEBE y.", "SI falla, ENTONCES el sistema NO DEBE z.",
                      "MIENTRAS dure, el sistema DEBE y.", "Las claves DEBEN salir de lang.py.", "`mth` NO DEBE escribir."]),
            (lang.EN, ["WHEN x arrives, the system SHALL y.", "IF it fails, THEN the system MUST NOT z.",
                      "WHILE it lasts, the system SHALL y.", "Keys SHALL come from lang.py."]),
        ]
        for vocab, criteria in valid:
            for text in criteria:
                with self.subTest(text=text):
                    self.assertIsNone(compact.ears_problem(text, vocab))
        invalid = [(lang.ES, "responde bien"), (lang.ES, "CUANDO llega x el sistema DEBE y"), (lang.ES, "SI falla, el sistema DEBE y"),
                   (lang.ES, "MIENTRAS dure el sistema responde"), (lang.ES, "WHEN x, the system SHALL y"),
                   (lang.EN, "CUANDO x, el sistema DEBE y"), (lang.EN, "IF it fails the system SHALL y")]
        for vocab, text in invalid:
            with self.subTest(vocab=vocab.code, text=text):
                self.assertIn("EARS", compact.ears_problem(text, vocab) or "")

    def test_trace_reports_the_criterion_with_its_line(self):
        # verifies: SPEC-0018/AC-03
        text = SPEC.replace("CUANDO pasa algo, el sistema DEBE responder.", "responde bien.")
        found = findings({"specs/features/SPEC-0001-a.md": text})
        self.assertRegex(found, r"SPEC-0001-a\.md:\d+: AC-01 no sigue ningún patrón EARS")
        # DEBE on another line is rejected: one rule per line
        split = SPEC.replace("CUANDO pasa algo, el sistema DEBE responder.", "CUANDO pasa algo, el sistema\n    DEBE responder.")
        self.assertIn("AC-01 no sigue", findings({"specs/features/SPEC-0001-a.md": split}))

    def test_english_document_uses_english_keywords(self):
        # verifies: SPEC-0018/AC-07
        en = SPEC.replace("Estado: aprobada", "Status: approved").replace("Formato: compacto", "Format: compact").replace(
            "Modos de fallo", "Failure modes")
        self.assertIn("AC-01 no sigue", findings({"specs/features/SPEC-0001-a.md": en}, EN_CONFIG))
        ok = en.replace("CUANDO pasa algo, el sistema DEBE responder.", "WHEN it happens, the system SHALL answer.")
        self.assertEqual(findings({"specs/features/SPEC-0001-a.md": ok}, EN_CONFIG), "")
        # a Spanish marker is not the English one: the document is not validated as compact
        self.assertFalse(compact.is_compact(SPEC, lang.EN))


class AdrFieldTests(unittest.TestCase):
    def test_every_missing_field_is_reported(self):
        # verifies: SPEC-0018/AC-04
        adr = "# ADR-0001 · X\n- Estado: aceptado\n- Formato: compacto\n## Contexto\n## Decisión\n"
        found = findings({"specs/adr/p/ADR-0001-x.md": adr})
        for field in ("Rechazado", "Consecuencias", "Impone"):
            self.assertIn(f"falta el campo «{field}»", found)
        self.assertNotIn("«Contexto»", found)
        full = adr + "## Rechazado\n## Consecuencias\n## Impone\n"
        self.assertEqual(findings({"specs/adr/p/ADR-0001-x.md": full}), "")


    def test_missing_fields_are_reported_in_english(self):
        # verifies: SPEC-0018/AC-04
        adr = "# ADR-0001 · X\n- Status: accepted\n- Format: compact\n"
        found = findings({"specs/adr/p/ADR-0001-x.md": adr}, EN_CONFIG)
        for field in ("Context", "Decision", "Rejected", "Consequences", "Imposes"):
            self.assertIn(f"falta el campo «{field}»", found)


class FailureModeTests(unittest.TestCase):
    def test_duplicate_and_untagged_rows(self):
        # verifies: SPEC-0018/AC-05
        text = SPEC.replace("| FM-01 | x | y | AC-01 |", "| FM-01 | x | y | AC-01 |\n    | FM-01 | otra | y | AC-01 |\n    | libre | x | y | AC-01 |")
        found = findings({"specs/features/SPEC-0001-a.md": text})
        self.assertRegex(found, r":\d+: FM-01 definido dos veces")
        self.assertRegex(found, r":\d+: fila de modos de fallo sin ID FM-NN: «libre»")

    def test_dangling_references(self):
        # verifies: SPEC-0018/AC-06
        local = SPEC + "\n    Ver FM-09 y FM-01.\n"
        self.assertIn("referencia a FM-09, que la spec no define", findings({"specs/features/SPEC-0001-a.md": local}))
        self.assertNotIn("FM-01, que", findings({"specs/features/SPEC-0001-a.md": local}))
        other = "# Guía\n" + ref("SPEC-0001", "FM-01") + " existe; " + ref("SPEC-0001", "FM-07") + " no; " + ref("SPEC-0001", "FM-01x") + "\n"
        found = findings({"specs/features/SPEC-0001-a.md": SPEC, "docs/guia.md": other})
        self.assertIn(f"referencia a {ref('SPEC-0001', 'FM-07')}, que la spec no define", found)
        self.assertNotIn(f"{ref('SPEC-0001', 'FM-01')}, que", found)
        # a qualified reference is not read as a bare one of the document that quotes it
        quoted = SPEC + "\n    Como en " + ref("SPEC-0002", "FM-05") + ".\n"
        self.assertNotIn("referencia a FM-05", findings({"specs/features/SPEC-0001-a.md": quoted, "specs/features/SPEC-0002-b.md": SPEC.replace("0001", "0002").replace("FM-01", "FM-05")}))

    def test_reference_to_a_missing_spec_is_reported_once(self):
        # verifies: SPEC-0018/AC-06
        missing = "SPEC-00" + "99"
        found = findings({"docs/guia.md": "Ver " + ref(missing, "FM-01") + "\n"})
        self.assertEqual(found.count(missing), 1)  # by the ID check; no second finding for the mode


if __name__ == "__main__":
    unittest.main()
