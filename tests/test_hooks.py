"""Tests of chained and replaced commit-msg hooks (SPEC-0006)."""
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
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
# A repository hook that rejects work-in-progress messages.
FOREIGN = '#!/bin/sh\nif grep -q WIP "$1"; then echo "no WIP commits" >&2; exit 1; fi\n'
VALID = "chore: add a file\n\nBody text.\n\nRefs: n/a\n"


class HookModeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.env = {**os.environ, **test_mth.GIT_ENV}
        self.run_git("init", "-q", "-b", "main")
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        self.git = Git.discover(self.root)
        self.hooks = self.git.hooks_dir()
        self.hooks.mkdir(parents=True, exist_ok=True)
        self.foreign = self.hooks / "commit-msg"
        self.foreign.write_text(FOREIGN, encoding="utf-8")
        self.foreign.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=check, capture_output=True, text=True)

    def commit(self, message: str) -> subprocess.CompletedProcess:
        (self.root / f"f{len(list(self.root.iterdir()))}.txt").write_text("x", encoding="utf-8")
        self.run_git("add", "-A")
        return self.run_git("commit", "-q", "-m", message, check=False)

    def test_own_keeps_a_foreign_hook(self):
        # verifies: SPEC-0006/AC-01
        self.assertEqual(setup.install_hook(self.git), "foreign")
        self.assertEqual(setup.install_hook(self.git, "own"), "foreign")
        self.assertEqual(self.foreign.read_text(), FOREIGN)

    def test_replace_backs_up_the_foreign_hook(self):
        # verifies: SPEC-0006/AC-02
        self.assertEqual(setup.install_hook(self.git, "replace"), "replaced")
        self.assertEqual((self.hooks / "commit-msg.pre-mth").read_text(), FOREIGN)
        self.assertIn(setup.HOOK_MARK, self.foreign.read_text())
        self.assertEqual(setup.install_hook(self.git, "replace"), "current")

    def test_replace_refuses_to_overwrite_a_backup(self):
        # verifies: SPEC-0006/AC-02
        (self.hooks / "commit-msg.pre-mth").write_text("old backup", encoding="utf-8")
        with self.assertRaises(MthError) as ctx:
            setup.install_hook(self.git, "replace")
        self.assertIn("commit-msg.pre-mth ya existe", ctx.exception.message)
        self.assertEqual(self.foreign.read_text(), FOREIGN)
        self.assertEqual((self.hooks / "commit-msg.pre-mth").read_text(), "old backup")

    def test_chain_runs_both_hooks(self):
        # verifies: SPEC-0006/AC-03
        self.assertEqual(setup.install_hook(self.git, "chain"), "chained")
        self.assertEqual((self.hooks / "commit-msg.local").read_text(), FOREIGN)
        self.assertEqual(self.commit(VALID).returncode, 0)
        rejected_by_repo = self.commit(VALID.replace("Body text.", "WIP body."))
        self.assertNotEqual(rejected_by_repo.returncode, 0)
        self.assertIn("no WIP commits", rejected_by_repo.stderr)
        rejected_by_mth = self.commit("bad message")
        self.assertNotEqual(rejected_by_mth.returncode, 0)
        self.assertIn("Mensaje de commit inválido", rejected_by_mth.stderr)

    def test_chain_is_idempotent(self):
        # verifies: SPEC-0006/AC-04
        setup.install_hook(self.git, "chain")
        hook, local = self.foreign.read_text(), (self.hooks / "commit-msg.local").read_text()
        self.assertEqual(setup.install_hook(self.git, "chain"), "current")
        self.assertEqual((self.foreign.read_text(), (self.hooks / "commit-msg.local").read_text()), (hook, local))

    def test_versioned_hooks_directory_is_left_alone(self):
        # verifies: SPEC-0006/AC-05
        managed = self.root / ".husky"
        managed.mkdir()
        (managed / "commit-msg").write_text(FOREIGN, encoding="utf-8")
        self.run_git("config", "core.hooksPath", ".husky")
        for mode in ("replace", "chain"):
            with self.subTest(mode=mode), self.assertRaises(MthError) as ctx:
                setup.install_hook(self.git, mode)
            self.assertIn("está versionado", ctx.exception.message)
        self.assertEqual(sorted(p.name for p in managed.iterdir()), ["commit-msg"])
        self.assertEqual((managed / "commit-msg").read_text(), FOREIGN)

    def test_absolute_hooks_path_inside_the_work_tree_is_left_alone(self):
        # verifies: SPEC-0006/AC-05
        managed = self.root / "tools" / "hooks"
        managed.mkdir(parents=True)
        (managed / "commit-msg").write_text(FOREIGN, encoding="utf-8")
        self.run_git("config", "core.hooksPath", str(managed))
        for mode in ("replace", "chain"):
            with self.subTest(mode=mode), self.assertRaises(MthError) as ctx:
                setup.install_hook(self.git, mode)
            self.assertIn("está versionado", ctx.exception.message)
        self.assertEqual(sorted(p.name for p in managed.iterdir()), ["commit-msg"])

    def test_mode_names_are_exact(self):
        # verifies: SPEC-0006/AC-06
        for mode in ("CHAIN", "", "chain "):
            with self.subTest(mode=mode), self.assertRaises(MthError) as ctx:
                parse(self.root, CONFIG + f'[hooks]\ncommit_msg = "{mode}"\n')
            self.assertIn("debe ser uno de own, replace, chain", ctx.exception.message)

    def test_unknown_mode_fails_fast(self):
        # verifies: SPEC-0006/AC-06
        with self.assertRaises(MthError) as ctx:
            parse(self.root, CONFIG + '[hooks]\ncommit_msg = "merge"\n')
        self.assertIn("debe ser uno de own, replace, chain", ctx.exception.message)

    def test_chain_rejects_when_the_chained_hook_is_gone(self):
        # verifies: SPEC-0006/AC-07
        setup.install_hook(self.git, "chain")
        (self.hooks / "commit-msg.local").chmod(0o644)
        not_executable = self.commit(VALID)
        self.assertNotEqual(not_executable.returncode, 0)
        self.assertIn("falta el hook encadenado commit-msg.local", not_executable.stderr)
        (self.hooks / "commit-msg.local").unlink()
        self.assertNotEqual(self.commit(VALID).returncode, 0)


if __name__ == "__main__":
    unittest.main()
