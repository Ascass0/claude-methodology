"""Tests of the decisions around the secrets hook and workflow: gaps, doctor and interview (SPEC-0024)."""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import catalog_support as support  # noqa: E402
import test_adoption  # noqa: E402
import test_mth  # noqa: E402
from mthlib import adoption, secretci, setup, survey, update  # noqa: E402
from test_secrets import install_fake  # noqa: E402
from test_update import UpdateTestCase  # noqa: E402

UNDECIDED = support.template_with_agents().replace('mode = ""', 'mode = "off"', 1)


def decided(**keys: str) -> str:
    """The update-test configuration with ``secrets.hook`` and ``secrets.ci`` set as given."""
    text = UNDECIDED
    for key in ("hook", "ci"):
        text = text.replace(f'\n{key} = ""', f'\n{key} = "{keys.get(key, "off")}"', 1)
    return text


class GapTests(UpdateTestCase):
    config_text = UNDECIDED

    def test_undecided_pieces_are_decision_gaps_and_decided_ones_are_not(self):
        # verifies: SPEC-0024/AC-12
        gaps = self.ids()
        self.assertEqual(gaps["secretos-hook"].clase, update.DECISION)
        self.assertEqual(gaps["secretos-ci"].clase, update.DECISION)
        for value in ("off", "on"):
            self.write(".claude/methodology.toml", decided(hook=value, ci=value))
            self.assertNotIn("secretos-hook", self.ids())
            self.assertNotIn("secretos-ci", self.ids())

    def test_the_ci_decision_is_only_asked_with_github_and_a_required_ci(self):
        # verifies: SPEC-0024/AC-12
        self.write(".claude/methodology.toml", UNDECIDED.replace('forge = "github"', 'forge = "gitlab"'))
        self.assertNotIn("secretos-ci", self.ids())
        self.write(".claude/methodology.toml", UNDECIDED.replace("required = true", "required = false", 1))
        self.assertNotIn("secretos-ci", self.ids())

    def test_a_decided_hook_and_workflow_that_are_missing_are_automatic_gaps(self):
        # verifies: SPEC-0024/AC-13
        self.write(".claude/methodology.toml", decided(hook="on", ci="on"))
        repo = self.up_to_date()
        gaps = self.ids(repo)
        self.assertEqual(gaps["secretos-workflow"].clase, update.AUTOMATIC)
        self.assertIn("hook pre-commit absent", gaps["hook"].evidence)
        setup.sync_secrets_hook(repo.git, repo.cfg)
        setup.sync_secrets_workflow(self.root, repo.cfg)
        fixed = self.ids(self.repo())
        self.assertNotIn("secretos-workflow", fixed)
        self.assertNotIn("hook", fixed)

    def test_an_outdated_workflow_is_a_gap_and_a_foreign_one_is_left_alone(self):
        # verifies: SPEC-0024/AC-13
        self.write(".claude/methodology.toml", decided(ci="on"))
        repo = self.up_to_date()
        setup.sync_secrets_workflow(self.root, repo.cfg)
        path = self.root / secretci.WORKFLOW
        path.write_text(path.read_text().replace("8.30.1", "8.0.0"), encoding="utf-8")
        self.assertIn("stale", self.ids(self.repo())["secretos-workflow"].evidence)
        path.write_text("name: mine\n", encoding="utf-8")
        self.assertNotIn("secretos-workflow", self.ids(self.repo()))


class DoctorTests(unittest.TestCase):
    setUp_e2e = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def setUp(self):
        self.setUp_e2e()
        self.fake = install_fake(self.tmp / "fakebin")
        self.env = {**self.env, "FAKE_GITLEAKS_LOG": str(self.tmp / "gitleaks.log"), "FAKE_GITLEAKS_MODE": "clean"}
        self.mth("init")
        cfg = self.work / ".claude/methodology.toml"  # the local remote is not GitHub: declare it, with a required CI
        text = re.sub(r'(?m)^forge = "[^"]*"', 'forge = "github"', cfg.read_text())
        cfg.write_text(re.sub(r"required = false[^\n]*", "required = true", text, count=1))

    def set_key(self, key: str, value: str) -> None:
        cfg = self.work / ".claude/methodology.toml"
        cfg.write_text(re.sub(rf'(\n{key} = )"[^"]*"', rf'\1"{value}"', cfg.read_text(), count=1))

    def with_tool(self, version: str = "8.30.1") -> None:
        self.env = {**self.env, "PATH": f"{self.fake}:{self.env['PATH']}", "FAKE_GITLEAKS_VERSION": version}

    def test_undecided_pieces_warn_and_never_block(self):
        # verifies: SPEC-0024/AC-14
        out = self.mth("doctor")
        self.assertIn("⚠ secrets.hook sin decidir", out)
        self.assertIn("⚠ secrets.ci sin decidir", out)

    def test_hook_on_without_the_tool_is_blocking_and_a_missing_hook_or_workflow_warns(self):
        # verifies: SPEC-0024/AC-14
        self.set_key("hook", "on")
        self.set_key("ci", "on")
        self.assertIn("✗ gitleaks instalado", self.mth("doctor", ok=False))
        self.with_tool()
        (self.work / ".git/hooks/pre-commit").unlink(missing_ok=True)
        (self.work / secretci.WORKFLOW).unlink(missing_ok=True)
        out = self.mth("doctor")
        self.assertIn("⚠ Hook pre-commit de secretos: absent", out)
        self.assertIn("⚠ Workflow de secretos: absent", out)
        (self.work / secretci.WORKFLOW).parent.mkdir(parents=True, exist_ok=True)
        (self.work / secretci.WORKFLOW).write_text("name: mine\n")
        self.assertIn("⚠ Workflow de secretos: foreign", self.mth("doctor"))

    def test_an_old_gitleaks_warns(self):
        # verifies: SPEC-0024/AC-14
        self.set_key("hook", "on")
        self.with_tool("8.18.4")
        self.assertIn("⚠ gitleaks 8.18.4 · PATH (mínima 8.19.0)", self.mth("doctor"))
        self.with_tool("8.30.1")
        self.assertIn("✓ gitleaks 8.30.1 · PATH (mínima 8.19.0)", self.mth("doctor"))


class InterviewTests(unittest.TestCase):
    survey_of = test_adoption.AnswersTests.survey_of
    config = test_adoption.AnswersTests.config

    def test_the_question_is_a_decision_in_every_profile_with_three_options(self):
        # verifies: SPEC-0024/AC-15
        for profile in survey.PROFILES:
            inventory = self.survey_of(profile)
            question = next(q for q in inventory.questions if q["id"] == "secretos")
            self.assertEqual(question["outcome"], survey.DECISION, profile)
        self.assertEqual(set(adoption.OPTIONS["secretos"]), {"bloquear", "integrar", "ninguno"})

    def test_a_new_repo_asks_at_most_six_questions(self):
        # verifies: SPEC-0024/AC-15
        inventory = self.survey_of("new", ci=False)
        self.assertLessEqual(len(inventory.asked()), 6)
        self.assertIn("secretos", inventory.asked())

    def test_each_option_sets_the_keys_without_activating_anything_silently(self):
        # verifies: SPEC-0024/AC-15
        inventory = self.survey_of("new", ci=True)
        base = {q: test_adoption.DEFAULT_ANSWERS[q] for q in inventory.asked() if q != "secretos"}
        effects = {"bloquear": ("block", "on", "on"), "integrar": ("block", "off", "off"), "ninguno": ("off", "off", "off")}
        for option, (mode, hook, ci) in effects.items():
            cfg = self.config(inventory, {**base, "secretos": {"option": option}})
            self.assertEqual((cfg["secrets"]["mode"], cfg["secrets"]["hook"], cfg["secrets"]["ci"]), (mode, hook, ci), option)

    def test_bloquear_leaves_the_ci_undecided_when_github_ci_does_not_apply(self):
        # verifies: SPEC-0024/AC-15
        inventory = self.survey_of("new", forge="gitlab")
        base = {q: test_adoption.DEFAULT_ANSWERS[q] for q in inventory.asked() if q != "secretos"}
        cfg = self.config(inventory, {**base, "secretos": {"option": "bloquear"}})
        self.assertEqual((cfg["secrets"]["hook"], cfg["secrets"]["ci"]), ("on", ""))


class DocsTests(unittest.TestCase):
    def test_readme_and_skills_document_the_pieces_and_the_branch_protection(self):
        # verifies: SPEC-0024/AC-16
        # verifies: SPEC-0024/FM-08
        plugin = HERE.parent / "plugins" / "methodology" / "skills"
        readme = (HERE.parent / "README.md").read_text(encoding="utf-8")
        for needle in ("secrets.hook", "secrets.ci", "hooks.pre_commit", "mth secrets --staged", "secrets.yml",
                       "secretos-hook", "secretos-ci", "Protección de rama"):
            self.assertIn(needle, readme)
        self.assertIn("## `secretos`", (plugin / "mth-init" / "preguntas.md").read_text(encoding="utf-8"))
        self.assertIn("secretos", (plugin / "mth-init" / "SKILL.md").read_text(encoding="utf-8"))
        update_skill = (plugin / "mth-update" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("secretos-hook", update_skill)
        self.assertIn("secretos-ci", update_skill)


if __name__ == "__main__":
    unittest.main()
