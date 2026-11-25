"""Tests of configurable autonomy (SPEC-0007)."""
from __future__ import annotations

import contextlib
import io
import json
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
from mthlib import guard, session  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
UNTIL_PR = ["$MTH integrate --title x", '${MTH} release', 'sh "/opt/plugin/scripts/mth" hotfix finish',
            "python3 /opt/plugin/scripts/mth.py integrate", "mth release"]
SUPERVISED_ONLY = ['$MTH commit --type feat --summary "x"', "$MTH branch feat runner",
                   'git commit -m "x"', "git -C . push origin feat/runner"]
NEVER = ["$MTH trace", "$MTH hotfix leak", "git status", "ls -la"]


class ConfirmationTests(unittest.TestCase):
    def test_full_never_asks(self):
        # verifies: SPEC-0007/AC-01
        for command in UNTIL_PR + SUPERVISED_ONLY + NEVER:
            with self.subTest(command=command):
                self.assertIsNone(guard.confirmation(command, "full"))
        self.assertEqual(parse(Path("."), CONFIG)["autonomy"]["level"], "full")

    def test_until_pr_asks_before_integrating_and_releasing(self):
        # verifies: SPEC-0007/AC-02
        for command in UNTIL_PR:
            with self.subTest(command=command):
                self.assertIn("requiere confirmación", guard.confirmation(command, "until-pr"))
        for command in SUPERVISED_ONLY + NEVER:
            with self.subTest(command=command):
                self.assertIsNone(guard.confirmation(command, "until-pr"))

    def test_supervised_also_asks_for_commits_branches_and_pushes(self):
        # verifies: SPEC-0007/AC-03
        for command in UNTIL_PR + SUPERVISED_ONLY:
            with self.subTest(command=command):
                self.assertIsNotNone(guard.confirmation(command, "supervised"))
        for command in NEVER:
            with self.subTest(command=command):
                self.assertIsNone(guard.confirmation(command, "supervised"))

    def test_invalid_levels_are_rejected_exactly(self):
        # verifies: SPEC-0007/AC-06
        for level in ("FULL", "", "until_pr"):
            with self.subTest(level=level), self.assertRaises(MthError) as ctx:
                parse(Path("."), CONFIG + f'[autonomy]\nlevel = "{level}"\n')
            self.assertIn("debe ser uno de full, until-pr, supervised", ctx.exception.message)

    def test_session_rules_describe_the_level(self):
        # verifies: SPEC-0007/AC-05
        for level, expected in (("full", "Trabajas de forma **autónoma** sobre las specs"),
                                ("until-pr", "**autónoma hasta el PR**"), ("supervised", "Trabajas **supervisado**")):
            with self.subTest(level=level):
                cfg = parse(Path("."), CONFIG + f'[autonomy]\nlevel = "{level}"\n')
                self.assertIn(expected, session.rules(cfg, "mth"))


class GuardHookTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        env = {**os.environ, **test_mth.GIT_ENV}
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "init"],
                     ["checkout", "-q", "-b", "feat/runner"]):
            subprocess.run(["git", *args], cwd=self.root, env=env, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_guard(self, command: str, config: str) -> tuple[int, str]:
        test_mth._write(self.root / ".claude/methodology.toml", config)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = guard.main(json.dumps({"tool_input": {"command": command}, "cwd": str(self.root)}))
        return code, out.getvalue()

    def test_no_autonomy_table_never_asks_through_the_hook(self):
        # verifies: SPEC-0007/AC-01
        for command in ("$MTH integrate --title x", 'git commit -m "x"'):
            with self.subTest(command=command):
                self.assertEqual(self.run_guard(command, CONFIG), (0, ""))

    def test_other_blocked_commands_stay_blocked(self):
        # verifies: SPEC-0007/AC-04
        for command in ("git rebase origin/main", 'git commit --no-verify -m "x"'):
            for level in ("full", "supervised"):
                with self.subTest(command=command, level=level):
                    code, out = self.run_guard(command, CONFIG + f'[autonomy]\nlevel = "{level}"\n')
                    self.assertEqual((code, out), (guard.BLOCK, ""))

    def test_blocked_commands_stay_blocked(self):
        # verifies: SPEC-0007/AC-04
        for level in ("full", "until-pr", "supervised"):
            with self.subTest(level=level):
                code, out = self.run_guard("git push --force origin feat/runner",
                                           CONFIG + f'[autonomy]\nlevel = "{level}"\n')
                self.assertEqual((code, out), (guard.BLOCK, ""))

    def test_ask_decision_and_fail_safe_on_invalid_config(self):
        # verifies: SPEC-0007/AC-02
        # verifies: SPEC-0007/AC-06
        code, out = self.run_guard("$MTH integrate --title x", CONFIG + '[autonomy]\nlevel = "until-pr"\n')
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((code, decision["permissionDecision"], decision["hookEventName"]), (0, "ask", "PreToolUse"))
        with self.assertRaises(MthError) as ctx:
            parse(self.root, CONFIG + '[autonomy]\nlevel = "yolo"\n')
        self.assertIn("debe ser uno de full, until-pr, supervised", ctx.exception.message)
        code, out = self.run_guard('git commit -m "x"', CONFIG + '[autonomy]\nlevel = "yolo"\n')
        self.assertEqual((code, json.loads(out)["hookSpecificOutput"]["permissionDecision"]), (0, "ask"))
        self.assertIn("Trabajas **supervisado**", session.rules(None, "mth"))


if __name__ == "__main__":
    unittest.main()
