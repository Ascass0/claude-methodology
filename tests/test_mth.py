"""Tests of claude-methodology: unit tests and a full end-to-end flow.

The end-to-end flow uses a bare local repository as remote and a fake `gh`
(tests/fake_gh.py) that performs real merge commits. No network is needed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "methodology"
MTH = PLUGIN / "scripts" / "mth.py"
sys.path.insert(0, str(PLUGIN / "scripts"))

from mthlib import branches, changelog, commits, guard, trace  # noqa: E402
from mthlib.config import Config, DEFAULTS, _merge  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.ids import IdRegistry  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def _cfg(root: Path, **override) -> Config:
    data = _merge(DEFAULTS, {"commands": {"test": ""}, **override})
    return Config(root=root, data=data)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


class CommitMessageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _write(self.tmp / "specs/features/SPEC-0001-x.md", "# SPEC-0001 · X\n")
        self.cfg = _cfg(self.tmp)
        self.reg = IdRegistry(self.cfg, ["specs/features/SPEC-0001-x.md"])

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def errors(self, msg):
        return commits.validate(msg, self.cfg, self.reg)

    def test_valid_feature(self):
        self.assertEqual(self.errors("feat(core): add x\n\nWhy and what.\n\nRefs: SPEC-0001\n"), [])

    def test_feature_requires_refs(self):
        self.assertTrue(self.errors("feat: add x\n\nBody.\n\nRefs: n/a\n"))

    def test_undefined_ref(self):
        self.assertIn("SPEC-0002", " ".join(self.errors("fix: y\n\nBody.\n\nRefs: SPEC-0002\n")))

    def test_missing_body(self):
        self.assertTrue(any("cuerpo" in e for e in self.errors("docs: y\n\nRefs: n/a\n")))

    def test_breaking_needs_trailer(self):
        self.assertTrue(self.errors("feat!: y\n\nBody.\n\nRefs: SPEC-0001\n"))

    def test_rewrite_commits_rejected(self):
        self.assertTrue(self.errors("fixup! feat: y"))

    def test_merge_accepted(self):
        self.assertEqual(self.errors("Merge development into feat/x"), [])

    def test_build_roundtrip(self):
        msg = commits.build("feat", "a", "do x", "Because.", ["SPEC-0001", "#12"])
        self.assertEqual(self.errors(msg), [])
        self.assertEqual(commits.refs_of(msg), ["SPEC-0001", "#12"])


class BranchModelTests(unittest.TestCase):
    def setUp(self):
        self.cfg = _cfg(Path("."), branches={"extra": {"sync": {"flow": "feature"}}})

    def test_child_parent(self):
        info = branches.parse("feat/runner--fix-cleanup--test-more", self.cfg)
        self.assertEqual(info.parent, "feat/runner--fix-cleanup")
        self.assertEqual(info.top, "feat/runner")

    def test_targets(self):
        self.assertEqual(branches.target_of(branches.parse("hotfix/x", self.cfg), self.cfg), "main")
        self.assertEqual(branches.target_of(branches.parse("sync/up", self.cfg), self.cfg), "development")
        self.assertIsNone(branches.parse("release/v1.2.3", self.cfg))

    def test_invalid(self):
        for name in ("feature/x", "feat/X", "feat/a/b", "feat/a--wip-b"):
            with self.assertRaises(MthError):
                branches.parse(name, self.cfg)


class ChangelogTests(unittest.TestCase):
    def test_render_and_insert(self):
        tmp = Path(tempfile.mkdtemp())
        a, b = tmp / "feat-a.md", tmp / "fix-b.md"
        a.write_text("---\nbump: minor\nrefs: SPEC-0001\n---\n### Añadido\n- Cosa A.\n")
        b.write_text("---\nbump: patch\nrefs:\n---\n### Corregido\n- Cosa B\n  continúa.\n")
        frags = [changelog.parse(a), changelog.parse(b)]
        self.assertEqual(changelog.highest_bump(frags), "minor")
        self.assertEqual(changelog.next_version((1, 4, 2), "minor"), "1.5.0")
        section = changelog.render("1.5.0", frags)
        self.assertIn("- Cosa A. (SPEC-0001)", section)
        self.assertIn("- Cosa B continúa.", section)
        log = changelog.insert(f"# Changelog\n\n{changelog.MARKER}\n\n## [1.4.2] - x\n", section)
        self.assertLess(log.index("[1.5.0]"), log.index("[1.4.2]"))
        self.assertIn("Cosa A", changelog.section_of(log, "1.5.0"))
        shutil.rmtree(tmp)

    def test_placeholder_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "feat-a.md"
        f.write_text(changelog.template("feat", []))
        cfg = _cfg(tmp)
        errors = changelog.validate(changelog.parse(f), IdRegistry(cfg, []), True)
        self.assertTrue(any("plantilla" in e for e in errors))
        self.assertTrue(any("refs" in e for e in errors))
        shutil.rmtree(tmp)


class TraceTests(unittest.TestCase):
    def test_findings(self):
        root = Path(tempfile.mkdtemp())
        _write(root / "specs/features/SPEC-0001-a.md", """
            # SPEC-0001 · A
            - Estado: implementada
            ## Criterios de aceptación
            - **AC-01**: uno
            - **AC-02**: dos
            """)
        _write(root / "specs/adr/arq/ADR-0001-x.md", "# ADR-0001 · X\n")
        _write(root / "specs/adr/arq/ADR-0001-y.md", "# ADR-0001 · Y\n")
        _write(root / "docs/a.md", """
            # Guía
            ## F-001 · Runner de contenedores efímeros por tarea
            [ok](#f-001--runner-de-contenedores-efímeros-por-tarea)
            [mal](#no-existe) [fuera](../../otro/repo.md) [roto](nada.md) [web](https://x.y)
            Ver ADR-0009. `ADR-0010 en código inline` no cuenta como enlace.
            """)
        _write(root / "tests/test_a.py", "# verifies: SPEC-0001/AC-01\n# verifies: SPEC-0001/AC-09\n")
        files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
        found = "\n".join(str(f) for f in trace.check(_cfg(root), files))
        self.assertIn("ADR-0001 definido dos veces", found)
        self.assertIn("ancla inexistente: #no-existe", found)
        self.assertIn("enlace fuera del repositorio", found)
        self.assertIn("enlace roto: nada.md", found)
        self.assertNotIn("https://x.y", found)
        self.assertNotIn("f-001--runner", found)
        self.assertIn("referencia a ADR-0009", found)
        self.assertIn("SPEC-0001/AC-02 no tiene ningún test", found)
        self.assertIn("SPEC-0001/AC-09, que no existe", found)
        shutil.rmtree(root)


class GuardTests(unittest.TestCase):
    P = {"main", "development"}

    def blocked(self, cmd, current="feat/x"):
        return guard.violation(cmd, self.P, current) is not None

    def test_blocks(self):
        for cmd in ("git push --force", "git push origin +feat/x", "git push origin development",
                    "git rebase development", "git pull --rebase", "gh pr merge 3 --squash",
                    "git commit --no-verify -m x", "git push origin --delete feat/y",
                    "git tag -d v1.0.0", "cd x && git -C . push -f"):
            self.assertTrue(self.blocked(cmd), cmd)
        self.assertTrue(self.blocked("git commit -m x", current="development"))
        self.assertTrue(self.blocked("git push", current="main"))

    def test_allows(self):
        for cmd in ("git push -u origin feat/x", "git status && git add -A", "git rebase --abort",
                    "git commit -m 'x'", "python3 mth.py integrate --title 'git push --force'"):
            self.assertFalse(self.blocked(cmd), cmd)


class LauncherTests(unittest.TestCase):
    """The launcher must skip shims that resolve to Python < 3.11 (pyenv, venvs)."""

    def test_skips_old_python_shims(self):
        tmp = Path(tempfile.mkdtemp())
        for name in ("python3", "python3.12", "python3.13", "python3.14"):
            shim = tmp / name
            shim.write_text("#!/bin/sh\nexit 1\n")  # behaves like a pyenv shim for a missing version
            shim.chmod(0o755)
        real = shutil.which("python3.12") or shutil.which("python3.11") or sys.executable
        (tmp / "python3.11").write_text(f"#!/bin/sh\nexec {real} \"$@\"\n")
        (tmp / "python3.11").chmod(0o755)
        env = {**os.environ, "PATH": f"{tmp}:/usr/bin:/bin"}
        out = subprocess.run(["sh", str(PLUGIN / "scripts" / "mth"), "--version"], env=env,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertRegex(out.stdout.strip(), r"^\d+\.\d+\.\d+$")
        shutil.rmtree(tmp)


@unittest.skipUnless(shutil.which("git"), "git required")
class EndToEndTests(unittest.TestCase):
    """main → development → feat (+ child) → release → hotfix, against a local remote."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.remote = self.tmp / "remote.git"
        self.work = self.tmp / "work"
        bindir = self.tmp / "bin"
        bindir.mkdir()
        (bindir / "gh").write_text(f"#!/bin/sh\nexec {sys.executable} {HERE / 'fake_gh.py'} \"$@\"\n")
        (bindir / "gh").chmod(0o755)
        self.env = {**os.environ, **GIT_ENV, "PATH": f"{bindir}:{os.environ['PATH']}",
                    "FAKE_GH_STATE": str(self.tmp / "gh.json"), "FAKE_GH_REMOTE": str(self.remote),
                    "MTH_CI_POLL_SECONDS": "0", "MTH_CI_POLL_ATTEMPTS": "1"}
        self.git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=self.tmp)
        self.git("clone", "-q", str(self.remote), str(self.work), cwd=self.tmp)
        self.git("checkout", "-q", "-b", "main")
        (self.work / "README.md").write_text("# demo\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")
        self.git("push", "-q", "-u", "origin", "main")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.work, env=getattr(self, "env", {**os.environ, **GIT_ENV}),
                              check=True, capture_output=True, text=True).stdout.strip()

    def mth(self, *args, ok=True, checks="pass"):
        proc = subprocess.run([sys.executable, str(MTH), *args], cwd=self.work, capture_output=True,
                              text=True, env={**self.env, "FAKE_GH_CHECKS": checks})
        if ok and proc.returncode != 0:
            self.fail(f"mth {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}")
        if not ok:
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
        return proc.stdout + proc.stderr

    def parents(self, ref):
        return len(self.git("rev-list", "--parents", "-n", "1", ref).split()) - 1

    def test_full_flow(self):
        # Adoption on its own branch.
        self.mth("init")
        self.assertEqual(self.git("branch", "--show-current"), "chore/adopt-methodology")
        cfg_path = self.work / ".claude/methodology.toml"
        cfg = cfg_path.read_text().replace('test = ""', 'test = "true"').replace('agents = []', 'agents = ["revisor-x"]')
        cfg_path.write_text(cfg)
        _write(self.work / ".claude/agents/revisor-x.md", "---\nname: revisor-x\n---\nRevisa.\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Set test command and reviewers.", "--refs", "n/a")
        self.assertNotIn("✗", self.mth("doctor"))
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")
        self.assertEqual(self.git("branch", "--show-current"), "development")
        self.assertEqual(self.parents("origin/development"), 2)

        # Raw commit with a bad message is rejected by the commit-msg hook.
        self.mth("branch", "feat", "runner")
        (self.work / "x.txt").write_text("x")
        self.git("add", "-A")
        with self.assertRaises(subprocess.CalledProcessError):
            self.git("commit", "-m", "bad message")
        self.git("reset", "-q", "HEAD", "x.txt")
        (self.work / "x.txt").unlink()

        # Spec created inside the feature branch is linked to its fragment.
        self.mth("doc", "spec", "--title", "Ephemeral runner")
        frag = self.work / "changes/feat-runner.md"
        self.assertIn("refs: SPEC-0001", frag.read_text())
        spec = self.work / "specs/features/SPEC-0001-ephemeral-runner.md"
        spec.write_text(spec.read_text().replace("- Estado: borrador", "- Estado: implementada"))
        _write(self.work / "tests/test_runner.py", "# verifies: SPEC-0001/AC-01\ndef test_x():\n    pass\n")
        frag.write_text(frag.read_text().replace("<describe el cambio para quien usa el proyecto>",
                                                 "Runner efímero por tarea."))
        self.git("add", "-A")
        self.mth("commit", "--type", "feat", "--scope", "runner", "--summary", "add ephemeral runner",
                 "--body", "Spec, test and changelog fragment.", "--refs", "SPEC-0001")

        # Child branch integrates into its parent.
        self.mth("branch", "fix", "cleanup", "--child")
        (self.work / "cleanup.txt").write_text("c")
        self.git("add", "-A")
        self.mth("commit", "--type", "fix", "--scope", "runner", "--summary", "clean up on timeout",
                 "--body", "Teardown also on timeout.", "--refs", "SPEC-0001")
        self.mth("integrate", "--title", "fix(runner): clean up on timeout", "--summary", "Limpieza.")
        self.assertEqual(self.git("branch", "--show-current"), "feat/runner")

        # Review is mandatory and bound to the HEAD sha; red CI blocks and the run is resumable.
        out = self.mth("integrate", "--title", "feat(runner): ephemeral runner", "--summary", "S.", ok=False)
        self.assertIn("Faltan revisiones", out)
        self.mth("review", "record", "revisor-x", "--blocking", "0", "--summary", "Sin hallazgos.")
        out = self.mth("integrate", "--title", "feat(runner): ephemeral runner", "--summary", "S.",
                       ok=False, checks="fail")
        self.assertIn("CI", out)
        self.mth("integrate", "--title", "feat(runner): ephemeral runner", "--summary", "S.")
        self.assertEqual(self.git("branch", "--show-current"), "development")
        log = self.git("log", "-1", "--format=%B", "origin/development")
        self.assertIn("feat(runner): ephemeral runner (#", log)
        self.assertIn("Refs: SPEC-0001", log)
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "feat/runner"), "")

        # Release: red CI stops it; a second run resumes without creating another version.
        self.assertIn("CI", self.mth("release", ok=False, checks="fail"))
        self.assertIn("Reanudando release/v0.1.0", self.mth("release"))
        self.git("fetch", "-q", "--tags")
        self.assertIn("v0.1.0", self.git("tag", "--list"))
        self.assertEqual(self.parents("origin/main"), 2)
        changelog_text = self.git("show", "origin/main:CHANGELOG.md")
        self.assertIn("## [0.1.0]", changelog_text)
        self.assertIn("Runner efímero por tarea. (SPEC-0001)", changelog_text)
        self.assertEqual(self.git("ls-tree", "--name-only", "origin/development", "changes/"), "changes/.gitkeep")
        self.git("merge-base", "--is-ancestor", "v0.1.0", "origin/development")  # main ⊆ development

        # Hotfix.
        self.mth("branch", "hotfix", "leak", "--spec", "SPEC-0001")
        (self.work / "leak.txt").write_text("l")
        hf = self.work / "changes/hotfix-leak.md"
        hf.write_text(hf.read_text().replace("<describe el cambio para quien usa el proyecto>", "Fuga corregida."))
        self.git("add", "-A")
        self.mth("commit", "--type", "fix", "--summary", "close leaked handle", "--body", "Close on exit.",
                 "--refs", "SPEC-0001")
        self.mth("review", "record", "revisor-x", "--blocking", "0", "--summary", "OK.")
        self.mth("hotfix", "finish")
        self.git("fetch", "-q", "--tags")
        self.assertIn("v0.1.1", self.git("tag", "--list"))
        self.git("merge-base", "--is-ancestor", "v0.1.1", "origin/development")
        self.assertIn("✓ Trazabilidad OK", self.mth("trace"))
        trace_log = (self.work / ".git/mth/trace.jsonl").read_text().splitlines()
        self.assertTrue(any(json.loads(line)["event"] == "release" for line in trace_log))

    def test_fork_mode(self):
        """Upstream history, upstream tags and upstream files must not leak into the flow."""
        self.git("checkout", "-q", "-b", "up")
        (self.work / "core.py").write_text("x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Upstream change one")
        self.git("tag", "v9.9.9")
        self.git("update-ref", "refs/remotes/upstream/main", "up")
        self.git("checkout", "-q", "main")
        _write(self.work / "fork/docs/02-cambios.md", "# 02 · Cambios\n\n## F-001 · Runner\n")
        _write(self.work / "website/docs/x.md", "[roto](nada.md)\n")
        _write(self.work / "CLAUDE.md", "# Upstream rules\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fork docs")
        self.git("push", "-q", "origin", "main")
        cfg_file = self.tmp / "fork.toml"
        cfg_file.write_text(textwrap.dedent("""
            version = 1
            [commands]
            test = "true"
            [paths]
            docs = "fork/docs"
            specs = "fork/docs"
            adr = "fork/docs/adr"
            changes = "fork/changes"
            changelog = "fork/CHANGELOG.md"
            claude_md = ".claude/CLAUDE.md"
            [ids.F]
            pattern = 'F-\\d{3}'
            defined_in = ["fork/docs/02-*.md"]
            [branches.extra.sync]
            flow = "feature"
            [commits]
            external_refs = ["refs/remotes/upstream/main"]
            [review]
            required_for = []
            [ci]
            required = false
            [trace]
            acceptance = false
            spec_kind = "F"
            adr_kind = "F"
            include = ["fork/**", ".claude/**"]
            [release]
            github_release = false
            tag_prefix = "fork-v"
            """))
        self.mth("init", "--config", str(cfg_file))
        self.assertEqual((self.work / "CLAUDE.md").read_text(), "# Upstream rules\n")
        self.assertIn("claude-methodology:start", (self.work / ".claude/CLAUDE.md").read_text())
        self.assertFalse((self.work / "CHANGELOG.md").exists())
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "A.")

        # Upstream sync: thousands of non-conventional commits must not block integration.
        self.mth("branch", "sync", "upstream-1")
        self.git("merge", "--no-ff", "up", "-m", "Merge upstream/main into sync/upstream-1")
        out = self.mth("integrate", "--title", "chore(sync): merge upstream main", "--summary", "S.")
        self.assertIn("historia externa", out)

        self.mth("branch", "fix", "leak", "--spec", "F-001")
        frag = self.work / "fork/changes/fix-leak.md"
        frag.write_text(frag.read_text().replace("<describe el cambio para quien usa el proyecto>", "Fuga."))
        (self.work / "fork/leak.txt").write_text("l")
        self.git("add", "-A")
        self.mth("commit", "--type", "fix", "--summary", "close leak", "--body", "Close.", "--refs", "F-001")
        self.mth("integrate", "--title", "fix(runner): close leak", "--summary", "F.")

        # Release ignores upstream tags and does not list upstream commits.
        self.mth("release")
        self.git("fetch", "-q", "--tags")
        self.assertIn("fork-v0.0.1", self.git("tag", "--list"))
        body = self.git("log", "-1", "--format=%B", "origin/main")
        self.assertNotIn("Upstream change one", body)
        self.assertIn("fix: close leak", body)
        self.assertIn("✓ Trazabilidad OK", self.mth("trace"))  # website/ is outside trace.include

    def test_parent_blocked_by_open_child(self):
        self.mth("init")
        cfg_path = self.work / ".claude/methodology.toml"
        cfg_path.write_text(cfg_path.read_text().replace('test = ""', 'test = "true"'))
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "set test command", "--body", "Enable tests.")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "A.")
        self.mth("branch", "chore", "docs-x")
        (self.work / "docs/x.md").write_text("# X\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "docs", "--summary", "add x guide", "--body", "Guide.")
        self.mth("branch", "docs", "more", "--child")
        self.git("checkout", "-q", "chore/docs-x")
        out = self.mth("integrate", "--title", "docs: add x guide", "--summary", "S.", ok=False)
        self.assertIn("hijas sin integrar", out)

if __name__ == "__main__":
    unittest.main()
