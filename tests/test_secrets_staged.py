"""Tests of `mth secrets --staged` and the new keys (SPEC-0024) with a fake gitleaks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import secretgate  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_secrets import BASE, SECTION, install_fake  # noqa: E402


class KeysTests(unittest.TestCase):
    def test_defaults_are_undecided_and_own(self):
        # verifies: SPEC-0024/AC-01
        cfg = parse(Path("."), BASE)
        self.assertEqual((cfg["secrets"]["hook"], cfg["secrets"]["ci"], cfg["hooks"]["pre_commit"]), ("", "", "own"))

    def test_unknown_values_fail_fast_naming_the_key(self):
        # verifies: SPEC-0024/AC-01
        # verifies: SPEC-0024/FM-01
        cases = (("[secrets]\nhook = \"yes\"\n", "secrets.hook"), ("[secrets]\nci = \"block\"\n", "secrets.ci"),
                 ("[hooks]\npre_commit = \"skip\"\n", "hooks.pre_commit"))
        for body, key in cases:
            with self.assertRaises(MthError, msg=key) as ctx:
                parse(Path("."), BASE + body)
            self.assertIn(key, ctx.exception.message)
        for value in ("", "off", "on"):
            parse(Path("."), BASE + f'[secrets]\nhook = "{value}"\nci = "{value}"\n')
        for value in ("own", "replace", "chain"):
            parse(Path("."), BASE + f'[hooks]\npre_commit = "{value}"\n')


class StagedScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.log = self.tmp / "calls.log"
        env = {"PATH": f"{install_fake(self.tmp / 'bin')}:{os.environ['PATH']}", "FAKE_GITLEAKS_LOG": str(self.log),
               "FAKE_GITLEAKS_MODE": "clean"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.tmp / "repo"
        self.root.mkdir()

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def mode(self, mode: str) -> None:
        os.environ["FAKE_GITLEAKS_MODE"] = mode

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.root, check=True,
                       capture_output=True)

    def committed_repo(self) -> None:
        self.git("init", "-q")
        (self.root / "a.txt").write_text("one\n")
        (self.root / "b.txt").write_text("two\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def test_nothing_staged_or_only_deletions_never_run_gitleaks(self):
        # regression: the pre-commit hook started gitleaks even when the commit adds no content
        self.committed_repo()
        secretgate.enforce_staged(self.root, SECTION)
        self.git("rm", "-q", "a.txt")
        secretgate.enforce_staged(self.root, SECTION)
        self.assertFalse(self.log.exists())

    def test_added_modified_and_renamed_files_are_scanned(self):
        # regression: the early exit must not skip content that can hold a secret
        self.committed_repo()
        (self.root / "c.txt").write_text("new\n")
        self.git("add", "c.txt")
        secretgate.enforce_staged(self.root, SECTION)
        (self.root / "b.txt").write_text("changed\n")
        self.git("add", "b.txt")
        self.git("mv", "a.txt", "renamed.txt")
        secretgate.enforce_staged(self.root, SECTION)
        self.assertEqual(len(self.calls()), 2)

    def test_scans_only_what_is_staged_and_passes_the_baseline_if_it_exists(self):
        # verifies: SPEC-0024/AC-02
        secretgate.enforce_staged(self.root, SECTION)
        (self.root / SECTION["baseline"]).write_text("[]\n")
        secretgate.enforce_staged(self.root, SECTION)
        first, second = self.calls()
        for call in (first, second):
            self.assertEqual(call[:2], ["git", str(self.root)])
            for flag in ("--pre-commit", "--staged", "--redact"):
                self.assertIn(flag, call)
            self.assertFalse([a for a in call if a.startswith("--log-opts")])
        self.assertNotIn("--baseline-path", first)
        self.assertIn("--baseline-path", second)

    def test_a_staged_finding_is_listed_without_value_or_commit_and_clean_passes(self):
        # verifies: SPEC-0024/AC-03
        # verifies: SPEC-0024/FM-03
        secretgate.enforce_staged(self.root, SECTION)
        self.mode("leak")
        with self.assertRaises(MthError) as ctx:
            secretgate.enforce_staged(self.root, SECTION)
        text = ctx.exception.message + (ctx.exception.hint or "")
        self.assertIn("aws-access-token · src/cfg.py:7", text)
        self.assertNotIn("TOPSECRET", text)
        self.assertNotIn("01234567", text)

    def test_missing_failing_or_hanging_tool_rejects_the_commit(self):
        # verifies: SPEC-0024/AC-04
        # verifies: SPEC-0024/FM-02
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp)}):
            with self.assertRaises(MthError) as ctx:
                secretgate.enforce_staged(self.root, SECTION)
            self.assertIn("gitleaks", ctx.exception.message)
            self.assertTrue(ctx.exception.hint)
        for mode in ("error", "badreport", "noreport"):
            self.mode(mode)
            with self.assertRaises(MthError, msg=mode):
                secretgate.enforce_staged(self.root, SECTION)
        self.mode("hang")
        with mock.patch.object(secretgate, "SCAN_TIMEOUT", 1):
            with self.assertRaises(MthError):
                secretgate.enforce_staged(self.root, SECTION)


if __name__ == "__main__":
    unittest.main()
