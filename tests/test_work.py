"""Tests of the local working directory .work/ (SPEC-0010)."""
from __future__ import annotations

import contextlib
import io
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
from mthlib import guard, session, setup, work  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
EXTRA = CONFIG + '[work]\ndirs = ["benchmarks"]\n'
ALL_DIRS = [*work.DEFAULT_DIRS, "benchmarks"]


class WorkCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.env = {**os.environ, **test_mth.GIT_ENV}
        self.git("init", "-q", "-b", "main")
        self.repo = Git.discover(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def exclude(self) -> str:
        return (self.root / ".git/info/exclude").read_text(encoding="utf-8")

    def doctor(self) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            setup.doctor(self.root)
        return out.getvalue()


class EnsureTests(WorkCase):
    def test_creates_the_tree_and_excludes_it(self):
        # verifies: SPEC-0010/AC-01
        work.ensure(self.repo, ["benchmarks"])
        for name in ALL_DIRS:
            self.assertTrue((self.root / ".work" / name).is_dir(), name)
        self.assertIn("\n/.work/\n", "\n" + self.exclude())
        (self.root / ".work/plans/plan.md").write_text("plan\n", encoding="utf-8")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(self.repo.files(), [])

    def test_is_idempotent(self):
        # verifies: SPEC-0010/AC-02
        work.ensure(self.repo, [])
        note = self.root / ".work/notes/keep.md"
        note.write_text("mine\n", encoding="utf-8")
        exclude = self.exclude()
        self.assertEqual(work.ensure(self.repo, []), [])
        self.assertEqual(self.exclude(), exclude)
        self.assertEqual(self.exclude().count("/.work/"), 1)
        self.assertEqual(note.read_text(encoding="utf-8"), "mine\n")

    def test_an_existing_exclusion_is_reused(self):
        # verifies: SPEC-0010/AC-02
        (self.root / ".git/info/exclude").write_text("*.log\n.work", encoding="utf-8")
        work.ensure(self.repo, [])
        self.assertEqual(self.exclude(), "*.log\n.work")

    def test_versioned_or_non_directory_work_is_left_alone(self):
        # verifies: SPEC-0010/AC-04
        exclude = self.exclude()
        (self.root / ".work").mkdir()
        (self.root / ".work/plan.md").write_text("x\n", encoding="utf-8")
        self.git("add", ".work/plan.md")
        with self.assertRaises(MthError) as ctx:
            work.ensure(self.repo, [])
        self.assertIn("git versiona ficheros bajo .work/: .work/plan.md", ctx.exception.message)
        self.assertFalse((self.root / ".work/plans").exists())
        self.assertEqual(self.exclude(), exclude)

        self.git("rm", "-q", "-r", "--cached", ".work")
        shutil.rmtree(self.root / ".work")
        (self.root / ".work").write_text("not a directory\n", encoding="utf-8")
        with self.assertRaises(MthError) as ctx:
            work.ensure(self.repo, [])
        self.assertIn(".work existe y no es un directorio", ctx.exception.message)
        self.assertEqual(self.exclude(), exclude)

    def test_write_errors_are_reported_with_their_cause(self):
        # verifies: SPEC-0010/AC-05
        exclude = self.root / ".git/info/exclude"
        exclude.unlink()
        exclude.mkdir()  # writing the exclude file now fails with an OSError
        with self.assertRaises(MthError) as ctx:
            work.ensure(self.repo, [])
        self.assertIn("No se puede preparar .work/", ctx.exception.message)
        self.assertIsInstance(ctx.exception.__cause__, OSError)
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        out = session.context(self.root, "mth")
        self.assertIn("⚠ Directorio .work/: No se puede preparar .work/", out)
        self.assertIn("Fragmentos de changelog pendientes", out)

    def test_worktrees_share_the_exclusion(self):
        # verifies: SPEC-0010/AC-01
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        linked = self.root.parent / (self.root.name + "-wt")
        self.git("worktree", "add", "-q", str(linked), "-b", "other")
        try:
            work.ensure(Git.discover(linked), [])
            self.assertIn("/.work/", self.exclude())
            (linked / ".work/tmp/x").write_text("x\n", encoding="utf-8")
            self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=linked, capture_output=True,
                                            text=True, check=True).stdout, "")
        finally:
            shutil.rmtree(linked, ignore_errors=True)


class ConfigTests(unittest.TestCase):
    def test_invalid_work_dirs_fail_fast(self):
        # verifies: SPEC-0010/AC-03
        self.assertEqual(parse(Path("."), CONFIG)["work"]["dirs"], [])
        self.assertEqual(parse(Path("."), EXTRA)["work"]["dirs"], ["benchmarks"])
        cases = {'["a/b"]': "único segmento", '["Bench"]': "único segmento", '[""]': "único segmento",
                 '["x", "x"]': "está repetido", '["tmp"]': "subdirectorio de serie"}
        for value, expected in cases.items():
            with self.subTest(value=value), self.assertRaises(MthError) as ctx:
                parse(Path("."), CONFIG + f"[work]\ndirs = {value}\n")
            self.assertIn(expected, ctx.exception.message)

    def test_valid_names_are_accepted(self):
        # verifies: SPEC-0010/AC-03
        dirs = parse(Path("."), CONFIG + '[work]\ndirs = ["a-b", "x1", "v1.2_c"]\n')["work"]["dirs"]
        self.assertEqual(dirs, ["a-b", "x1", "v1.2_c"])


class SessionAndDoctorTests(WorkCase):
    def test_session_prepares_work_only_in_an_adopted_repo(self):
        # verifies: SPEC-0010/AC-05
        session.context(self.root, "mth")
        self.assertFalse((self.root / ".work").exists())
        test_mth._write(self.root / ".claude/methodology.toml", EXTRA)
        session.context(self.root, "mth")
        self.assertTrue(work.inspect(self.repo, ["benchmarks"]).ready)

    def test_session_warns_and_continues_when_work_cannot_be_prepared(self):
        # verifies: SPEC-0010/AC-05
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        (self.root / ".work").write_text("x\n", encoding="utf-8")
        out = session.context(self.root, "mth")
        self.assertIn("⚠ Directorio .work/: No se prepara .work/: .work existe y no es un directorio", out)
        self.assertIn("Fragmentos de changelog pendientes", out)

    def test_session_rules_describe_work(self):
        # verifies: SPEC-0010/AC-09
        test_mth._write(self.root / ".claude/methodology.toml", EXTRA)
        out = session.context(self.root, "mth")
        for name in work.DEFAULT_DIRS:
            self.assertIn(f"`{name}/`", out)
        self.assertIn("`.work/` (local, excluido de git", out)
        self.assertIn("los propios del repo: `benchmarks/`", out)

    def test_doctor_warns_about_a_missing_subdirectory_of_an_excluded_work(self):
        # verifies: SPEC-0010/AC-07
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        work.ensure(self.repo, [])
        shutil.rmtree(self.root / ".work/plans")
        out = self.doctor()
        self.assertIn("⚠ Directorio de trabajo .work/: faltan plans", out)
        self.assertNotIn("sin excluir", out)

    def test_session_rules_without_extra_dirs(self):
        # verifies: SPEC-0010/AC-09
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        out = session.context(self.root, "mth")
        for name in work.DEFAULT_DIRS:
            self.assertIn(f"`{name}/`", out)
        self.assertNotIn("los propios del repo", out)

    def test_doctor_reports_each_state(self):
        # verifies: SPEC-0010/AC-07
        # verifies: SPEC-0010/AC-04
        test_mth._write(self.root / ".claude/methodology.toml", CONFIG)
        self.assertIn("⚠ Directorio de trabajo .work/: faltan plans", self.doctor())
        self.assertIn("sin excluir de git", self.doctor())
        work.ensure(self.repo, [])
        self.assertIn("✓ Directorio de trabajo .work/ (local, excluido de git)", self.doctor())
        (self.root / ".work/tmp/x").write_text("x\n", encoding="utf-8")
        self.git("add", "-f", ".work/tmp/x")
        self.assertIn("✗ Directorio de trabajo .work/: git versiona ficheros bajo .work/: .work/tmp/x", self.doctor())
        self.git("rm", "-q", "-r", "--cached", ".work")
        shutil.rmtree(self.root / ".work")
        (self.root / ".work").write_text("x\n", encoding="utf-8")
        self.assertIn("✗ Directorio de trabajo .work/: .work existe y no es un directorio", self.doctor())


class InitTests(unittest.TestCase):
    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def test_init_prepares_work(self):
        # verifies: SPEC-0010/AC-06
        self.mth("init")
        self.assertTrue(work.inspect(Git.discover(self.work), []).ready)
        self.assertNotIn(".work", self.git("show", "--name-only", "--format=", "HEAD"))

    def test_init_completes_a_partial_work(self):
        # verifies: SPEC-0010/AC-06
        (self.work / ".work/plans").mkdir(parents=True)
        self.mth("init")
        self.assertTrue(work.inspect(Git.discover(self.work), []).ready)


class GuardTests(unittest.TestCase):
    def test_forced_adds_that_reach_work_are_blocked(self):
        # verifies: SPEC-0010/AC-08
        protected = {"main", "development"}
        for command in ("git add -f .work/x", "git add --force .", "git add -f -A", "git add -f :/",
                        "git add -fA", "git add -f ./", "git add ./.work/plans -f"):
            with self.subTest(command=command):
                self.assertIn(".work/ es local", guard.violation(command, protected, "feat/x") or "")
        for command in ("git add .", "git add -A", "git add -f build/x", "git add src/.work.md"):
            with self.subTest(command=command):
                self.assertIsNone(guard.violation(command, protected, "feat/x"))

    def test_forced_adds_chained_after_another_command_are_blocked(self):
        # verifies: SPEC-0010/AC-08
        protected = {"main", "development"}
        for command in ("git status && git add -f .work/x", "git add -f -- .work/plans/p.md"):
            with self.subTest(command=command):
                self.assertIn(".work/ es local", guard.violation(command, protected, "feat/x") or "")


if __name__ == "__main__":
    unittest.main()
