"""Tests of the version files rewritten on release (SPEC-0003)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402  (module import: its test classes are not collected twice)
from mthlib import versions  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

BASE_CONFIG = 'version = 1\n[commands]\ntest = ""\n'
PACKAGE = '{\n  "name": "demo",\n  "version": "0.0.0",\n  "deps": {"x": "1.2.3"}\n}\n'
ENTRY = '[[release.version_files]]\npath = "package.json"\npattern = \'"version": "(\\d+\\.\\d+\\.\\d+)"\'\n'


def _config(body: str) -> str:
    return BASE_CONFIG + body


class VersionFileConfigTests(unittest.TestCase):
    def test_default_is_empty(self):
        # verifies: SPEC-0003/AC-01
        self.assertEqual(parse(Path("."), BASE_CONFIG)["release"]["version_files"], [])

    def test_invalid_entries_fail_fast(self):
        # verifies: SPEC-0003/AC-02
        cases = {
            "exactamente 'path' y 'pattern'": '[[release.version_files]]\npath = "a.json"\n',
            "exactamente 'path' y 'pattern' ": '[[release.version_files]]\npattern = "(x)"\n',
            "exactamente 'path' y 'pattern'  ": '[[release.version_files]]\npath = "a"\npattern = "(x)"\nflag = 1\n',
            "ruta relativa normalizada": '[[release.version_files]]\npath = "/etc/a"\npattern = "(x)"\n',
            "ruta relativa normalizada ": '[[release.version_files]]\npath = "../a"\npattern = "(x)"\n',
            "no es una expresión regular válida": '[[release.version_files]]\npath = "a"\npattern = "(x"\n',
            "exactamente un grupo de captura (tiene 0)": '[[release.version_files]]\npath = "a"\npattern = "x"\n',
            "exactamente un grupo de captura (tiene 2)": '[[release.version_files]]\npath = "a"\npattern = "(x)(y)"\n',
            "está repetida": ENTRY + ENTRY,
        }
        for expected, body in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(MthError) as ctx:
                    parse(Path("."), _config(body))
                self.assertIn(expected.strip(), ctx.exception.message)


class VersionFileWriteTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "package.json").write_text(PACKAGE, encoding="utf-8")
        self.items = versions.from_config(parse(self.root, _config(ENTRY))["release"]["version_files"])

    def test_replaces_only_the_capture(self):
        # verifies: SPEC-0003/AC-03
        self.assertEqual(versions.write(self.root, self.items, "1.4.0"), ["package.json"])
        self.assertEqual((self.root / "package.json").read_text(encoding="utf-8"),
                         PACKAGE.replace('"0.0.0"', '"1.4.0"'))
        self.assertEqual(versions.write(self.root, self.items, "1.4.0"), [])  # resumed release: no change

    def test_broken_entry_leaves_every_file_untouched(self):
        # verifies: SPEC-0003/AC-05
        items = self.items + versions.from_config([{"path": "missing.toml", "pattern": "v(.+)"}])
        with self.assertRaises(MthError) as ctx:
            versions.write(self.root, items, "1.4.0")
        self.assertIn("No existe el fichero de versión missing.toml", ctx.exception.message)
        self.assertEqual((self.root / "package.json").read_text(encoding="utf-8"), PACKAGE)

    def test_pattern_must_match_once(self):
        # verifies: SPEC-0003/AC-05
        (self.root / "package.json").write_text(PACKAGE + PACKAGE, encoding="utf-8")
        with self.assertRaises(MthError) as ctx:
            versions.read(self.root, self.items[0])
        self.assertIn("aparece 2 veces", ctx.exception.message)


class VersionFileFlowTests(unittest.TestCase):
    """End to end against a local remote, with the harness of test_mth.EndToEndTests."""

    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth
    report = test_mth.EndToEndTests.report

    def adopt(self, entry: str = ENTRY) -> None:
        self.mth("init")
        cfg_path = self.work / ".claude/methodology.toml"
        cfg_path.write_text(cfg_path.read_text().replace('test = ""', 'test = "true"') + "\n" + entry)
        (self.work / "package.json").write_text(PACKAGE, encoding="utf-8")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Test command and version file.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")

    def add_fragment(self) -> None:
        self.mth("branch", "chore", "notes")
        test_mth._write(self.work / "changes/chore-notes.md",
                        "---\nbump: minor\nrefs:\n---\n### Añadido\n- Notas.\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add a changelog fragment", "--body", "Notes.",
                 "--refs", "n/a")
        self.mth("integrate", "--title", "chore: add a changelog fragment", "--summary", "Notas.")

    def test_release_and_hotfix_update_version_files(self):
        # verifies: SPEC-0003/AC-01
        # verifies: SPEC-0003/AC-03
        # verifies: SPEC-0003/AC-04
        # verifies: SPEC-0003/AC-06
        self.adopt()
        self.assertIn("✓ Fichero de versión package.json: 0.0.0", self.mth("doctor"))  # no tag yet: 0.0.0
        self.add_fragment()
        self.mth("release")
        self.git("fetch", "-q", "--tags")
        self.assertEqual(self.git("show", "origin/main:package.json") + "\n", PACKAGE.replace('"0.0.0"', '"0.1.0"'))
        release_commit = self.git("log", "--format=%B", "-1", "origin/main^2")
        self.assertIn("chore(release): v0.1.0", release_commit)
        self.assertIn("Set version 0.1.0 in package.json.", release_commit)
        self.assertIn("✓ Fichero de versión package.json: 0.1.0", self.mth("doctor"))

        self.mth("branch", "hotfix", "leak")
        self.mth("doc", "spec", "--title", "Leak")
        frag = self.work / "changes/hotfix-leak.md"
        frag.write_text(frag.read_text().replace("<describe el cambio para quien usa el proyecto>", "Fuga."))
        self.git("add", "-A")
        self.mth("commit", "--type", "fix", "--summary", "close leaked handle", "--body", "Close on exit.",
                 "--refs", "SPEC-0001")
        self.mth("review", "record", "verificador", "--report", self.report(), "--summary", "OK.")
        self.mth("hotfix", "finish")
        self.assertEqual(self.git("show", "origin/main:package.json") + "\n", PACKAGE.replace('"0.0.0"', '"0.1.1"'))

        (self.work / "package.json").write_text(PACKAGE.replace('"0.0.0"', '"9.9.9"'), encoding="utf-8")
        self.assertIn("⚠ Fichero de versión package.json: 9.9.9 (última etiqueta: 0.1.1)", self.mth("doctor"))
        (self.work / "package.json").write_text("{}\n", encoding="utf-8")
        self.assertIn("✗ Fichero de versión: El patrón de versión de package.json aparece 0 veces",
                      self.mth("doctor", ok=False))

    def test_release_refuses_a_missing_version_file(self):
        # verifies: SPEC-0003/AC-05
        self.adopt(ENTRY + '[[release.version_files]]\npath = "VERSION"\npattern = "(.+)"\n')
        self.add_fragment()
        out = self.mth("release", ok=False)
        self.assertIn("No existe el fichero de versión VERSION", out)
        self.assertEqual(self.git("branch", "--list", "release/*"), "")
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "release/*"), "")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.work / "package.json").read_text(encoding="utf-8"), PACKAGE)


if __name__ == "__main__":
    unittest.main()
