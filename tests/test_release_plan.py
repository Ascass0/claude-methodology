"""Tests of the autonomous release decision (SPEC-0017, ADR-0013)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import changelog, lang, releaseplan  # noqa: E402

SKILLS = HERE.parent / "plugins" / "methodology" / "skills"


def fragment(name: str, bump: str, **sections) -> changelog.Fragment:
    return changelog.Fragment(path=Path(name), bump=bump, refs=[], sections=sections or {"Añadido": ["x"]})


class MinimumBumpTests(unittest.TestCase):
    def test_minimum_by_type_and_removals(self):
        # verifies: SPEC-0017/AC-01
        pre, stable = (0, 10, 0), (1, 2, 0)
        cases = [
            (fragment("feat-a.md", "minor"), pre, "minor"), (fragment("fix-a.md", "patch", Corregido=["x"]), pre, "patch"),
            (fragment("hotfix-a.md", "patch", Corregido=["x"]), stable, "patch"),
            (fragment("security-a.md", "patch", Seguridad=["x"]), stable, "patch"),
            (fragment("fix-a.md", "patch", Eliminado=["una opción"]), pre, "minor"),
            (fragment("feat-a.md", "minor", Eliminado=["una opción"]), stable, "major"),
        ]
        for frag, current, expected in cases:
            with self.subTest(name=frag.path.name, current=current):
                self.assertEqual(changelog.minimum_bump(frag, current)[0], expected)
        english = fragment("fix-a.md", "patch", Removed=["an option"])
        self.assertEqual(changelog.minimum_bump(english, stable, lang.EN)[0], "major")
        errors = changelog.bump_errors(fragment("feat-a.md", "patch"), pre)
        self.assertEqual(len(errors), 1)
        for text in ("feat-a.md", "'patch'", "'minor'", "tipo feat"):
            self.assertIn(text, errors[0])
        self.assertIn("elimina funcionalidad", changelog.bump_errors(fragment("fix-b.md", "patch", Eliminado=["x"]), pre)[0])
        self.assertEqual(changelog.bump_errors(fragment("feat-a.md", "major"), pre), [])  # above the minimum is respected


class DecisionTests(unittest.TestCase):
    def test_the_four_decisions(self):
        # verifies: SPEC-0017/AC-04
        latest = (0, 10, 0)
        skip = releaseplan.decide([], latest, [])
        self.assertEqual(skip.decision, releaseplan.SKIP)
        self.assertIn("no versiona", skip.reasons[0])
        blocked = releaseplan.decide([fragment("feat-a.md", "patch")], latest, [])
        self.assertEqual(blocked.decision, releaseplan.BLOCKED)
        wait = releaseplan.decide([fragment("feat-a.md", "minor")], latest, ["feat/otra", "fix/b"])
        self.assertEqual(wait.decision, releaseplan.WAIT)
        self.assertIn("feat/otra, fix/b", wait.reasons[0])
        go = releaseplan.decide([fragment("feat-a.md", "minor"), fragment("fix-b.md", "patch", Corregido=["x"])], latest, [])
        self.assertEqual((go.decision, go.level, go.version), (releaseplan.PUBLISH, "minor", "0.11.0"))
        patch_only = releaseplan.decide([fragment("fix-b.md", "patch", Corregido=["x"])], latest, [])
        self.assertEqual((patch_only.level, patch_only.version), ("patch", "0.10.1"))
        text = "\n".join(go.lines())
        for expected in ("feat-a.md: minor", "Nivel: minor → versión 0.11.0 (última: 0.10.0)", "Decisión: publicar"):
            self.assertIn(expected, text)

    def test_one_dot_zero_needs_an_explicit_decision(self):
        # verifies: SPEC-0017/AC-05
        major = [fragment("feat-a.md", "major")]
        blocked = releaseplan.decide(major, (0, 9, 0), [])
        self.assertEqual((blocked.decision, blocked.version), (releaseplan.BLOCKED, "1.0.0"))
        self.assertIn("--allow-major", blocked.reasons[0])
        allowed = releaseplan.decide(major, (0, 9, 0), [], allow_major=True)
        self.assertEqual((allowed.decision, allowed.version), (releaseplan.PUBLISH, "1.0.0"))
        self.assertEqual(releaseplan.decide(major, (1, 2, 0), []).version, "2.0.0")  # already stable: no gate


class ReleasePlanFlowTests(unittest.TestCase):
    """An adopted repository (GitHub, fake gh): the decision as the agent runs it after an integration."""

    setUp_base = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def setUp(self):
        self.setUp_base()
        self.mth("init")
        cfg_path = self.work / ".claude/methodology.toml"
        cfg_path.write_text(cfg_path.read_text().replace('test = ""', 'test = "true"')
                            .replace('agents = ["verificador"]', "agents = []"))
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Set the test command.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")

    def add_fragment(self, name: str, bump: str, section: str = "Añadido") -> None:
        test_mth._write(self.work / f"changes/{name}.md", f"---\nbump: {bump}\nrefs:\n---\n### {section}\n- Cambio.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", f"add {name} fragment")
        self.git("push", "-q", "origin", "development")

    def state(self) -> tuple:
        return (self.git("status", "--porcelain"), self.git("branch", "-a"), self.git("tag", "--list"),
                self.git("rev-parse", "HEAD"))

    def test_integrate_and_release_refuse_a_level_below_the_minimum(self):
        # verifies: SPEC-0017/AC-02
        self.mth("branch", "feat", "widget")
        test_mth._write(self.work / "changes/feat-widget.md", "---\nbump: patch\nrefs:\n---\n### Añadido\n- Widget.\n")
        (self.work / "w.txt").write_text("w")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add widget", "--body", "Widget.", "--refs", "n/a")
        out = self.mth("integrate", "--title", "feat(widget): add widget", "--summary", "S.", ok=False)
        self.assertIn("bump 'patch' por debajo del mínimo 'minor' (tipo feat)", out)
        self.git("checkout", "-q", "development")
        self.add_fragment("feat-gadget", "patch")
        before = self.state()
        out = self.mth("release", ok=False)
        self.assertIn("por debajo del mínimo", out)
        self.assertEqual(self.state(), before)  # no release branch was created

    def test_plan_reads_and_decides_without_writing(self):
        # verifies: SPEC-0017/AC-03
        self.add_fragment("feat-gadget", "minor")
        self.add_fragment("fix-leak", "patch", "Corregido")
        before = self.state()
        out = self.mth("release", "--plan")
        self.assertEqual(self.state(), before)
        for expected in ("Fragmentos (2):", "feat-gadget.md: minor", "fix-leak.md: patch",
                         "Nivel: minor → versión 0.1.0 (última: 0.0.0)", "Decisión: publicar"):
            self.assertIn(expected, out)
        self.git("checkout", "-q", "-b", "chore/elsewhere")
        self.assertIn("se ejecuta desde development", self.mth("release", "--plan", ok=False))

    def test_plan_waits_for_open_work_and_skips_maintenance(self):
        # verifies: SPEC-0017/AC-04
        self.assertIn("Decisión: no publicar", self.mth("release", "--plan"))
        self.assertIn("nada que publicar", self.mth("release", ok=False))
        self.add_fragment("feat-gadget", "minor")
        self.mth("branch", "feat", "later")
        self.git("checkout", "-q", "development")
        (self.work / "changes/feat-later.md").unlink()  # the branch's own, untracked fragment stays behind
        out = self.mth("release", "--plan")
        self.assertIn("Decisión: esperar", out)
        self.assertIn("feat/later", out)

    def test_major_before_one_dot_zero_is_blocked_unless_allowed(self):
        # verifies: SPEC-0017/AC-05
        self.add_fragment("feat-big", "major")
        out = self.mth("release", "--plan")
        self.assertIn("Decisión: bloqueado", out)
        self.assertIn("--allow-major", out)
        self.assertIn("Publicación bloqueada", self.mth("release", ok=False))
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "release/v1.0.0"), "")
        self.mth("release", "--allow-major")
        self.git("fetch", "-q", "--tags")
        self.assertIn("v1.0.0", self.git("tag", "--list"))

    def test_release_publishes_what_the_plan_proposed_and_traces_it(self):
        # verifies: SPEC-0017/AC-06
        self.add_fragment("feat-gadget", "minor")
        proposed = [line for line in self.mth("release", "--plan").splitlines() if line.startswith("Nivel:")][0]
        self.assertIn("versión 0.1.0", proposed)
        self.mth("release")
        self.git("fetch", "-q", "--tags")
        self.assertIn("v0.1.0", self.git("tag", "--list"))
        events = [json.loads(line) for line in (self.work / ".git/mth/trace.jsonl").read_text().splitlines()]
        plans = [e for e in events if e["event"] == "release.plan"]
        self.assertTrue(plans)
        self.assertEqual((plans[-1]["decision"], plans[-1]["version"]), ("publicar", "0.1.0"))
        self.assertTrue(plans[-1]["reasons"])


class ReleaseFailureModeTests(ReleasePlanFlowTests):
    """Failure modes of the decision; the base tests do not run again here."""

    test_integrate_and_release_refuse_a_level_below_the_minimum = None
    test_plan_reads_and_decides_without_writing = None
    test_plan_waits_for_open_work_and_skips_maintenance = None
    test_major_before_one_dot_zero_is_blocked_unless_allowed = None
    test_release_publishes_what_the_plan_proposed_and_traces_it = None

    def test_unreadable_remote_branches_are_not_a_reason_to_wait(self):
        # verifies: SPEC-0017/AC-04
        from unittest import mock
        from mthlib import flow
        from mthlib.errors import MthError
        ctx = mock.Mock()
        ctx.cfg.development, ctx.cfg.main = "development", "main"
        ctx.git.remote_branches.side_effect = MthError("git no responde")
        with mock.patch.object(flow, "warn") as warned:
            self.assertEqual(flow._open_work(ctx), [])
        self.assertIn("se decide sin ellas", warned.call_args.args[0])

    def test_invalid_fragments_stop_the_decision(self):
        # verifies: SPEC-0017/AC-03
        missing = "SPEC-" + "9999"  # not written whole: trace would flag it as a dangling reference
        test_mth._write(self.work / "changes/feat-gadget.md", f"---\nbump: minor\nrefs: {missing}\n---\n### Añadido\n- Cambio.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "add invalid fragment")
        self.git("push", "-q", "origin", "development")
        for args in (("release", "--plan"), ("release",)):
            with self.subTest(args=args):
                out = self.mth(*args, ok=False)
                self.assertIn("Fragmentos inválidos", out)
                self.assertNotIn("Decisión:", out)
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "release/*"), "")


class SkillTests(unittest.TestCase):
    def test_skills_document_the_autonomous_decision(self):
        # verifies: SPEC-0017/AC-07
        for name in ("mth-release", "mth-develop"):
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name):
                self.assertIn("mth release --plan", text)
                for decision in ("publicar", "esperar", "no publicar", "bloqueado"):
                    self.assertIn(decision, text)
        self.assertIn("--allow-major", (SKILLS / "mth-release/SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
