"""Tests of plugin upgrades against newer or older configurations (SPEC-0009)."""
from __future__ import annotations

import contextlib
import io
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
from mthlib import __version__, setup  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
# Every table a 0.5.x configuration could declare, without the keys added in 0.6.0.
CONFIG_05 = 'version = 1\nremote = "origin"\n' + (
    '[commands]\ntest = ""\nprecommit = ""\n'
    '[paths]\ndocs = "docs"\n'
    '[branches]\nmain = "main"\ndevelopment = "development"\n'
    '[commits]\nrequire_refs = ["feat", "fix"]\n'
    '[review]\nagents = ["verificador"]\n'
    '[roles]\nverifier = "verificador"\n'
    '[ci]\nrequired = true\n'
    '[trace]\nlinks = true\n'
    '[release]\ngithub_release = true\ntag_prefix = "v"\n'
    '[models]\ntask = "sonnet"\n'
)


class UnknownKeyTests(unittest.TestCase):
    def test_error_names_the_plugin_version_and_how_to_upgrade(self):
        # verifies: SPEC-0009/AC-01
        for body, key in ((CONFIG + '[sandbox]\nimage = "x"\n', "'sandbox'"),
                          (CONFIG + '[release]\nnewer_option = true\n', "'release.newer_option'")):
            with self.subTest(key=key), self.assertRaises(MthError) as ctx:
                parse(Path("."), body)
            self.assertIn(f"Clave desconocida en la configuración: {key}", ctx.exception.message)
            self.assertIn(f"claude-methodology {__version__} no la reconoce", ctx.exception.message)
            self.assertIn("actualízalo con /plugin", ctx.exception.hint)
            self.assertIn("sesión nueva", ctx.exception.hint)

    def test_a_05_configuration_keeps_its_behaviour(self):
        # verifies: SPEC-0009/AC-02
        cfg = parse(Path("."), CONFIG_05)
        self.assertEqual(cfg["language"]["docs"], "es")
        self.assertEqual(cfg["hooks"]["commit_msg"], "own")
        self.assertEqual(cfg["autonomy"]["level"], "full")
        self.assertEqual(cfg["trace"]["legacy_base"], "")
        self.assertEqual(cfg["release"]["version_files"], [])


class DoctorHintTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG + '[autonomy]\nnewer = 1\n')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_doctor_shows_the_hint_of_a_configuration_error(self):
        # verifies: SPEC-0009/AC-03
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            problems = setup.doctor(self.root)
        self.assertEqual(problems, 1)
        self.assertIn("✗ Configuración: Clave desconocida en la configuración: 'autonomy.newer'", out.getvalue())
        self.assertIn("→ Si no es una errata", out.getvalue())


if __name__ == "__main__":
    unittest.main()
