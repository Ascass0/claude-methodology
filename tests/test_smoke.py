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


class FailureModeTests(SmokeTestCase):
    def test_a_timeout_with_evidence_of_failure_still_fails(self):
        # verifies: SPEC-0014/AC-12
        result = self.run_smoke("leak-then-hang", timeout=1.0)
        self.assertEqual(result.outcome, smoke.FAIL, result)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(self.probes["pid"].read_text()), 0)

    def test_a_scratch_repo_that_cannot_be_built_is_an_actionable_error(self):
        # verifies: SPEC-0014/AC-12
        from mthlib.errors import MthError
        for failure in (OSError("disco lleno"), MthError("git init falló")):
            with self.subTest(failure=failure), mock.patch.object(smoke, "build_repo", side_effect=failure), \
                    self.assertRaises(MthError) as caught:
                self.seed_record()
                self.run_smoke("obey")
            self.assertIn("repositorio temporal", caught.exception.message)
            self.assertIn("no se ha registrado nada", caught.exception.hint)
            self.assertEqual(self.record()["claude_version"], "1.0.0 (Old)")

    def test_a_git_that_hangs_in_the_scratch_repo_is_bounded(self):
        # verifies: SPEC-0014/AC-12
        from mthlib.errors import MthError
        fake = self.bin / "git"
        fake.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        fake.chmod(0o755)
        with mock.patch.object(smoke, "GIT_TIMEOUT", 0.5), \
                mock.patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}"}), \
                self.assertRaises(MthError) as caught:
            smoke._git(self.root, "init")
        self.assertIn("no respondió", caught.exception.message)

    def test_the_callers_git_variables_never_reach_the_scratch_repo(self):
        # verifies: SPEC-0014/AC-12
        env = smoke._environment({"GIT_DIR": "/real/.git", "GIT_WORK_TREE": "/real", "HOME": "/h"})
        self.assertEqual(env, {"HOME": "/h"})
        with mock.patch.dict(os.environ, {"GIT_DIR": str(self.root / ".git")}):
            scratch = Path(self.bin / "scratch")
            scratch.mkdir()
            smoke.build_repo(scratch)
        self.assertTrue((scratch / ".git").is_dir())
        self.assertEqual(subprocess.run(["git", "-C", str(self.root), "log", "--oneline"], capture_output=True,
                                        text=True).stdout.strip(), "")

    def test_a_record_that_cannot_be_written_keeps_the_verdict(self):
        # verifies: SPEC-0014/AC-12
        with mock.patch.object(smoke, "write_record", side_effect=OSError("solo lectura")):
            passed = self.run_smoke("obey")
        self.assertEqual(passed.outcome, smoke.PASS)
        self.assertIn("No se pudo actualizar el registro", " ".join(passed.details))
        self.seed_record()
        with mock.patch.object(smoke, "clear_record", side_effect=OSError("solo lectura")):
            failed = self.run_smoke("ignore-hooks")
        self.assertEqual(failed.outcome, smoke.FAIL)
        self.assertIn("bórralo", " ".join(failed.details))

    def test_a_cli_that_cannot_start_is_inconclusive(self):
        # verifies: SPEC-0014/AC-12
        broken = self.bin / "broken"
        broken.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
        broken.chmod(0o755)
        self.seed_record()
        result = smoke.smoke(self.git, str(broken), "haiku", 5.0, dict(os.environ))
        self.assertEqual(result.outcome, smoke.INCONCLUSIVE)
        self.assertEqual(self.record()["claude_version"], "1.0.0 (Old)")

    def test_a_real_sigterm_cleans_up_and_kills_claude(self):
        # verifies: SPEC-0014/AC-06
        import signal
        import time
        mth = Path(__file__).resolve().parent.parent / "plugins/methodology/scripts/mth.py"
        proc = subprocess.Popen([sys.executable, str(mth), "smoke", "--claude", str(self.claude)], cwd=self.root,
                                env=self.environ("hang"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (self.probes["pid"].exists() and self.probes["pid"].read_text()):
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(Path(self.probes["cwd"].read_text()).exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(self.probes["pid"].read_text()), 0)
        self.assertIsNone(self.record())

    def test_every_verdict_is_traced(self):
        # verifies: SPEC-0014/AC-12
        self.run_smoke("ignore-hooks")
        lines = (self.git.common_dir() / "mth" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[-1])
        self.assertEqual((event["event"], event["outcome"]), ("smoke.verdict", smoke.FAIL))
        self.assertTrue(event["evidence"]["leak_file"])


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
        # A relative or empty PATH entry would pick a file of the current directory (the repository).
        cwd = os.getcwd()
        os.chdir(self.bin)  # holds an executable `claude`
        try:
            self.assertTrue(smoke.shutil.which("claude", path=":."))  # the hazard is real...
            self.assertIsNone(smoke.find_claude(None, {"PATH": ":."}))  # ...and refused
        finally:
            os.chdir(cwd)

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
