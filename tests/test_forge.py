"""Tests of the configurable forge (SPEC-0016, ADR-0012)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import forge, guard  # noqa: E402
from mthlib.config import DEFAULTS, _merge, parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

GITLAB = "https://gitlab.com/acme/app.git"


class ForgeConfigTests(unittest.TestCase):
    def test_forge_values(self):
        # verifies: SPEC-0016/AC-01
        self.assertEqual(DEFAULTS["forge"], "github")
        for value in forge.FORGES:
            with self.subTest(forge=value):
                cfg = parse(Path("."), f'version = 1\nforge = "{value}"\n[commands]\ntest = ""\n')
                self.assertEqual(cfg.forge, value)
        self.assertEqual(parse(Path("."), 'version = 1\n[commands]\ntest = ""\n').forge, "github")
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), 'version = 1\nforge = "bitbucket"\n[commands]\ntest = ""\n')
        self.assertIn("'forge' = 'bitbucket'", ctx.exception.message)
        self.assertIsNotNone(_merge)  # the defaults merge is what makes the key optional

    def test_forge_is_deduced_from_the_host_only(self):
        # verifies: SPEC-0016/AC-02
        cases = {
            "https://github.com/acme/app.git": "github", "git@github.com:acme/app.git": "github",
            "ssh://git@github.com:22/acme/app.git": "github",
            "https://gitlab.com/acme/app.git": "gitlab", "git@gitlab.com:acme/app.git": "gitlab",
            "https://gitlab.empresa.com/acme/app.git": "gitlab",
            "https://user:s3cret@gitlab.empresa.com/acme/app.git": "gitlab",
            "https://mygitlab.com/a/b.git": "none", "https://bitbucket.org/a/b.git": "none",
            "https://github.com.evil.example/a/b.git": "none", "/srv/git/app.git": "none", "": "none", None: "none",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(forge.forge_of(url), expected)
        self.assertEqual(forge.host_of("https://user:s3cret@gitlab.empresa.com/a.git"), "gitlab.empresa.com")
        self.assertNotIn("s3cret", forge.host_of("https://user:s3cret@gitlab.empresa.com/a.git"))


class GuardTests(unittest.TestCase):
    def test_glab_merge_is_blocked_like_gh_merge(self):
        # verifies: SPEC-0016/AC-09
        protected = {"main", "development"}
        for command in ("glab mr merge 5", "gh pr merge 3 --merge", "echo x && glab mr merge 7 --squash"):
            with self.subTest(command=command):
                self.assertIn("mth integrate", guard.violation(command, protected, "feat/x") or "")
        for command in ("glab mr list", "glab mr view 5", "gh pr view 3", "glab ci status"):
            with self.subTest(command=command):
                self.assertIsNone(guard.violation(command, protected, "feat/x"))


class ManualForgeTests(unittest.TestCase):
    """An adopted repository whose remote is on GitLab: mth does the local part and never calls gh."""

    setUp_base = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth
    report = test_mth.EndToEndTests.report

    def setUp(self):
        self.setUp_base()
        self.mth("init")  # still GitHub: the fake gh merges the adoption
        cfg_path = self.work / ".claude/methodology.toml"
        cfg_path.write_text(cfg_path.read_text().replace('test = ""', 'test = "true"')
                            .replace('agents = ["verificador"]', "agents = []"))
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Set the test command.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")
        self.git("checkout", "-q", "development")
        cfg_path.write_text(cfg_path.read_text().replace('forge = "github"', 'forge = "gitlab"'))
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "use gitlab")
        self.git("push", "-q", "origin", "development")
        test_mth.set_forge_url(self, GITLAB)
        self.gh_calls = self.tmp / "gh-calls.log"  # from here on, any call to gh is a failure
        gh = self.tmp / "bin" / "gh"
        gh.write_text(f"#!/bin/sh\necho \"$@\" >> {self.gh_calls}\nexit 1\n")

    def assert_no_gh(self):
        self.assertFalse(self.gh_calls.exists(), self.gh_calls.read_text() if self.gh_calls.exists() else "")

    def person_merges(self, source: str, target: str) -> None:
        """What the person does in the forge: a merge commit of ``source`` into ``target``."""
        clone = self.tmp / "forge-ui"
        shutil.rmtree(clone, ignore_errors=True)
        self.git("clone", "-q", str(self.remote), str(clone), cwd=self.tmp)
        self.git("checkout", "-q", target, cwd=clone)
        self.git("merge", "--no-ff", "-q", "-m", f"Merge {source} into {target}", f"origin/{source}", cwd=clone)
        self.git("push", "-q", "origin", target, cwd=clone)

    def remote_files(self, ref: str, path: str) -> str:
        return self.git("ls-tree", "--name-only", f"origin/{ref}", path)

    def test_integrate_prepares_the_merge_request_and_never_merges(self):
        # verifies: SPEC-0016/AC-05
        self.mth("branch", "chore", "tidy")
        (self.work / "tidy.txt").write_text("t")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "tidy up", "--body", "Tidy.", "--refs", "n/a")
        before = self.git("rev-parse", "origin/development")
        out = self.mth("integrate", "--title", "chore: tidy up", "--summary", "Orden.")
        self.assert_no_gh()
        self.assertIn("Pasos manuales", out)
        self.assertIn("forge = gitlab", out)
        request = (self.work / ".work/merge-request/chore-tidy.md").read_text()
        self.assertTrue(request.startswith("# chore: tidy up"))
        self.assertIn("Orden.", request)
        self.assertEqual(self.git("rev-parse", "origin/development"), before)  # nothing merged
        self.assertIn("chore/tidy", self.git("ls-remote", "--heads", "origin", "chore/tidy"))  # branch is on the forge
        self.assertEqual(self.git("branch", "--show-current"), "chore/tidy")
        # Failing gates still fail: a bad title is refused before anything is prepared.
        self.assertIn("Título inválido", self.mth("integrate", "--title", "tidy up", "--summary", "x", ok=False))
        # After the person merges, running it again recognises the merge and cleans up.
        self.person_merges("chore/tidy", "development")
        self.mth("integrate", "--title", "chore: tidy up", "--summary", "Orden.")
        self.assert_no_gh()
        self.assertEqual(self.git("branch", "--show-current"), "development")
        self.assertEqual(self.git("branch", "--list", "chore/tidy"), "")

    def prepare_release(self) -> str:
        test_mth._write(self.work / "changes/feat-widget.md",
                        "---\nbump: minor\nrefs:\n---\n### Añadido\n- Widget.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "add widget fragment")
        self.git("push", "-q", "origin", "development")
        return self.mth("release")

    def test_release_prepares_the_branch_and_lists_the_manual_steps(self):
        # verifies: SPEC-0016/AC-06
        # verifies: SPEC-0016/AC-11
        out = self.prepare_release()
        self.assert_no_gh()
        self.assertIn("release/v0.1.0 preparada", out)
        for step in ("· 1.", "· 2.", "· 3.", "· 4."):
            self.assertIn(step, out)
        self.assertIn("git tag -a v0.1.0 -m v0.1.0 origin/main && git push origin v0.1.0", out)
        self.assertIn("## [0.1.0]", self.git("show", "origin/release/v0.1.0:CHANGELOG.md"))
        self.assertEqual(self.remote_files("release/v0.1.0", "changes/feat-widget.md"), "")  # folded in
        self.assertIn("Widget.", (self.work / ".work/merge-request/release-v0.1.0.md").read_text())
        self.assertNotIn("v0.1.0", self.git("ls-remote", "--tags", "origin"))  # no tag, no merge
        self.assertEqual(self.remote_files("main", "CHANGELOG.md"), "")  # main untouched

    def test_release_resumes_and_cleans_up_when_every_step_is_done(self):
        # verifies: SPEC-0016/AC-07
        self.prepare_release()
        self.person_merges("release/v0.1.0", "main")
        out = self.mth("release")
        self.assertIn("✓ 1.", out)
        self.assertIn("· 2.", out)
        self.assertIn("· 4.", out)  # main ⊆ development holds until the release is merged: not a done step
        self.git("fetch", "-q", "origin")
        self.git("tag", "-a", "v0.1.0", "-m", "v0.1.0", "origin/main")
        self.git("push", "-q", "origin", "v0.1.0")
        out = self.mth("release")
        self.assertIn("✓ 2.", out)
        self.assertIn("· 4.", out)
        self.person_merges("main", "development")
        out = self.mth("release")
        self.assert_no_gh()
        self.assertIn("publicada a mano", out)
        self.assertEqual(self.git("branch", "--show-current"), "development")
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "release/v0.1.0"), "")
        self.assertEqual(self.remote_files("development", "changes/feat-widget.md"), "")

    def test_hotfix_finish_refuses_before_touching_anything(self):
        # verifies: SPEC-0016/AC-08
        self.git("checkout", "-q", "-b", "hotfix/leak")  # cut from development here: main has no configuration yet
        status, head = self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")
        out = self.mth("hotfix", "finish", ok=False)
        self.assertIn("forge = gitlab", out)
        self.assertEqual((self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")), (status, head))
        self.assert_no_gh()

    def test_doctor_does_not_ask_for_gh_or_ci(self):
        # verifies: SPEC-0016/AC-10
        out = self.mth("doctor")
        self.assertNotIn("✗", out)
        self.assertNotIn("gh instalado", out)
        self.assertNotIn("ci.required", out)
        self.assertIn("forge = gitlab", out)


class InitDetectsTheForgeTests(unittest.TestCase):
    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def test_plain_init_writes_the_deduced_forge(self):
        # verifies: SPEC-0016/AC-03
        test_mth.set_forge_url(self, GITLAB)
        self.mth("init")
        cfg = tomllib.loads((self.work / ".claude/methodology.toml").read_text())
        self.assertEqual(cfg["forge"], "gitlab")
        self.assertFalse(cfg["ci"]["required"])


if __name__ == "__main__":
    unittest.main()
