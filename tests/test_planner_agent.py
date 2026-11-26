"""Tests of the planificador plugin agent (SPEC-0023/AC-15, ADR-0021)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "methodology"
AGENT = PLUGIN / "agents" / "planificador.md"
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}


def split(text: str) -> tuple[dict[str, str], str]:
    head, body = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S).groups()
    return dict(line.split(": ", 1) for line in head.splitlines()), body


class PlannerAgentTests(unittest.TestCase):
    def setUp(self):
        self.meta, self.body = split(AGENT.read_text(encoding="utf-8"))

    def test_it_is_read_only_and_does_not_fix_its_model(self):
        # verifies: SPEC-0023/AC-15
        self.assertEqual(self.meta["name"], "planificador")
        tools = {t.strip() for t in self.meta["tools"].split(",")}
        self.assertFalse(tools & WRITE_TOOLS)
        self.assertNotIn("model", self.meta)  # ADR-0002: the model of a plugin agent is not in its header; mth-plan launches it on opus

    def test_its_text_requires_the_catalog_rules(self):
        # verifies: SPEC-0023/AC-15
        for needle in ("mth agents list", "Agentes a instalar", "mth agents add", "requisitos sin cumplir",
                       "Preguntas abiertas", "Asigna solo agentes de esa lista"):
            self.assertIn(needle, self.body)


class PlanSkillTests(unittest.TestCase):
    def test_the_skill_launches_the_planner_on_opus_and_agrees_only_with_approval(self):
        # verifies: SPEC-0023/AC-16
        meta, body = split((PLUGIN / "skills" / "mth-plan" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(meta["name"], "mth-plan")
        for needle in ('model: "opus"', "methodology:planificador", "mth plan agree", "visto bueno"):
            self.assertIn(needle, body)


class PlannerOpusRuleTests(unittest.TestCase):
    def test_agent_skill_and_develop_require_opus(self):
        # verifies: SPEC-0023/AC-22
        _, agent = split(AGENT.read_text(encoding="utf-8"))
        self.assertIn('model: "opus"', agent)
        self.assertIn("Modelo: opus", agent)
        _, plan_skill = split((PLUGIN / "skills" / "mth-plan" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("Modelo: opus", plan_skill)
        _, develop = split((PLUGIN / "skills" / "mth-develop" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn('model: "opus"', develop)


class PlanReadersTests(unittest.TestCase):
    def test_orchestrator_and_verifier_work_from_the_plan(self):
        # verifies: SPEC-0023/AC-17
        orchestrator = (PLUGIN / "catalog" / "orquestador" / "agent.md.tmpl").read_text(encoding="utf-8")
        for needle in ("plan acordado", "oleadas", "Registro de ejecución", "ruta del plan y la tarea", "mth agents add"):
            self.assertIn(needle, orchestrator)
        verifier = (PLUGIN / "agents" / "verificador.md").read_text(encoding="utf-8")
        for needle in ("plan acordado", "Registro de ejecución", "nada de secciones nuevas"):
            self.assertIn(needle, verifier)


if __name__ == "__main__":
    unittest.main()
