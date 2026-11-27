"""Tests of the opt-in pre-commit hook of the secrets gate (SPEC-0024, ADR-0022) with a fake gitleaks."""
from __future__ import annotations

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
from mthlib import setup  # noqa: E402
from mthlib.config import load  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402
from test_secrets import install_fake  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n[secrets]\nhook = "on"\n'
FOREIGN = '#!/bin/sh\nif [ -e BLOCKED ]; then echo "blocked by the repo hook" >&2; exit 1; fi\n'
PRE = setup.PRE_COMMIT


class PreCommitCase(unittest.TestCase):
    config = CONFIG

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.fake = install_fake(self.root.parent / f"{self.root.name}-bin")
        self.addCleanup(shutil.rmtree, self.fake)
        self.log = self.root.parent / f"{self.root.name}.log"
        self.addCleanup(lambda: self.log.unlink(missing_ok=True))
        self.env = {**os.environ, **test_mth.GIT_ENV, "FAKE_GITLEAKS_LOG": str(self.log),
                    "FAKE_GITLEAKS_MODE": "clean", "PATH": f"{self.fake}:{os.environ['PATH']}"}
        self.run_git("init", "-q", "-b", "main")
        test_mth._write(self.root / ".claude/methodology.toml", self.config)
        self.git = Git.discover(self.root)
        self.hooks = self.git.hooks_dir()
        self.hooks.mkdir(parents=True, exist_ok=True)

    def run_git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=check, capture_output=True, text=True)

    def commit(self) -> subprocess.CompletedProcess:
        (self.root / f"f{len(list(self.root.iterdir()))}.txt").write_text("x", encoding="utf-8")
        self.run_git("add", "-A")
        return self.run_git("commit", "-q", "-m", "chore: add a file", check=False)

    def foreign(self) -> Path:
        path = self.hooks / "pre-commit"
        path.write_text(FOREIGN, encoding="utf-8")
        path.chmod(0o755)
        return path


class HookBehaviourTests(PreCommitCase):
    def test_installed_hook_scans_what_is_staged_and_rejects_a_secret(self):
        # verifies: SPEC-0024/AC-05
        # verifies: SPEC-0024/FM-02
        # verifies: SPEC-0024/FM-03
        setup.install_hook(self.git, "own", PRE)
        self.assertEqual(self.commit().returncode, 0)
        self.env["FAKE_GITLEAKS_MODE"] = "leak"
        refused = self.commit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("aws-access-token · src/cfg.py:7", refused.stderr + refused.stdout)
        self.assertNotIn("TOPSECRET", refused.stderr + refused.stdout)
        self.env["FAKE_GITLEAKS_MODE"] = "clean"
        self.env["PATH"] = "/usr/bin:/bin"  # no gitleaks: the commit is rejected, never waved through
        self.assertNotEqual(self.commit().returncode, 0)

    def test_the_hook_rejects_the_commit_when_mth_is_missing(self):
        # verifies: SPEC-0024/AC-05
        setup.install_hook(self.git, "own", PRE)
        path = self.hooks / "pre-commit"
        path.write_text(path.read_text().replace(str(setup.MTH), "/nonexistent/mth"), encoding="utf-8")
        refused = self.commit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("claude-methodology no encontrado", refused.stderr)

    def test_installing_twice_changes_nothing(self):
        # verifies: SPEC-0024/AC-08
        self.assertEqual(setup.install_hook(self.git, "chain", PRE), "installed")
        first = (self.hooks / "pre-commit").read_text()
        self.assertEqual(setup.install_hook(self.git, "chain", PRE), "current")
        self.assertEqual((self.hooks / "pre-commit").read_text(), first)
        self.assertEqual(setup.hook_state(self.git, "chain", PRE), "current")


class HookModeTests(PreCommitCase):
    def test_own_keeps_a_foreign_hook(self):
        # verifies: SPEC-0024/AC-06
        path = self.foreign()
        self.assertEqual(setup.install_hook(self.git, "own", PRE), "foreign")
        self.assertEqual(path.read_text(), FOREIGN)

    def test_replace_keeps_a_copy_and_refuses_when_the_copy_exists(self):
        # verifies: SPEC-0024/AC-06
        # verifies: SPEC-0024/FM-04
        self.foreign()
        (self.hooks / "pre-commit.pre-mth").write_text("old", encoding="utf-8")
        with self.assertRaises(MthError):
            setup.install_hook(self.git, "replace", PRE)
        self.assertEqual((self.hooks / "pre-commit").read_text(), FOREIGN)
        (self.hooks / "pre-commit.pre-mth").unlink()
        self.assertEqual(setup.install_hook(self.git, "replace", PRE), "replaced")
        self.assertEqual((self.hooks / "pre-commit.pre-mth").read_text(), FOREIGN)

    def test_chain_runs_the_foreign_hook_first_and_rejects_when_it_is_gone(self):
        # verifies: SPEC-0024/AC-06
        # verifies: SPEC-0024/FM-05
        self.foreign()
        self.assertEqual(setup.install_hook(self.git, "chain", PRE), "chained")
        self.assertEqual(self.commit().returncode, 0)
        (self.root / "BLOCKED").write_text("", encoding="utf-8")
        blocked = self.commit()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("blocked by the repo hook", blocked.stderr)
        (self.root / "BLOCKED").unlink()
        (self.hooks / "pre-commit.local").unlink()
        gone = self.commit()
        self.assertNotEqual(gone.returncode, 0)
        self.assertIn("falta el hook encadenado pre-commit.local", gone.stderr)

    def test_versioned_hooks_directory_is_left_alone_with_the_instruction(self):
        # verifies: SPEC-0024/AC-07
        # verifies: SPEC-0024/FM-04
        managed = self.root / ".husky"
        managed.mkdir()
        (managed / "pre-commit").write_text(FOREIGN, encoding="utf-8")
        self.run_git("config", "core.hooksPath", ".husky")
        for mode in ("replace", "chain"):
            with self.subTest(mode=mode), self.assertRaises(MthError) as ctx:
                setup.install_hook(self.git, mode, PRE)
            self.assertIn("mth secrets --staged", ctx.exception.hint)
        self.assertEqual(sorted(p.name for p in managed.iterdir()), ["pre-commit"])


class SecretsSwitchTests(PreCommitCase):
    def cfg(self, hook: str):
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG.replace('hook = "on"', f'hook = "{hook}"'))
        return load(self.root)

    def test_on_installs_and_off_retires_only_our_hook(self):
        # verifies: SPEC-0024/AC-05
        self.assertEqual(setup.sync_secrets_hook(self.git, self.cfg("on")), "installed")
        self.assertEqual(setup.sync_secrets_hook(self.git, self.cfg("off")), "removed")
        self.assertFalse((self.hooks / "pre-commit").exists())
        self.assertIsNone(setup.sync_secrets_hook(self.git, self.cfg("")))
        path = self.foreign()
        (self.hooks / "pre-commit.local").write_text("saved", encoding="utf-8")
        self.assertIsNone(setup.sync_secrets_hook(self.git, self.cfg("off")))
        self.assertEqual(path.read_text(), FOREIGN)
        self.assertTrue((self.hooks / "pre-commit.local").exists())


if __name__ == "__main__":
    unittest.main()
