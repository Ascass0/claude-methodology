"""Tests of legacy mode in traceability (SPEC-0005)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
BROKEN = "# Guía\n\n[roto](nada.md)\n"


class LegacyConfigTests(unittest.TestCase):
    def test_legacy_base_must_be_a_full_hash(self):
        # verifies: SPEC-0005/AC-02
        for value in ("HEAD", "abc1234", "g" * 40, "A" * 40):
            with self.subTest(value=value), self.assertRaises(MthError) as ctx:
                parse(Path("."), CONFIG + f'[trace]\nlegacy_base = "{value}"\n')
            self.assertIn("hash completo de un commit", ctx.exception.message)
        self.assertEqual(parse(Path("."), CONFIG)["trace"]["legacy_base"], "")


class LegacyTraceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.git("init", "-q", "-b", "main")
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        test_mth._write(self.root / "docs/old.md", BROKEN)
        test_mth._write(self.root / "docs/touched.md", BROKEN)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "before adoption")
        self.base = self.git("rev-parse", "HEAD")

    def tearDown(self):
        shutil.rmtree(self.root)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env={**os.environ, **test_mth.GIT_ENV},
                              check=True, capture_output=True, text=True).stdout.strip()

    def trace(self, *args, legacy_base=None):
        body = CONFIG + (f'[trace]\nlegacy_base = "{legacy_base}"\n' if legacy_base else "")
        (self.root / ".claude/methodology.toml").write_text(body, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(test_mth.MTH), "trace", *args], cwd=self.root,
                              capture_output=True, text=True, env={**os.environ, **test_mth.GIT_ENV})
        return proc.returncode, proc.stdout + proc.stderr

    def test_without_legacy_base_every_finding_is_an_error(self):
        # verifies: SPEC-0005/AC-01
        code, out = self.trace()
        self.assertEqual(code, 1)
        self.assertIn("✗ docs/old.md:3: enlace roto: nada.md", out)

    def test_unchanged_files_are_warnings_and_touched_or_new_ones_errors(self):
        # verifies: SPEC-0005/AC-03
        # verifies: SPEC-0005/AC-04
        code, out = self.trace(legacy_base=self.base)
        self.assertEqual(code, 0, out)
        self.assertIn(f"⚠ 2 hallazgos en contenido legado (anterior a {self.base[:7]})", out)
        (self.root / "docs/touched.md").write_text(BROKEN + "\nUna línea más.\n", encoding="utf-8")
        test_mth._write(self.root / "docs/new.md", BROKEN)
        code, out = self.trace(legacy_base=self.base)
        self.assertEqual(code, 1)
        self.assertIn("✗ docs/touched.md:3: enlace roto", out)
        self.assertIn("✗ docs/new.md:3: enlace roto", out)
        self.assertNotIn("✗ docs/old.md", out)
        self.assertIn("⚠ 1 hallazgos en contenido legado", out)

    def test_legacy_listing(self):
        # verifies: SPEC-0005/AC-05
        _, out = self.trace(legacy_base=self.base)
        self.assertNotIn("⚠ docs/old.md:3", out)
        _, out = self.trace("--legacy", legacy_base=self.base)
        self.assertIn("⚠ docs/old.md:3: enlace roto: nada.md", out)
        self.assertIn("⚠ docs/touched.md:3: enlace roto: nada.md", out)

    def test_unknown_legacy_commit_fails(self):
        # verifies: SPEC-0005/AC-06
        missing = "0" * 40
        code, out = self.trace(legacy_base=missing)
        self.assertEqual(code, 1)
        self.assertIn(f"No existe el commit {missing} de trace.legacy_base", out)


if __name__ == "__main__":
    unittest.main()
