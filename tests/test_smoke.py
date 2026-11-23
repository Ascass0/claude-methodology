"""mth smoke: the verdict, isolation, cost limits and the version warnings (SPEC-0014)."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import catalog_support  # noqa: F401  (puts the plugin on sys.path)
import test_agents
from mthlib import catalog, smoke
from mthlib.git import Git

FAKE = Path(__file__).resolve().parent / "fake_claude.py"


class SmokeTestCase(test_agents.AgentsTestCase):
    def setUp(self):
        super().setUp()
        self.git = Git(self.root)
        self.bin = self.root.parent / f"{self.root.name}-bin"
        self.bin.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.bin, ignore_errors=True))
        self.claude = self.bin / "claude"
        self.claude.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        self.claude.chmod(self.claude.stat().st_mode | stat.S_IXUSR)
        self.probes = {name: self.bin / name for name in ("cwd", "pid", "argv")}

    def environ(self, mode: str, **extra: str) -> dict[str, str]:
        return {**os.environ, "FAKE_CLAUDE_MODE": mode, "FAKE_CWDFILE": str(self.probes["cwd"]),
                "FAKE_PIDFILE": str(self.probes["pid"]), "FAKE_ARGVFILE": str(self.probes["argv"]), **extra}

    def run_smoke(self, mode: str, timeout: float = 60.0, **extra: str) -> smoke.Result:
        return smoke.smoke(self.git, str(self.claude), "haiku", timeout, self.environ(mode, **extra))

    def record(self) -> dict | None:
        return smoke.read_record(self.git)

    def seed_record(self, version: str = "1.0.0 (Old)") -> None:
        smoke.write_record(self.git, version, self.claude)


class VerdictTests(SmokeTestCase):
    def test_a_guard_that_acts_passes_and_records_the_literal_version(self):
        # verifies: SPEC-0014/AC-01
        result = self.run_smoke("obey")
        self.assertEqual((result.outcome, result.summary[:5]), (smoke.PASS, "PASA:"), result)
        self.assertEqual(self.record()["claude_version"], "9.9.9 (Fake Claude Code)")

    def test_a_forbidden_command_that_runs_fails_and_clears_the_record(self):
        # verifies: SPEC-0014/AC-02
        self.seed_record()
        result = self.run_smoke("ignore-hooks")
        self.assertEqual(result.outcome, smoke.FAIL, result)
        self.assertIn("FALLA", result.summary)
        self.assertIsNone(self.record())

    def test_no_tools_or_a_failing_cli_is_inconclusive_and_keeps_the_record(self):
        # verifies: SPEC-0014/AC-03
        self.seed_record()
        for mode in ("no-tools", "auth-error"):
            with self.subTest(mode=mode):
                result = self.run_smoke(mode)
                self.assertEqual(result.outcome, smoke.INCONCLUSIVE, result)
                self.assertEqual(self.record()["claude_version"], "1.0.0 (Old)")
        self.assertIn("not logged in", " ".join(self.run_smoke("auth-error").details))

    def test_a_missing_denial_or_control_never_passes(self):
        # verifies: SPEC-0014/AC-04
        for mode in ("permission-block", "no-control"):
            with self.subTest(mode=mode):
                result = self.run_smoke(mode)
                self.assertEqual(result.outcome, smoke.INCONCLUSIVE, result)
                self.assertIsNone(self.record())

    def test_a_write_the_guard_never_saw_fails(self):
        # verifies: SPEC-0014/AC-05
        self.assertEqual(self.run_smoke("write-unseen").outcome, smoke.FAIL)


class IsolationTests(SmokeTestCase):
    def scratch(self) -> Path:
        return Path(self.probes["cwd"].read_text(encoding="utf-8"))

    def test_the_users_repo_is_untouched_and_the_scratch_repo_is_removed(self):
        # verifies: SPEC-0014/AC-06
        for mode in ("obey", "ignore-hooks", "no-tools"):
            with self.subTest(mode=mode):
                before = self.snapshot()
                self.run_smoke(mode)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse((self.root / ".claude" / "agents").exists())
                self.assertNotEqual(self.scratch(), self.root)
                self.assertFalse(self.scratch().exists())

    def test_a_timeout_kills_claude_and_removes_the_scratch_repo(self):
        # verifies: SPEC-0014/AC-06
        result = self.run_smoke("hang", timeout=1.0)
        self.assertEqual(result.outcome, smoke.INCONCLUSIVE, result)
        self.assertIn("plazo", " ".join([result.summary, *result.details]))
        self.assertFalse(self.scratch().exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(self.probes["pid"].read_text()), 0)

    def test_an_interruption_cleans_up_and_records_nothing(self):
        # verifies: SPEC-0014/AC-06
        created = []
        real_build = smoke.build_repo

        def build(root):
            created.append(root)
            return real_build(root)

        with mock.patch.object(smoke, "build_repo", build), \
                mock.patch.object(smoke, "run_claude", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            self.run_smoke("obey")
        self.assertFalse(created[0].exists())
        self.assertIsNone(self.record())

    def test_the_canary_is_not_part_of_the_catalog(self):
        # verifies: SPEC-0014/AC-07
        self.run_smoke("obey")
        self.assertNotIn(smoke.CANARY, [p.name for p in catalog.CATALOG_DIR.iterdir()])
        self.assertEqual(self.mth("agents", "list"), 0)
        self.assertNotIn(smoke.CANARY, self.output)


class LimitsTests(SmokeTestCase):
    def test_the_command_line_bounds_cost_and_isolates_settings(self):
        # verifies: SPEC-0014/AC-08
        self.run_smoke("obey")
        argv = json.loads(self.probes["argv"].read_text(encoding="utf-8"))
        for flag, value in (("--model", "haiku"), ("--max-turns", "8"), ("--max-budget-usd", "0.5"),
                            ("--setting-sources", "project")):
            self.assertEqual(argv[argv.index(flag) + 1], value, flag)
        self.assertIn("--no-session-persistence", argv)
        self.assertIn("-p", argv)

    def test_the_session_variables_are_not_inherited(self):
        # verifies: SPEC-0014/AC-08
        env = smoke._environment({"CLAUDECODE": "1", "CLAUDE_PROJECT_DIR": "/x", "ANTHROPIC_API_KEY": "k"})
        self.assertEqual(env, {"ANTHROPIC_API_KEY": "k"})


class LocatingTests(SmokeTestCase):
    def test_the_order_is_flag_then_mth_claude_then_execpath_then_path(self):
        # verifies: SPEC-0014/AC-09
        paths = {}
        for name in ("flag", "mth", "exec", "onpath"):
            path = self.bin / name
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(0o755)
            paths[name] = path
        (self.bin / "claude").unlink()
        shadow = self.bin / "claude"
        shadow.symlink_to(paths["onpath"])
        env = {"MTH_CLAUDE": str(paths["mth"]), "CLAUDE_CODE_EXECPATH": str(paths["exec"]), "PATH": str(self.bin)}
        self.assertEqual(smoke.find_claude(str(paths["flag"]), env), paths["flag"])
        self.assertEqual(smoke.find_claude(None, env), paths["mth"])
        del env["MTH_CLAUDE"]
        self.assertEqual(smoke.find_claude(None, env), paths["exec"])
        del env["CLAUDE_CODE_EXECPATH"]
        self.assertEqual(smoke.find_claude(None, env), shadow)
        self.assertIsNone(smoke.find_claude("/nonexistent/claude", env))  # the first one given wins

    def test_a_missing_cli_is_inconclusive_with_a_hint(self):
        # verifies: SPEC-0014/AC-09
        result = smoke.smoke(self.git, None, "haiku", 5.0, {"PATH": str(self.bin / "empty")})
        self.assertEqual(result.outcome, smoke.INCONCLUSIVE)
        self.assertIn("MTH_CLAUDE", " ".join(result.details))


class WarningTests(SmokeTestCase):
    def notices(self, installed: bool = True, **env: str) -> list[str]:
        environ = {"CLAUDE_CODE_EXECPATH": str(self.claude), "PATH": "", **env}
        return smoke.warnings(self.git, installed, environ)

    def test_the_notices_follow_the_recorded_version(self):
        # verifies: SPEC-0014/AC-10
        self.assertIn("no se han verificado con Claude Code 9.9.9 (Fake Claude Code) (mth smoke)", self.notices()[0])
        self.seed_record("1.0.0 (Old)")
        changed = self.notices()
        self.assertEqual(len(changed), 1)
        self.assertIn("Claude Code ha cambiado desde la última prueba de humo (1.0.0 (Old) → 9.9.9 (Fake Claude "
                      "Code)); las restricciones de los agentes no están verificadas", changed[0])
        self.seed_record("9.9.9 (Fake Claude Code)")
        self.assertEqual(self.notices(), [])

    def test_no_notice_without_catalog_agents_and_doctor_explains_an_unknown_version(self):
        # verifies: SPEC-0014/AC-10
        self.assertEqual(self.notices(installed=False), [])
        self.assertEqual(smoke.warnings(self.git, True, {"PATH": ""}), [])
        self.assertIn("No se pudo determinar", smoke.warnings(self.git, True, {"PATH": ""}, explain_unknown=True)[0])

    def test_session_and_doctor_show_the_notice_once_an_agent_is_installed(self):
        # verifies: SPEC-0014/AC-10
        from mthlib import session, setup
        self.add("revisor-seguridad")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_EXECPATH": str(self.claude)}):
            self.assertTrue(any("no se han verificado" in line for line in session._state(self.root)))
            self.quiet(setup.doctor, self.root)
            self.assertIn("no se han verificado", self.output)

    def test_a_corrupt_record_counts_as_none(self):
        # verifies: SPEC-0014/AC-11
        path = self.git.common_dir() / smoke.RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        for text in ("{no json", '["lista"]', '{"claude_version": 3}'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                self.assertIsNone(smoke.read_record(self.git))
        self.assertTrue(self.notices())


if __name__ == "__main__":
    unittest.main()
