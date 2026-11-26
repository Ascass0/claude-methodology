"""Tests of the secrets gate (SPEC-0022, ADR-0020) with a fake gitleaks."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import catalog_support as support  # noqa: E402
import test_mth  # noqa: E402
from mthlib import secretgate, update  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_update import UpdateTestCase  # noqa: E402

BASE = 'version = 1\n[commands]\ntest = ""\n'
ROOT = HERE.parent
SECTION = {"mode": "block", "baseline": ".gitleaks-baseline.json"}


def install_fake(directory: Path) -> Path:
    """A `gitleaks` executable in ``directory`` that runs tests/fake_gitleaks.py."""
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "gitleaks"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {HERE / 'fake_gitleaks.py'} \"$@\"\n")
    exe.chmod(0o755)
    return directory


class ConfigTests(unittest.TestCase):
    def test_defaults_are_undecided(self):
        # verifies: SPEC-0022/AC-01
        section = parse(Path("."), BASE)["secrets"]
        self.assertEqual(section, {"mode": "", "baseline": ".gitleaks-baseline.json"})

    def test_unknown_mode_or_empty_baseline_fail_fast_naming_the_key(self):
        # verifies: SPEC-0022/AC-01
        # verifies: SPEC-0022/FM-01
        for body, key in (('mode = "warn"\n', "secrets.mode"), ('baseline = " "\n', "secrets.baseline")):
            with self.assertRaises(MthError) as ctx:
                parse(Path("."), BASE + "[secrets]\n" + body)
            self.assertIn(key, ctx.exception.message)
        for mode in ("", "off", "block"):
            parse(Path("."), BASE + f'[secrets]\nmode = "{mode}"\n')

    def test_baseline_outside_the_repo_is_rejected(self):
        # verifies: SPEC-0022/AC-14
        # verifies: SPEC-0022/FM-08
        for value in ("/etc/passwd", "../x.json", "a/../../x.json", ".git/hooks/pre-commit"):
            with self.assertRaises(MthError, msg=value):
                parse(Path("."), BASE + f'[secrets]\nbaseline = "{value}"\n')
        parse(Path("."), BASE + '[secrets]\nbaseline = "config/.gitleaks-baseline.json"\n')


class ScanTests(unittest.TestCase):
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

    def test_scans_the_branch_range_or_the_whole_history(self):
        # verifies: SPEC-0022/AC-02
        secretgate.enforce(self.root, SECTION, "origin/development..HEAD")
        secretgate.enforce(self.root, SECTION, None)
        branch, history = self.calls()
        self.assertIn("--log-opts=origin/development..HEAD", branch)
        self.assertFalse([a for a in history if a.startswith("--log-opts")])
        for call in (branch, history):
            self.assertEqual(call[:2], ["git", str(self.root)])
            self.assertIn("--redact", call)

    def test_clean_scan_succeeds(self):
        # verifies: SPEC-0022/AC-04
        self.assertEqual(secretgate.scan(self.root, "a..b", None), [])

    def test_findings_are_listed_without_the_secret_value(self):
        # verifies: SPEC-0022/AC-03
        # verifies: SPEC-0022/FM-04
        self.mode("leak")
        with self.assertRaises(MthError) as ctx:
            secretgate.enforce(self.root, SECTION, "a..b")
        text = ctx.exception.message + (ctx.exception.hint or "")
        self.assertIn("aws-access-token · src/cfg.py:7 · 01234567", text)
        self.assertNotIn("TOPSECRET", text)
        self.assertNotIn("0123456789abcdef", text)

    def test_baseline_is_passed_only_when_it_exists(self):
        # verifies: SPEC-0022/AC-05
        # verifies: SPEC-0022/FM-05
        secretgate.enforce(self.root, SECTION, "a..b")
        self.assertNotIn("--baseline-path", self.calls()[0])
        (self.root / SECTION["baseline"]).write_text("[]\n")
        secretgate.enforce(self.root, SECTION, "a..b")
        call = self.calls()[1]
        self.assertEqual(call[call.index("--baseline-path") + 1], str(self.root / SECTION["baseline"]))

    def test_accept_writes_the_baseline_without_using_it(self):
        # verifies: SPEC-0022/AC-06
        self.mode("leak")
        (self.root / SECTION["baseline"]).write_text("[]\n")
        self.assertEqual(secretgate.accept_history(self.root, SECTION), 1)
        self.assertNotIn("--baseline-path", self.calls()[0])
        saved = json.loads((self.root / SECTION["baseline"]).read_text())
        self.assertEqual(saved[0]["RuleID"], "aws-access-token")
        self.assertIn("rótalos", secretgate.ACCEPT_WARNING)

    def test_missing_tool_fails_closed_with_the_remedy(self):
        # verifies: SPEC-0022/AC-08
        # verifies: SPEC-0022/FM-02
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp)}):
            self.assertFalse(secretgate.is_installed())
            with self.assertRaises(MthError) as ctx:
                secretgate.enforce(self.root, SECTION, "a..b")
        self.assertIn("gitleaks", ctx.exception.message)
        self.assertIn("Instala", ctx.exception.hint)

    def test_baseline_that_resolves_outside_the_repo_is_refused(self):
        # verifies: SPEC-0022/AC-14
        outside = self.tmp / "outside.json"
        (self.root / "link.json").symlink_to(outside)
        self.mode("leak")
        for call in (lambda s: secretgate.accept_history(self.root, s), lambda s: secretgate.enforce(self.root, s, "a..b")):
            with self.assertRaises(MthError):
                call({**SECTION, "baseline": "link.json"})
        self.assertFalse(outside.exists())

    def test_accepted_findings_stop_blocking_and_new_ones_still_block(self):
        # verifies: SPEC-0022/AC-05
        self.mode("leak")
        with self.assertRaises(MthError):
            secretgate.enforce(self.root, SECTION, "a..b")
        secretgate.accept_history(self.root, SECTION)
        secretgate.enforce(self.root, SECTION, "a..b")

    def test_tool_output_is_never_echoed_and_a_hang_times_out(self):
        # verifies: SPEC-0022/AC-09
        # verifies: SPEC-0022/AC-15
        # verifies: SPEC-0022/FM-09
        self.mode("error")
        with self.assertRaises(MthError) as ctx:
            secretgate.enforce(self.root, SECTION, "a..b")
        self.assertNotIn("TOPSECRET", ctx.exception.message + (ctx.exception.hint or ""))
        self.mode("hang")
        with mock.patch.object(secretgate, "SCAN_TIMEOUT", 1):
            with self.assertRaises(MthError) as ctx:
                secretgate.enforce(self.root, SECTION, "a..b")
        self.assertIn("no respondió", ctx.exception.message)

    def test_tool_failure_or_unreadable_report_fail_closed(self):
        # verifies: SPEC-0022/AC-09
        # verifies: SPEC-0022/FM-03
        for mode in ("error", "badreport", "noreport"):
            self.mode(mode)
            with self.assertRaises(MthError, msg=mode):
                secretgate.enforce(self.root, SECTION, "a..b")

    def test_temporary_report_is_removed_even_on_failure(self):
        # verifies: SPEC-0022/AC-10
        # verifies: SPEC-0022/FM-06
        for mode in ("leak", "error", "clean"):
            self.mode(mode)
            try:
                secretgate.enforce(self.root, SECTION, "a..b")
            except MthError:
                pass
        paths = [Path(p) for p in Path(f"{self.log}.paths").read_text().split()]
        self.assertEqual(len(paths), 3)
        for path in paths:
            self.assertFalse(path.parent.exists(), path)


class GateTests(unittest.TestCase):
    """`mth secrets`, the `mth integrate` gate and `mth doctor` on a repo with a local remote."""

    setUp_e2e = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def setUp(self):
        self.setUp_e2e()
        self.fake = install_fake(self.tmp / "fakebin")
        self.log = self.tmp / "gitleaks.log"
        self.env = {**self.env, "FAKE_GITLEAKS_LOG": str(self.log), "FAKE_GITLEAKS_MODE": "clean"}
        self.mth("init")
        self.set_mode("block")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Set the test command and the secrets gate.", "--refs", "n/a")

    def with_tool(self) -> None:
        self.env = {**self.env, "PATH": f"{self.fake}:{self.env['PATH']}"}

    def set_mode(self, mode: str) -> None:
        cfg = self.work / ".claude/methodology.toml"
        text = cfg.read_text().replace('test = ""', 'test = "true"')
        text = re.sub(r'(\[secrets\][^\[]*?mode = )"[^"]*"', rf'\1"{mode}"', text, flags=re.S)
        cfg.write_text(text)

    def calls(self) -> list[list[str]]:
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def assertNotPushed(self, branch: str) -> None:
        """`mth branch` and `mth init` push the empty branch: what must not travel is the new commit."""
        remote = self.git("ls-remote", "--heads", "origin", branch).split()
        self.assertNotIn(self.git("rev-parse", "HEAD"), remote)

    def feature_commit(self) -> None:
        self.mth("branch", "chore", "extra")
        (self.work / "x.txt").write_text("x")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add x", "--body", "A file.", "--refs", "n/a")

    def test_integrate_scans_before_pushing_and_a_finding_blocks(self):
        # verifies: SPEC-0022/AC-07
        self.with_tool()
        self.mth("integrate", "--title", "chore(methodology): adopt", "--summary", "Adopción.")
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue([a for a in self.calls()[0] if a.startswith("--log-opts=") and a.endswith("origin/development..HEAD")])
        self.feature_commit()
        self.env["FAKE_GITLEAKS_MODE"] = "leak"
        out = self.mth("integrate", "--title", "chore(x): add x", "--summary", "x", ok=False)
        self.assertIn("aws-access-token", out)
        self.assertNotIn("TOPSECRET", out)
        self.assertNotPushed("chore/extra")

    def test_integrate_without_the_tool_fails_and_pushes_nothing(self):
        # verifies: SPEC-0022/AC-08
        out = self.mth("integrate", "--title", "chore(methodology): adopt", "--summary", "Adopción.", ok=False)
        self.assertIn("gitleaks", out)
        self.assertNotPushed("chore/adopt-methodology")

    def test_off_does_not_scan_and_undecided_warns(self):
        # verifies: SPEC-0022/AC-07
        self.with_tool()
        self.set_mode("off")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "turn the gate off", "--body", "Off.", "--refs", "n/a")
        out = self.mth("integrate", "--title", "chore(methodology): adopt", "--summary", "Adopción.")
        self.assertEqual(self.calls(), [])
        self.assertNotIn("sin decidir", out)
        self.mth("branch", "chore", "undecided")
        self.set_mode("")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "undecide", "--body", "Undecided.", "--refs", "n/a")
        out = self.mth("integrate", "--title", "chore(x): undecided", "--summary", "x")
        self.assertIn("secrets.mode sin decidir", out)
        self.assertEqual(self.calls(), [])

    def test_command_scans_branch_or_history_and_accept_writes_the_baseline(self):
        # verifies: SPEC-0022/AC-02
        # verifies: SPEC-0022/AC-06
        # verifies: SPEC-0022/FM-07
        self.with_tool()
        self.mth("secrets")
        self.mth("secrets", "--history")
        branch, history = self.calls()
        self.assertTrue([a for a in branch if a.startswith("--log-opts=")])
        self.assertFalse([a for a in history if a.startswith("--log-opts=")])
        self.env["FAKE_GITLEAKS_MODE"] = "leak"
        self.mth("secrets", "--history", ok=False)
        out = self.mth("secrets", "--history", "--accept")
        self.assertIn("rótalos", out)
        self.assertTrue((self.work / ".gitleaks-baseline.json").is_file())
        self.mth("secrets", "--accept", ok=False)

    def test_doctor_flags_a_missing_tool_and_an_undecided_mode(self):
        # verifies: SPEC-0022/AC-11
        out = self.mth("doctor", ok=False)
        self.assertIn("✗ gitleaks instalado", out)
        self.with_tool()
        self.assertIn("✓ gitleaks instalado", self.mth("doctor"))
        self.set_mode("")
        self.assertIn("⚠ secrets.mode sin decidir", self.mth("doctor"))
        self.set_mode("off")
        self.assertIn("⚠ secrets.mode = off", self.mth("doctor"))


class GapTests(UpdateTestCase):
    config_text = support.template_with_agents()

    def with_mode(self, mode: str) -> None:
        self.write(".claude/methodology.toml", support.template_with_agents().replace('mode = ""', f'mode = "{mode}"', 1))

    def test_undecided_mode_is_a_decision_gap_and_decided_is_not(self):
        # verifies: SPEC-0022/AC-12
        gap = self.ids()["secretos"]
        self.assertEqual(gap.clase, update.DECISION)
        for mode in ("off", "block"):
            self.with_mode(mode)
            self.assertNotIn("secretos", self.ids())


class DocsTests(unittest.TestCase):
    def test_docs_and_reviewer_cover_the_gate(self):
        # verifies: SPEC-0022/AC-13
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in ("[secrets]", "mth secrets", "gitleaks"):
            self.assertIn(needle, readme)
        skills = ROOT / "plugins/methodology/skills"
        for skill in ("mth-update", "mth-init"):
            text = (skills / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("secrets.mode", text, skill)
        agent = (ROOT / "plugins/methodology/catalog/revisor-seguridad/agent.md.tmpl").read_text(encoding="utf-8")
        for needle in ("secrets.mode", "secrets.baseline"):
            self.assertIn(needle, agent)


if __name__ == "__main__":
    unittest.main()
