"""Tests of the agreed-plans commands and gate (SPEC-0023, ADR-0021) on a repo with a local remote."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import catalog_support as support  # noqa: E402
import test_mth  # noqa: E402  (module import: its test classes are not collected twice)
from mthlib import update  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_plans import text as plan_text  # noqa: E402
from test_update import UpdateTestCase  # noqa: E402

BASE = 'version = 1\n[commands]\ntest = ""\n'


def set_required(text: str, table: str, value: str) -> str:
    """``required_for = value`` inside ``[table]`` (line by line: a table may hold lists before it)."""
    lines, current = text.splitlines(), ""
    for i, line in enumerate(lines):
        if line.startswith("["):
            current = line.strip("[] \n")
        elif current == table and line.startswith("required_for ="):
            lines[i] = f"required_for = {value}"
    return "\n".join(lines) + "\n"


class ConfigTests(unittest.TestCase):
    def test_defaults_and_unknown_kinds(self):
        # verifies: SPEC-0023/AC-01
        cfg = parse(Path("."), BASE)
        self.assertEqual(cfg["plans"]["required_for"], ["feat", "fix", "hotfix"])
        self.assertEqual(cfg["roles"]["planner"], "")
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), BASE + '[plans]\nrequired_for = ["feat", "bogus"]\n')
        self.assertIn("plans.required_for", ctx.exception.message)
        parse(Path("."), BASE + '[branches.extra.sync]\nflow = "feature"\n[plans]\nrequired_for = ["sync"]\n')
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), BASE + "[roles]\nplanner = 3\n")
        self.assertIn("roles.planner", ctx.exception.message)

    def test_the_template_names_the_planner_and_the_default_kinds(self):
        # verifies: SPEC-0023/AC-01
        cfg = parse(Path("."), support.template_with_agents())
        self.assertEqual(cfg["roles"]["planner"], "planificador")
        self.assertEqual(cfg["plans"]["required_for"], ["feat", "fix", "hotfix"])


class GateFlowTests(unittest.TestCase):
    setUp_e2e = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def setUp(self):
        self.setUp_e2e()
        self.mth("init")
        cfg = self.work / ".claude/methodology.toml"
        text = cfg.read_text().replace('test = ""', 'test = "true"').replace('agents = ["verificador"]', "agents = []")
        cfg.write_text(set_required(set_required(text, "changes", "[]"), "review", "[]"))  # only the plan gate is under test
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Set the test command.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")  # chore: no plan
        self.plans = self.work / ".work" / "plans"

    def plan_file(self, number: int = 1, state: str = "borrador", branch: str = "—") -> Path:
        path = next(self.plans.glob(f"PLAN-{number:04d}-*.md"), None) or self.plans / f"PLAN-{number:04d}-demo.md"
        path.write_text(plan_text(state, branch=branch).replace("PLAN-0001", f"PLAN-{number:04d}"), encoding="utf-8")
        return path

    def agreed_plan(self, number: int = 1) -> str:
        self.mth("plan", "new", "demo", "--title", "Demo")
        self.plan_file(number)
        self.mth("plan", "agree", f"PLAN-{number:04d}")
        return f"PLAN-{number:04d}"

    def test_plan_commands(self):
        # verifies: SPEC-0023/AC-02
        # verifies: SPEC-0023/AC-03
        # verifies: SPEC-0023/AC-04
        # verifies: SPEC-0023/AC-06
        # verifies: SPEC-0023/AC-07
        self.assertIn("No hay planes", self.mth("plan", "list"))
        self.assertIn("PLAN-0001-demo.md", self.mth("plan", "new", "demo", "--title", "Demo plan"))
        self.assertIn("PLAN-0002-otro.md", self.mth("plan", "new", "otro"))
        self.assertIn("PLAN-0001 · borrador · Demo plan", self.mth("plan", "list"))
        self.assertIn("# PLAN-0001 · Demo plan", self.mth("plan", "show", "PLAN-0001"))
        self.assertIn("no se puede acordar", self.mth("plan", "agree", "PLAN-0001", ok=False))  # the template is not ready
        self.plan_file(1)
        self.assertIn("«acordado»", self.mth("plan", "agree", "PLAN-0001"))
        self.assertIn("PLAN-0001 · acordado", self.mth("plan", "list"))
        self.assertIn("«ejecutado»", self.mth("plan", "done", "PLAN-0001"))
        self.assertIn("«ejecutado»", self.mth("plan", "done", "PLAN-0001", ok=False))
        self.assertIn("«abandonado»", self.mth("plan", "done", "PLAN-0002", "--abandon"))
        self.mth("plan", "show", "PLAN-0009", ok=False)
        self.mth("plan", "new", ok=False)
        self.mth("plan", "check", "SPEC-9999", ok=False)  # the actions of a spec's work plan keep their own meaning
        self.assertIn("No hay datos", self.mth("plan", "stats"))

    def test_a_branch_of_a_required_kind_needs_an_agreed_plan(self):
        # verifies: SPEC-0023/AC-09
        # verifies: SPEC-0023/AC-11
        # verifies: SPEC-0023/FM-01
        # verifies: SPEC-0023/FM-02
        self.mth("branch", "chore", "levels")
        for level in ("until-pr", "supervised"):  # "full" is already the configured level
            cfg = self.work / ".claude/methodology.toml"
            cfg.write_text(re.sub(r'(\[autonomy\]\s*(?:#.*\n)*level = )"[^"]*"', rf'\1"{level}"', cfg.read_text()))
            self.git("add", "-A")
            self.mth("commit", "--type", "chore", "--summary", f"level {level}", "--body", "Set the level.", "--refs", "n/a")
            self.assertIn("--plan", self.mth("branch", "feat", "x", ok=False), level)
            self.git("checkout", "-q", "chore/levels")
        self.assertEqual(self.git("branch", "--list", "feat/x"), "")
        self.mth("plan", "new", "demo")
        self.assertIn("«borrador»", self.mth("branch", "feat", "x", "--plan", "PLAN-0001", ok=False))
        self.assertEqual(self.git("branch", "--list", "feat/x"), "")
        self.plan_file(1)
        self.mth("plan", "agree", "PLAN-0001")
        self.mth("branch", "feat", "x", "--plan", "PLAN-0001")
        self.assertEqual(self.git("branch", "--show-current"), "feat/x")
        plan = (self.plans / "PLAN-0001-demo.md").read_text()
        self.assertIn("- Estado: en curso", plan)
        self.assertIn("- Rama: `feat/x`", plan)
        self.mth("branch", "chore", "free")  # chore needs no plan

    def test_integration_needs_a_running_plan_that_lists_the_branch(self):
        # verifies: SPEC-0023/AC-10
        # verifies: SPEC-0023/FM-08
        self.agreed_plan()
        self.mth("branch", "feat", "x", "--plan", "PLAN-0001")
        (self.work / "x.txt").write_text("x")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add x", "--body", "A file.", "--refs", "n/a")
        plan = self.plans / "PLAN-0001-demo.md"
        listed = plan.read_text()
        plan.write_text(listed.replace("- Rama: `feat/x`", "- Rama: —"))
        self.assertIn("no tiene un plan «en curso»", self.mth("integrate", "--title", "feat(x): add x", "--summary", "x", ok=False))
        plan.write_text(listed)
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "feat/x").split()[0] != self.git("rev-parse", "HEAD"), True)
        self.assertIn("Plan: PLAN-0001", self.mth("integrate", "--title", "feat(x): add x", "--summary", "x"))
        self.assertEqual(self.git("branch", "--show-current"), "development")

    def test_a_child_branch_uses_the_plan_of_its_parent(self):
        # verifies: SPEC-0023/AC-10
        self.agreed_plan()
        self.mth("branch", "feat", "x", "--plan", "PLAN-0001")
        self.mth("branch", "fix", "bug", "--child")
        (self.work / "y.txt").write_text("y")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add y", "--body", "A file.", "--refs", "n/a")
        self.assertIn("Plan: PLAN-0001", self.mth("integrate", "--title", "fix(x): add y", "--summary", "y"))

    def test_hotfix_finish_needs_the_plan_too(self):
        # verifies: SPEC-0023/AC-10
        for command in (("checkout", "-q", "main"), ("merge", "-q", "development"), ("push", "-q", "origin", "main"),
                        ("checkout", "-q", "development")):  # this harness leaves the configuration only on development
            self.git(*command)
        self.agreed_plan()
        self.mth("branch", "hotfix", "leak", "--plan", "PLAN-0001")
        self.mth("plan", "done", "PLAN-0001")
        self.assertIn("no tiene un plan «en curso»", self.mth("hotfix", "finish", ok=False))

    def test_a_corrupt_plan_is_named_and_never_counts(self):
        # verifies: SPEC-0023/AC-12
        self.plans.mkdir(parents=True, exist_ok=True)
        (self.plans / "PLAN-0001-roto.md").write_text("basura")
        self.assertIn("PLAN-0001-roto.md", self.mth("plan", "list"))
        self.assertIn("PLAN-0001-roto.md", self.mth("branch", "feat", "x", "--plan", "PLAN-0001", ok=False))

    def test_a_plan_id_is_not_a_valid_commit_reference(self):
        # verifies: SPEC-0023/AC-08
        self.agreed_plan()
        self.mth("branch", "feat", "x", "--plan", "PLAN-0001")
        (self.work / "x.txt").write_text("x")
        self.git("add", "-A")
        self.mth("commit", "--type", "feat", "--summary", "add x", "--body", "A file.", "--refs", "PLAN-0001", ok=False)

    def test_status_lists_open_plans_and_warns_about_a_branch_without_one(self):
        # verifies: SPEC-0023/AC-13
        self.agreed_plan()
        self.mth("branch", "feat", "x", "--plan", "PLAN-0001")
        status = self.mth("status")
        self.assertIn("Planes abiertos (.work/plans/): PLAN-0001 en curso: Demo", status)
        self.assertNotIn("⚠ La rama", status)
        plan = self.plans / "PLAN-0001-demo.md"
        plan.write_text(plan.read_text().replace("- Rama: `feat/x`", "- Rama: —"))
        self.assertIn("⚠ La rama feat/x no tiene un plan «en curso»", self.mth("status"))

    def test_doctor_checks_the_planner_role(self):
        # verifies: SPEC-0023/AC-14
        self.assertIn("Rol planner → planificador", self.mth("doctor"))
        cfg = self.work / ".claude/methodology.toml"
        cfg.write_text(cfg.read_text().replace('planner = "planificador"', 'planner = "no-existe"'))
        self.assertIn("✗ Rol planner → no-existe", self.mth("doctor", ok=False))


class UpdateGapTests(UpdateTestCase):
    def test_new_keys_arrive_through_the_config_gap_without_a_new_gap(self):
        # verifies: SPEC-0023/AC-18
        text = support.template_with_agents().replace('mode = ""', 'mode = "off"', 1)
        text = re.sub(r"\n\[plans\].*?(?=\n\[)", "", text, flags=re.S).replace('planner = "planificador"\n', "")
        self.write(".claude/methodology.toml", text)
        missing = {".".join(p) for p in update.missing_keys(self.repo())}
        self.assertTrue({"plans", "roles.planner"} <= missing, missing)
        self.assertEqual(self.ids()["config"].clase, update.AUTOMATIC)
        self.assertNotIn("planes", self.ids())
        self.assertNotIn("plan", self.ids())


if __name__ == "__main__":
    unittest.main()
