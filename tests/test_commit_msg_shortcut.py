"""The commit-msg shortcut of scripts/mth.py and `mth check-msg` through the CLI must say and exit the same."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "plugins" / "methodology" / "scripts"
CONFIG = 'version = 1\n[commands]\ntest = ""\n'
INVALID = "chore: no body and no trailer\n"
VALID = "chore: explain it\n\nThe body says what changes and why.\n\nRefs: n/a\n"


class CommitMsgShortcutTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "methodology.toml").write_text(CONFIG, encoding="utf-8")

    def both(self, message: str) -> tuple[tuple[int, str], tuple[int, str]]:
        file = self.repo / "MSG"
        file.write_text(message, encoding="utf-8")
        shortcut = subprocess.run([sys.executable, str(SCRIPTS / "mth.py"), "check-msg", str(file)], cwd=self.repo,
                                  capture_output=True, text=True)
        code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); from mthlib import cli; sys.exit(cli.main(['check-msg', {str(file)!r}]))"
        through_cli = subprocess.run([sys.executable, "-c", code], cwd=self.repo, capture_output=True, text=True)
        return (shortcut.returncode, shortcut.stderr), (through_cli.returncode, through_cli.stderr)

    def test_an_invalid_message_is_rejected_with_the_same_text_and_code(self):
        # regression: the shortcut copied the CLI handling and could drift from it
        shortcut, through_cli = self.both(INVALID)
        self.assertEqual(shortcut, through_cli)
        self.assertEqual(shortcut[0], 1)
        self.assertIn("Mensaje de commit inválido", shortcut[1])

    def test_a_valid_message_passes_both_ways(self):
        # regression: the shortcut copied the CLI handling and could drift from it
        self.assertEqual(self.both(VALID), ((0, ""), (0, "")))

    def test_a_missing_message_file_is_a_bug_with_the_same_code_both_ways(self):
        # regression: the shortcut copied the CLI handling and could drift from it
        (self.repo / "MSG").unlink(missing_ok=True)
        shortcut = subprocess.run([sys.executable, str(SCRIPTS / "mth.py"), "check-msg", str(self.repo / "NOPE")],
                                  cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(shortcut.returncode, 70)
        self.assertIn("(bug)", shortcut.stderr)


if __name__ == "__main__":
    unittest.main()
