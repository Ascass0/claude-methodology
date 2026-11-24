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
        self.probes = {name: self.bin / name for name in ("cwd", "pid", "argv", "env")}
        self.install("obey")

    def install(self, mode: str, **extra: str) -> None:
        """The fake CLI as an executable wrapper: the child's environment is minimal, so it carries its settings."""
        settings = {"FAKE_CLAUDE_MODE": mode, "FAKE_CWDFILE": str(self.probes["cwd"]),
                    "FAKE_PIDFILE": str(self.probes["pid"]), "FAKE_ARGVFILE": str(self.probes["argv"]),
                    "FAKE_ENVFILE": str(self.probes["env"]), **extra}
        exports = "".join(f"export {k}='{v}'\n" for k, v in settings.items())
        self.claude.write_text(f'#!/bin/sh\n{exports}exec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        self.claude.chmod(self.claude.stat().st_mode | stat.S_IXUSR)

    def environ(self, mode: str = "obey", **extra: str) -> dict[str, str]:
        return dict(os.environ)

    def run_smoke(self, mode: str, timeout: float = 60.0, **extra: str) -> smoke.Result:
        self.install(mode, **extra)
        return smoke.smoke(self.git, str(self.claude), "haiku", timeout, dict(os.environ))

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
        self.install("hang")
        proc = subprocess.Popen([sys.executable, str(mth), "smoke", "--claude", str(self.claude)], cwd=self.root,
                                env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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

    def events(self) -> list[dict]:
        path = self.git.common_dir() / "mth" / "trace.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_every_way_out_leaves_a_trace_event(self):
        # verifies: SPEC-0014/AC-12
        from mthlib.errors import MthError
        smoke.smoke(self.git, None, "haiku", 5.0, {"PATH": str(self.bin / "empty")})  # no claude
        broken = self.bin / "broken"
        broken.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
        broken.chmod(0o755)
        smoke.smoke(self.git, str(broken), "haiku", 5.0, dict(os.environ))  # claude --version fails
        with mock.patch.object(smoke, "build_repo", side_effect=MthError("git init falló")), \
                self.assertRaises(MthError):
            self.run_smoke("obey")
        with mock.patch.object(smoke, "run_claude", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            self.run_smoke("obey")
        self.assertEqual([e["event"] for e in self.events() if e["cmd"] == "smoke"],
                         ["smoke.verdict", "smoke.verdict", "smoke.error", "smoke.interrupted"])

    def test_the_signal_handler_exists_before_the_temp_dir_is_created(self):
        # verifies: SPEC-0014/AC-06
        order = []
        real_arm, real_mkdtemp = smoke._arm_term, smoke.tempfile.mkdtemp

        def arm():
            order.append("arm")
            return real_arm()

        def mkdtemp(*a, **k):
            order.append("mkdtemp")
            return real_mkdtemp(*a, **k)

        with mock.patch.object(smoke, "_arm_term", arm), mock.patch.object(smoke.tempfile, "mkdtemp", mkdtemp):
            self.run_smoke("obey")
        self.assertEqual(order, ["arm", "mkdtemp"])

    def test_a_background_child_does_not_outlive_the_test(self):
        # verifies: SPEC-0014/AC-06
        self.run_smoke("obey", FAKE_BACKGROUND="1")
        pid = int(self.probes["pid"].with_name("bgpid").read_text())
        deadline = __import__("time").monotonic() + 5
        while __import__("time").monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            __import__("time").sleep(0.05)
        self.fail("the background child is still alive")

    def test_relative_claude_paths_are_refused(self):
        # verifies: SPEC-0014/AC-09
        self.assertIsNone(smoke.find_claude("claude", {}))
        self.assertIsNone(smoke.find_claude(None, {"MTH_CLAUDE": "./claude"}))

    def test_control_characters_of_the_model_output_are_neutralised(self):
        # verifies: SPEC-0014/AC-12
        self.assertEqual(smoke._tail("ok\n\x1b[31mrojo\x07\n"), "?[31mrojo?")

    def test_git_ignores_the_users_configuration(self):
        # verifies: SPEC-0014/AC-12
        home = self.bin / "home"
        (home / "hooks").mkdir(parents=True)
        marker = self.bin / "hook-ran"
        (home / "hooks" / "pre-commit").write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        (home / "hooks" / "pre-commit").chmod(0o755)
        (home / ".gitconfig").write_text(f"[core]\n\thooksPath = {home / 'hooks'}\n[commit]\n\tgpgsign = true\n",
                                        encoding="utf-8")
        scratch = self.bin / "scratch"
        scratch.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home)}):
            smoke.build_repo(scratch)
        self.assertFalse(marker.exists())

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
        granted = argv[argv.index("--allowedTools") + 1:argv.index("--allowedTools") + 3]
        self.assertEqual(granted, ["Write", "Bash(touch:*)"])  # permissions never decide the test
        self.assertIn("-p", argv)

    def test_the_child_gets_a_minimal_environment(self):
        # verifies: SPEC-0014/AC-08
        secrets = {"GH_TOKEN": "t", "GITHUB_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "s", "OPENAI_API_KEY": "k",
                   "GOOGLE_APPLICATION_CREDENTIALS": "/c", "CLAUDECODE": "1", "CLAUDE_PROJECT_DIR": "/x"}
        needed = {"HOME": "/h", "PATH": "/bin", "ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_USE_BEDROCK": "0", "LC_ALL": "C"}
        self.assertEqual(smoke._environment({**secrets, **needed}), needed)
        # a provider's credentials pass only when that provider is the chosen one
        bedrock = {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_SECRET_ACCESS_KEY": "s", "GH_TOKEN": "t"}
        self.assertEqual(smoke._environment(bedrock), {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_SECRET_ACCESS_KEY": "s"})

    def test_claude_really_runs_without_the_users_credentials(self):
        # verifies: SPEC-0014/AC-08
        env = {**os.environ, "GH_TOKEN": "secreto", "GITHUB_TOKEN": "secreto", "ANTHROPIC_API_KEY": "k"}
        self.install("obey")
        smoke.smoke(self.git, str(self.claude), "haiku", 30.0, env)
        seen = json.loads(self.probes["env"].read_text(encoding="utf-8"))
        self.assertNotIn("GH_TOKEN", seen)
        self.assertNotIn("GITHUB_TOKEN", seen)
        self.assertEqual(seen.get("ANTHROPIC_API_KEY"), "k")


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
        self.assertIn("absoluta", " ".join(result.details))


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
