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

    def test_forge_rejects_other_spellings_and_types(self):
        # verifies: SPEC-0016/AC-01
        for literal in ('"GitHub"', '"gitlab "', '""', "1", "true"):
            with self.subTest(value=literal), self.assertRaises(MthError) as ctx:
                parse(Path("."), f'version = 1\nforge = {literal}\n[commands]\ntest = ""\n')
            self.assertIn("forge", ctx.exception.message)

    def test_forge_deduction_ignores_case_ports_and_bare_scp_hosts(self):
        # verifies: SPEC-0016/AC-02
        cases = {"https://GitLab.COM/a/b.git": "gitlab", "ssh://git@gitlab.empresa.com:2222/a/b.git": "gitlab",
                 "gitlab.com:a/b.git": "gitlab", "https://tok:x@GITHUB.com/a/b": "github",
                 "ssh://git@bitbucket.org:7999/a/b.git": "none", "gitlab:a/b.git": "gitlab"}
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(forge.forge_of(url), expected)
        self.assertEqual(forge.host_of("ssh://git@gitlab.empresa.com:2222/a/b.git"), "gitlab.empresa.com")

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
        for command in ("glab mr merge 5", "glab mr accept 5", "gh pr merge 3 --merge", "echo x && glab mr merge 7 --squash"):
            with self.subTest(command=command):
                self.assertIn("mth integrate", guard.violation(command, protected, "feat/x") or "")
        for command in ("glab mr list", "glab mr view 5", "gh pr view 3", "glab ci status"):
            with self.subTest(command=command):
                self.assertIsNone(guard.violation(command, protected, "feat/x"))


    def test_glab_merge_is_blocked_after_any_separator_and_other_glab_commands_pass(self):
        # verifies: SPEC-0016/AC-09
        protected = {"main", "development"}
        for command in ("glab mr merge", "cd repo; glab mr merge 5", "make test || glab mr merge 5", "true | glab mr accept 5"):
            with self.subTest(command=command):
                self.assertIn("mth integrate", guard.violation(command, protected, "feat/x") or "")
        for command in ("glab mr create --fill", "glab mr approve 5", "glab auth status", "echo glab mr merge"):
            with self.subTest(command=command):
                self.assertIsNone(guard.violation(command, protected, "feat/x"))


class MergeBypassTests(unittest.TestCase):
    PROTECTED = {"main", "development"}

    def blocked(self, command: str) -> bool:
        return "mth integrate" in (guard.violation(command, self.PROTECTED, "feat/x") or "")

    def test_a_merge_by_hand_is_blocked_however_it_is_spelled(self):
        # verifies: SPEC-0016/AC-12
        for command in ("gh -R owner/repo pr merge 3", "glab --repo owner/repo mr merge 5", "gh --hostname h pr merge 3",
                        "gh pr -R owner/repo merge 3", "sudo -u root gh pr merge 3", "env -i GH_TOKEN=x gh pr merge 3",
                        "command gh pr merge 3", "setsid glab mr accept 5"):
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command))

    def test_a_merge_inside_a_shell_construct_is_blocked(self):
        # verifies: SPEC-0016/AC-12
        for command in ("(gh pr merge 3)", "{ gh pr merge 3; }", "true && if x; then gh pr merge 3; fi", "`gh pr merge 3`",
                        "gh pr \\\nmerge 3"):
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command))

    def test_a_merge_through_the_api_is_blocked_unless_it_is_a_plain_read(self):
        # verifies: SPEC-0016/AC-12
        for command in ("gh api -X PUT repos/o/r/pulls/3/merge", "gh api -XPUT repos/o/r/pulls/3/merge",
                        "glab api projects/1/merge_requests/1/merge --method=put",
                        "gh api repos/o/r/pulls/3/merge -X GET -X PUT", "gh api repos/o/r/merges -f base=a -f head=b",
                        "gh api repos/o/r/pulls/3/merge?x=1 -fsha=abc", "gh api repos/o/r/pulls/3/merge -Fsha=abc",
                        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
                        "gh api graphql -F query=@merge.graphql"):
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command))

    def test_reads_and_other_subcommands_still_pass(self):
        # verifies: SPEC-0016/AC-12
        for command in ("gh -R owner/repo pr view 3", "gh pr -R owner/repo view 3", "glab -R owner/repo mr list",
                        "sudo -u x ls", "command -v gh", "echo gh pr merge 3", "git log --merges",
                        "gh api repos/o/r/pulls", "gh api repos/o/r/pulls/3/merge", "gh api repos/o/r/pulls/3/merge -X get"):
            with self.subTest(command=command):
                self.assertIsNone(guard.violation(command, self.PROTECTED, "feat/x"))


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

    def test_release_resumes_when_the_forge_deleted_the_release_branch(self):
        # verifies: SPEC-0016/AC-07
        self.prepare_release()
        self.person_merges("release/v0.1.0", "main")
        self.git("push", "-q", "origin", "--delete", "release/v0.1.0")  # the forge removes the source branch on merge
        self.git("checkout", "-q", "development")
        self.git("branch", "-D", "release/v0.1.0")
        out = self.mth("release")
        self.assertIn("Reanudando la publicación manual de v0.1.0", out)
        self.assertIn("✓ 1.", out)
        self.assertIn("· 2.", out)
        self.assertNotIn("No hay fragmentos", out)
        self.git("fetch", "-q", "origin")
        self.git("tag", "-a", "v0.1.0", "-m", "v0.1.0", "origin/main")
        self.git("push", "-q", "origin", "v0.1.0")
        self.person_merges("main", "development")
        self.assertIn("nada que publicar", self.mth("release", ok=False))  # everything is done: no new version either
        self.assert_no_gh()
        self.assertEqual(self.git("branch", "--show-current"), "development")

    def test_an_old_untagged_version_in_main_does_not_hold_back_a_new_release(self):
        # verifies: SPEC-0016/AC-07
        self.prepare_release()
        self.person_merges("release/v0.1.0", "main")
        self.git("fetch", "-q", "origin")
        self.git("tag", "-a", "v0.5.0", "-m", "v0.5.0", "origin/main")  # newer than the untagged 0.1.0 in the changelog
        self.git("push", "-q", "origin", "v0.5.0")
        self.git("push", "-q", "origin", "--delete", "release/v0.1.0")  # the forge removed the branch on merge
        self.person_merges("main", "development")
        self.git("checkout", "-q", "development")
        self.git("pull", "-q", "--ff-only", "origin", "development")
        test_mth._write(self.work / "changes/feat-gadget.md", "---\nbump: minor\nrefs:\n---\n### Añadido\n- Gadget.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "add gadget fragment")
        self.git("push", "-q", "origin", "development")
        out = self.mth("release")
        self.assertNotIn("Reanudando la publicación manual", out)
        self.assertIn("release/v0.6.0 preparada", out)
        self.assert_no_gh()

    def test_a_tag_that_is_not_published_on_main_does_not_count(self):
        # verifies: SPEC-0016/AC-07
        self.prepare_release()
        self.person_merges("release/v0.1.0", "main")
        self.git("fetch", "-q", "origin")
        self.git("tag", "-a", "v0.1.0", "-m", "v0.1.0", "origin/main")  # created, not pushed
        self.assertIn("· 2.", self.mth("release"))
        self.git("tag", "-d", "v0.1.0")
        stray = self.git("commit-tree", "-m", "stray", self.git("rev-parse", "origin/main^{tree}"))
        self.git("tag", "-a", "v0.1.0", "-m", "v0.1.0", stray)  # pushed, but not part of main
        self.git("push", "-q", "origin", "v0.1.0")
        self.assertIn("· 2.", self.mth("release"))
        self.person_merges("main", "development")
        self.assertNotIn("publicada a mano", self.mth("release"))  # still no valid tag: nothing is cleaned up
        self.assertNotEqual(self.git("ls-remote", "--heads", "origin", "release/v0.1.0"), "")

    def test_hotfix_finish_refuses_before_touching_anything(self):
        # verifies: SPEC-0016/AC-08
        self.git("checkout", "-q", "-b", "hotfix/leak")  # cut from development here: main has no configuration yet
        status, head = self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")
        out = self.mth("hotfix", "finish", ok=False)
        self.assertIn("forge = gitlab", out)
        self.assertEqual((self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")), (status, head))
        self.assert_no_gh()

    def use_forge_none(self) -> None:
        cfg_path = self.work / ".claude/methodology.toml"
        cfg_path.write_text(cfg_path.read_text().replace('forge = "gitlab"', 'forge = "none"'))
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "use no forge")
        self.git("push", "-q", "origin", "development")

    def test_integrate_without_a_forge_prepares_the_request_and_never_merges(self):
        # verifies: SPEC-0016/AC-05
        self.use_forge_none()
        self.mth("branch", "chore", "tidy")
        (self.work / "tidy.txt").write_text("t")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "tidy up", "--body", "Tidy.", "--refs", "n/a")
        before = self.git("rev-parse", "origin/development")
        out = self.mth("integrate", "--title", "chore: tidy up", "--summary", "Orden.")
        self.assert_no_gh()
        self.assertIn("forge = none", out)
        self.assertIn("Orden.", (self.work / ".work/merge-request/chore-tidy.md").read_text())
        self.assertEqual(self.git("rev-parse", "origin/development"), before)
        self.person_merges("chore/tidy", "development")
        self.mth("integrate", "--title", "chore: tidy up", "--summary", "Orden.")
        self.assertEqual(self.git("branch", "--list", "chore/tidy"), "")

    def test_release_without_a_forge_lists_the_manual_steps(self):
        # verifies: SPEC-0016/AC-06
        self.use_forge_none()
        out = self.prepare_release()
        self.assert_no_gh()
        self.assertIn("release/v0.1.0 preparada", out)
        self.assertIn("forge = none", out)
        self.assertIn("## [0.1.0]", self.git("show", "origin/release/v0.1.0:CHANGELOG.md"))
        self.assertIn("Widget.", (self.work / ".work/merge-request/release-v0.1.0.md").read_text())
        self.assertNotIn("v0.1.0", self.git("ls-remote", "--tags", "origin"))

    def test_hotfix_finish_without_a_forge_refuses_before_touching_anything(self):
        # verifies: SPEC-0016/AC-08
        self.use_forge_none()
        self.git("checkout", "-q", "-b", "hotfix/leak")
        status, head = self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")
        self.assertIn("forge = none", self.mth("hotfix", "finish", ok=False))
        self.assertEqual((self.git("status", "--porcelain"), self.git("rev-parse", "HEAD")), (status, head))
        self.assert_no_gh()

    def test_doctor_does_not_ask_for_gh_or_ci(self):
        # verifies: SPEC-0016/AC-10
        out = self.mth("doctor")
        self.assertNotIn("✗", out)
        self.assertNotIn("gh instalado", out)
        self.assertNotIn("ci.required", out)
        self.assertIn("forge = gitlab", out)


class GithubDoctorTests(unittest.TestCase):
    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def test_doctor_keeps_asking_for_gh_and_ci_with_github(self):
        # verifies: SPEC-0016/AC-10
        self.mth("init")  # the remote is named as GitHub: forge = github, and there are no workflows
        out = self.mth("doctor")
        self.assertIn("gh instalado y autenticado", out)
        self.assertIn("ci.required = true", out)
        self.assertNotIn("forge =", out)


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
