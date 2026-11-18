"""Tests of the configurable documentation language (SPEC-0008)."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402  (module import: its test classes are not collected twice)
from mthlib import changelog, lang, plan, trace  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.ids import IdRegistry  # noqa: E402

BASE_CONFIG = 'version = 1\n[commands]\ntest = ""\n'
EN_CONFIG = BASE_CONFIG + '[language]\ndocs = "en"\n'


def _fragment(root: Path, section: str) -> changelog.Fragment:
    path = root / "feat-x.md"
    path.write_text(f"---\nbump: minor\nrefs:\n---\n### {section}\n- Thing.\n", encoding="utf-8")
    return changelog.parse(path)


class LanguageConfigTests(unittest.TestCase):
    def test_default_is_spanish(self):
        # verifies: SPEC-0008/AC-01
        cfg = parse(Path("."), BASE_CONFIG)
        self.assertIs(cfg.vocab, lang.ES)
        self.assertEqual(changelog.template("feat", []).splitlines()[-2:],
                         ["### Añadido", "- <describe el cambio para quien usa el proyecto>"])

    def test_unknown_language_fails_fast(self):
        # verifies: SPEC-0008/AC-02
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), BASE_CONFIG + '[language]\ndocs = "fr"\n')
        self.assertIn("'language.docs' = 'fr' no es un idioma admitido (es, en)", ctx.exception.message)

    def test_templates_have_the_same_structure(self):
        for name in ("spec.md", "adr.md", "CHANGELOG.md", "claude-block.md"):
            with self.subTest(template=name):
                es = (lang.ES.templates / name).read_text(encoding="utf-8")
                en = (lang.EN.templates / name).read_text(encoding="utf-8")
                for pattern in (r"^#+ ", r"\{\{[A-Z]+\}\}", r"<!-- [a-z:-]+ -->", r"\*\*AC-\d+\*\*"):
                    self.assertEqual(len(re.findall(pattern, es, re.M)), len(re.findall(pattern, en, re.M)), pattern)


class EnglishKeywordTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.registry = IdRegistry(parse(self.root, BASE_CONFIG), [])

    def test_changelog_sections_follow_the_language(self):
        # verifies: SPEC-0008/AC-04
        added = _fragment(self.root, "Added")
        self.assertEqual(changelog.validate(added, self.registry, False, lang.EN), [])
        self.assertIn("sección 'Añadido' no válida (Added, Changed, Deprecated, Removed, Fixed, Security)",
                      changelog.validate(_fragment(self.root, "Añadido"), self.registry, False, lang.EN)[0])
        self.assertIn("sección 'Added' no válida", changelog.validate(added, self.registry, False, lang.ES)[0])
        self.assertIn("### Added\n- Thing.", changelog.render("1.0.0", [added], vocab=lang.EN))

    def test_implemented_status_requires_tests(self):
        # verifies: SPEC-0008/AC-05
        test_mth._write(self.root / "specs/features/SPEC-0001-a.md",
                        "# SPEC-0001 · A\n- Status: implemented\n## Acceptance criteria\n- **AC-01**: one\n")
        files = ["specs/features/SPEC-0001-a.md"]
        en = parse(self.root, EN_CONFIG)
        es = parse(self.root, BASE_CONFIG)
        self.assertIn("SPEC-0001/AC-01 no tiene ningún test", "\n".join(map(str, trace.check(en, files))))
        self.assertNotIn("AC-01 no tiene ningún test", "\n".join(map(str, trace.check(es, files))))

    def test_work_plan_in_english(self):
        # verifies: SPEC-0008/AC-06
        text = ("# SPEC-0001 · A\n## Acceptance criteria\n- **AC-01**: one\n## Work plan\n\n"
                "| Task | Wave | Files | Criteria | Model |\n|---|---|---|---|---|\n| T-01 | 1 | `a.py` | AC-01 | haiku |\n")
        tasks, problems = plan.check(text, vocab=lang.EN)
        self.assertEqual(([t.id for t in tasks], problems), (["T-01"], []))
        self.assertFalse(plan.has_plan(text, lang.ES))
        spanish_header = text.replace("| Task | Wave | Files | Criteria | Model |", "| Tarea | Oleada | Ficheros | Criterios |")
        self.assertIn("cabecera inválida: debe ser | Task | Wave | Files | Criteria |",
                      plan.check(spanish_header, vocab=lang.EN)[1][0].message)


class EnglishRepoFlowTests(unittest.TestCase):
    """mth init, doc, branch and session in an English repo, with the harness of test_mth.EndToEndTests."""

    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def adopt_in_english(self) -> None:
        template = (lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
        config = self.tmp / "methodology.toml"
        config.write_text(template.replace('test = ""', 'test = "true"').replace('docs = "es"', 'docs = "en"'),
                          encoding="utf-8")
        self.mth("init", "--config", str(config))

    def test_init_and_branch_write_english_files(self):
        # verifies: SPEC-0008/AC-08
        self.adopt_in_english()
        self.assertIn("All notable changes to this project", (self.work / "CHANGELOG.md").read_text())
        self.assertIn("## Methodology", (self.work / "CLAUDE.md").read_text())
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adoption.")
        self.mth("branch", "feat", "runner")
        self.assertIn("### Added\n- <describe the change for the project's users>",
                      (self.work / "changes/feat-runner.md").read_text())

    def test_docs_and_session_follow_the_language(self):
        # verifies: SPEC-0008/AC-03
        # verifies: SPEC-0008/AC-07
        self.adopt_in_english()
        self.mth("doc", "spec", "--title", "Runner")
        self.mth("doc", "adr", "--title", "Runner", "--category", "arch")
        self.assertIn("- Status: draft", (self.work / "specs/features/SPEC-0001-runner.md").read_text())
        self.assertIn("- Status: proposed", (self.work / "specs/adr/arch/ADR-0001-runner.md").read_text())
        out = subprocess.run([sys.executable, str(test_mth.MTH), "session"], cwd=self.work, env=self.env,
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("docs, specs, changelog y PR en inglés", out)


if __name__ == "__main__":
    unittest.main()
