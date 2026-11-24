"""Size and content of what is loaded every session (SPEC-0018, ADR-0014)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "methodology"


def normative(text: str) -> int:
    return len(re.findall(r"\b(?:NO DEBEN?|DEBERÍAN?|PUEDEN?|DEBEN?)\b", text))


def description(path: Path) -> str:
    m = re.search(r"^description:\s*(.*)$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"') if m else ""


# Characters before SPEC-0018 (git show development:<file>); `descripciones` is the sum over skills / agents.
BEFORE = {"core.md": 2487, "claude-block.md": 492, "PRINCIPLES.md": 22720, "skills": 3276, "agents": 4975}
# Normative words (DEBE, NO DEBE, DEBERÍA, PUEDE) per section of PRINCIPLES.md before SPEC-0018
# (git show origin/development:plugins/methodology/PRINCIPLES.md; section 7 and the core.md rules include what SPEC-0018 adds). Per section, so that rules added
# in one (the EARS lines of section 7) cannot hide a rule lost in another.
NORMATIVE_BEFORE = {1: 8, 2: 20, 3: 6, 4: 1, 5: 13, 6: 3, 7: 9, 8: 1, 9: 7, 10: 2, 11: 2}
CORE_RULES_BEFORE, CORE_STOPS_BEFORE = 9, 3


class LoadedContextTests(unittest.TestCase):
    def test_what_is_loaded_every_session_weighs_less(self):
        # verifies: SPEC-0018/AC-08
        now = {
            "core.md": len((PLUGIN / "context/core.md").read_text(encoding="utf-8")),
            "claude-block.md": len((PLUGIN / "templates/claude-block.md").read_text(encoding="utf-8")),
            "PRINCIPLES.md": len((PLUGIN / "PRINCIPLES.md").read_text(encoding="utf-8")),
            "skills": sum(len(description(f)) for f in PLUGIN.glob("skills/*/SKILL.md")),
            "agents": sum(len(description(f)) for f in [*PLUGIN.glob("agents/*.md"), *PLUGIN.glob("catalog/*/agent.md.tmpl")]),
        }
        for name, before in BEFORE.items():
            with self.subTest(document=name):
                self.assertLess(now[name], before)

    def test_no_normative_word_is_lost(self):
        # verifies: SPEC-0018/AC-09
        sections = re.split(r"^## (\d+)\. ", (PLUGIN / "PRINCIPLES.md").read_text(encoding="utf-8"), flags=re.M)
        counts = {int(sections[i]): normative(sections[i + 1]) for i in range(1, len(sections), 2)}
        for number, before in NORMATIVE_BEFORE.items():
            with self.subTest(section=number):
                self.assertGreaterEqual(counts[number], before)
        core = (PLUGIN / "context/core.md").read_text(encoding="utf-8")
        rules = core.split("**Reglas que no se negocian:**")[1].split("**Te detienes")[0]
        stops = core.split("**Te detienes y avisas solo si:**")[1].split("Principios completos")[0]
        self.assertGreaterEqual(len(re.findall(r"^- ", rules, re.M)), CORE_RULES_BEFORE)
        self.assertGreaterEqual(stops.count(";") + 1, CORE_STOPS_BEFORE)


if __name__ == "__main__":
    unittest.main()
