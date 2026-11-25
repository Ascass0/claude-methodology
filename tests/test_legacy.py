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

    def test_a_lowercase_full_hash_is_accepted(self):
        # verifies: SPEC-0005/AC-02
        value = "0123456789abcdef" * 2 + "01234567"
        self.assertEqual(parse(Path("."), CONFIG + f'[trace]\nlegacy_base = "{value}"\n')["trace"]["legacy_base"], value)


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

    def test_without_legacy_base_a_dangling_reference_is_an_error_too(self):
        # verifies: SPEC-0005/AC-01
        missing = "SPEC-" + "9999"
        test_mth._write(self.root / "docs/old.md", f"# Guía\n\nVer {missing}.\n")
        self.git("commit", "-q", "-a", "-m", "dangling reference")
        code, out = self.trace()
        self.assertEqual(code, 1)
        self.assertIn(f"✗ docs/old.md:3: referencia a {missing}, que no está definido", out)

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

    def test_a_file_changed_in_a_later_commit_is_an_error(self):
        # verifies: SPEC-0005/AC-04
        (self.root / "docs/touched.md").write_text(BROKEN + "\nUna línea más.\n", encoding="utf-8")
        self.git("commit", "-q", "-a", "-m", "touch after the base")
        code, out = self.trace(legacy_base=self.base)
        self.assertEqual(code, 1)
        self.assertIn("✗ docs/touched.md:3: enlace roto", out)
        self.assertNotIn("✗ docs/old.md", out)

    def test_legacy_listing(self):
        # verifies: SPEC-0005/AC-05
        _, out = self.trace(legacy_base=self.base)
        self.assertNotIn("⚠ docs/old.md:3", out)
        _, out = self.trace("--legacy", legacy_base=self.base)
        self.assertIn("⚠ docs/old.md:3: enlace roto: nada.md", out)
        self.assertIn("⚠ docs/touched.md:3: enlace roto: nada.md", out)

    def test_legacy_listing_leaves_out_errors(self):
        # verifies: SPEC-0005/AC-05
        test_mth._write(self.root / "docs/new.md", BROKEN)
        _, out = self.trace("--legacy", legacy_base=self.base)
        self.assertIn("⚠ docs/old.md:3: enlace roto: nada.md", out)
        self.assertNotIn("⚠ docs/new.md", out)
        self.assertIn("✗ docs/new.md:3: enlace roto", out)

    def test_gates_ignore_legacy_findings_and_refuse_an_unknown_base(self):
        # verifies: SPEC-0005/AC-03
        # verifies: SPEC-0005/AC-06
        from mthlib import flow
        from mthlib.config import load
        from mthlib.git import Git
        from mthlib.log import Tracer

        def gate(legacy_base: str) -> None:
            self.trace(legacy_base=legacy_base)  # writes the configuration
            git = Git.discover(self.root)
            flow._gate_trace(flow.Ctx(cfg=load(self.root), git=git, tracer=Tracer(git.git_dir(), "test")))
        gate(self.base)  # only legacy findings: the gate passes
        with self.assertRaises(MthError) as ctx:
            gate("0" * 40)
        self.assertIn("No existe el commit", ctx.exception.message)
        test_mth._write(self.root / "docs/new.md", BROKEN)
        with self.assertRaises(MthError) as ctx:
            gate(self.base)
        self.assertIn("Trazabilidad rota (1 hallazgos)", ctx.exception.message)

    def test_unknown_legacy_commit_fails(self):
        # verifies: SPEC-0005/AC-06
        missing = "0" * 40
        code, out = self.trace(legacy_base=missing)
        self.assertEqual(code, 1)
        self.assertIn(f"No existe el commit {missing} de trace.legacy_base", out)


if __name__ == "__main__":
    unittest.main()
