"""Tests of the per-agent guard, its shim and the launcher record (SPEC-0012)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import catalog_support as support
import test_mth
from mthlib import agent_guard, catalog, setup
from mthlib.git import Git

CATALOG = support.CATALOG
SHIM = CATALOG / "_shared" / "mth-agent-guard.sh"
RECORD = f"{sys.executable}\n{setup.MTH_PY}\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, **test_mth.GIT_ENV})


class GuardRepo:
    """A repository with every catalog agent installed and one linked worktree."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.root = (self.tmp / "repo").resolve()
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main")
        config = support.fixture_config(self.root).data
        for name in catalog.names(CATALOG):
            r = catalog.render(CATALOG, name, config)
            self.write(f".claude/agents/{name}.md", r.agent_md)
            self.write(f".claude/mth/agents/{name}.guard.toml", r.guard_toml)
        self.write("README.md", "x\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "init")
        self.worktree = self.root / ".claude" / "worktrees" / "agent-1"
        _git(self.root, "worktree", "add", "-q", "-b", "agent-1", str(self.worktree))

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def payload(self, agent: str | None, tool: str = "Bash", cwd: Path | None = None, **tool_input) -> dict:
        data = {"session_id": "s", "cwd": str(cwd or self.root), "hook_event_name": "PreToolUse",
                "tool_name": tool, "tool_input": tool_input}
        if agent is not None:
            data.update(agent_id="a1", agent_type=agent)
        return data

    def guard(self, payload: dict | str) -> int:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        with contextlib.redirect_stderr(io.StringIO()):
            return agent_guard.main(stdin, {"CLAUDE_PROJECT_DIR": str(self.root)})

    def close(self) -> None:
        shutil.rmtree(self.tmp)


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = GuardRepo()
        self.addCleanup(self.repo.close)


class EvalCaseTests(GuardTestCase):
    def test_every_guard_case_of_the_catalog_gives_the_expected_result(self):
        # verifies: SPEC-0012/AC-09
        total = 0
        for name in catalog.names(CATALOG):
            evals = tomllib.loads((CATALOG / name / "evals.toml").read_text(encoding="utf-8"))
            for case in evals.get("guard", []):
                tool = case.get("tool", "Bash")
                cwd = self.repo.worktree if case.get("cwd") == "worktree" else self.repo.root
                tool_input = {"command": case["command"]} if tool == "Bash" else {"file_path": case["path"]}
                with self.subTest(agent=name, case=tool_input):
                    rc = self.repo.guard(self.repo.payload(name, tool, cwd, **tool_input))
                    self.assertEqual("allow" if rc == 0 else "deny", case["expect"])
                    total += 1
        self.assertGreaterEqual(total, 60)


class FailClosedTests(GuardTestCase):
    def test_blocks_on_missing_rules_unreadable_payload_missing_agent_type_or_internal_error(self):
        # verifies: SPEC-0012/AC-08
        (self.repo.root / ".claude/mth/agents/revisor-fallos.guard.toml").unlink()
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-fallos", command="git log")), 2)
        self.assertEqual(self.repo.guard("{no es json"), 2)
        self.assertEqual(self.repo.guard("[1, 2]"), 2)
        payload = self.repo.payload("revisor-diseno", command="git log")
        del payload["agent_type"]
        self.assertEqual(self.repo.guard(payload), 2)
        with mock.patch.object(agent_guard, "check_bash", side_effect=RuntimeError("boom")):
            self.assertEqual(self.repo.guard(self.repo.payload("revisor-diseno", command="git log")), 2)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = agent_guard.main(json.dumps(self.repo.payload("revisor-diseno", command="git log")), {})
        self.assertEqual(rc, 2)

    def test_invalid_rules_and_unexpected_tools_are_blocked(self):
        self.repo.write(".claude/mth/agents/revisor-adr.guard.toml", "[bash\n")
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-adr", command="git log")), 2)
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-diseno", "WebFetch", url="x")), 2)


class DispatchTests(GuardTestCase):
    def test_only_catalog_agents_are_restricted(self):
        # verifies: SPEC-0012/AC-16
        push = {"command": "git push origin main"}
        self.repo.write(".claude/agents/propio.md", "---\nname: propio\ntools: Bash\n---\nAgente del repo.\n")
        for agent in ("Explore", "general-purpose", "methodology:verificador", "propio", "../revisor-adr"):
            with self.subTest(agent=agent):
                self.assertEqual(self.repo.guard(self.repo.payload(agent, **push)), 0)
        self.assertEqual(self.repo.guard(self.repo.payload(None, **push)), 0)  # main session
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-seguridad", **push)), 2)
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-seguridad", command="git log --oneline")), 0)
        self.assertEqual(self.repo.guard(self.repo.payload("orquestador", **push)), 0)  # delegate = "global"

    def test_messages_reach_the_model_on_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            agent_guard.main(json.dumps(self.repo.payload("revisor-seguridad", command="git push")),
                             {"CLAUDE_PROJECT_DIR": str(self.repo.root)})
        self.assertIn("[mth-agent-guard] Comando no permitido", err.getvalue())


class WorktreeWriteTests(GuardTestCase):
    def write_call(self, cwd: Path, path: str) -> int:
        return self.repo.guard(self.repo.payload("diagnosticador", "Write", cwd, file_path=path, content="x"))

    def test_in_worktree_agents_write_only_inside_their_linked_worktree(self):
        # verifies: SPEC-0012/AC-18
        wt = self.repo.worktree
        self.assertEqual(self.write_call(wt, str(wt / "tests/test_x.py")), 0)
        self.assertEqual(self.write_call(wt, "src/x.py"), 0)
        self.assertEqual(self.write_call(self.repo.root, str(self.repo.root / "src/x.py")), 2)
        self.assertEqual(self.write_call(wt, str(self.repo.root / "README.md")), 2)
        (wt / "tests").mkdir()
        self.assertEqual(self.write_call(wt / "tests", "../../../../README.md"), 2)
        other = self.repo.tmp / "otro"
        other.mkdir()
        _git(other, "init", "-q")
        self.assertEqual(self.write_call(other, str(other / "x.py")), 2)

    def test_non_worktree_writers_keep_their_globs(self):
        evals = lambda path: self.repo.guard(self.repo.payload("analista-evals", "Write", file_path=path, content="x"))
        self.assertEqual(evals(".work/evals/informe.md"), 0)
        self.assertEqual(evals(str(self.repo.root / "src/x.py")), 2)
        self.assertEqual(evals("/etc/passwd"), 2)

    def test_bash_from_another_repository_is_blocked(self):
        other = self.repo.tmp / "otro"
        other.mkdir()
        _git(other, "init", "-q")
        self.assertEqual(self.repo.guard(self.repo.payload("revisor-fallos", cwd=other, command="git log")), 2)
        self.assertEqual(self.repo.guard(self.repo.payload("diagnosticador", cwd=self.repo.worktree,
                                                           command="pytest -q")), 0)


class ShimTests(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.shim = self.repo.root / ".claude/hooks/mth-agent-guard"
        self.shim.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SHIM, self.shim)
        self.common = self.repo.root / ".git"

    def run_shim(self, payload: dict, project: Path | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project or self.repo.root)}
        return subprocess.run(["sh", str(self.shim)], input=json.dumps(payload), env=env,
                              capture_output=True, text=True)

    def fake_launcher(self, body: str) -> Path:
        """Record ``sh`` as the interpreter and a script with ``body`` as mth.py."""
        script = self.repo.tmp / "fake-mth.sh"
        script.write_text(body, encoding="utf-8")
        (self.common / "mth").mkdir(exist_ok=True)
        (self.common / "mth" / "launcher").write_text(f"{shutil.which('sh')}\n{script}\n", encoding="utf-8")
        return script

    def test_main_session_skips_the_launcher_and_subagents_need_it(self):
        # verifies: SPEC-0012/AC-10
        marker = self.repo.tmp / "called"
        self.fake_launcher(f"touch {marker}\nexit 2\n")
        self.assertEqual(self.run_shim(self.repo.payload(None, command="git push")).returncode, 0)
        self.assertFalse(marker.exists())
        (self.common / "mth" / "launcher").unlink()
        proc = self.run_shim(self.repo.payload("revisor-seguridad", command="git log"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("abre una sesión nueva", proc.stderr)
        self.assertFalse(marker.exists())

    def test_real_launcher_from_a_linked_worktree(self):
        # verifies: SPEC-0012/AC-10
        setup.register_launcher(Git(self.repo.worktree))
        self.assertEqual((self.common / "mth" / "launcher").read_text(encoding="utf-8"), RECORD)
        wt = self.repo.worktree
        push = self.repo.payload("revisor-seguridad", cwd=wt, command="git push origin agent-1")
        log = self.repo.payload("revisor-seguridad", cwd=wt, command="git log --oneline")
        self.assertEqual(self.run_shim(push).returncode, 2)
        self.assertEqual(self.run_shim(log).returncode, 0)
        self.assertEqual(self.run_shim(log, project=wt).returncode, 0)

    def test_any_failure_of_the_launcher_blocks(self):
        self.fake_launcher("exit 1\n")
        proc = self.run_shim(self.repo.payload("revisor-seguridad", command="git log"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("código 1", proc.stderr)

    def test_outside_a_repository_subagents_are_blocked(self):
        outside = self.repo.tmp / "fuera"
        outside.mkdir()
        self.assertEqual(self.run_shim(self.repo.payload("revisor-adr", command="git log"), project=outside).returncode, 2)


class LauncherRecordTests(unittest.TestCase):
    def test_register_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init", "-q")
            git = Git(root)
            path = setup.register_launcher(git)
            self.assertEqual(path.read_text(encoding="utf-8"), RECORD)
            mtime = path.stat().st_mtime_ns
            self.assertEqual(setup.register_launcher(git), path)
            self.assertEqual(path.stat().st_mtime_ns, mtime)
            self.assertEqual(path, (root / ".git/mth/launcher").resolve())


if __name__ == "__main__":
    unittest.main()
