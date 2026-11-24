"""Size and content of what is loaded every session (SPEC-0018, ADR-0014)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "methodology"


def normative(text: str) -> dict[str, int]:
    patterns = {"NO DEBE": r"NO DEBEN?\b", "DEBERÍA": r"DEBERÍAN?\b", "PUEDE": r"PUEDEN?\b", "DEBE": r"(?<!NO )DEBEN?\b"}
    return {k: len(re.findall(p, text)) for k, p in patterns.items()}


def description(path: Path) -> str:
    m = re.search(r"^description:\s*(.*)$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"') if m else ""


# Characters before SPEC-0018 (git show development:<file>); `descripciones` is the sum over skills / agents.
BEFORE = {"core.md": 2487, "claude-block.md": 492, "PRINCIPLES.md": 22720, "skills": 3276, "agents": 4975}
# Normative words of PRINCIPLES.md and rules of core.md before SPEC-0018.
NORMATIVE_BEFORE = {"NO DEBE": 22, "DEBERÍA": 7, "PUEDE": 3, "DEBE": 37}
CORE_RULES_BEFORE, CORE_STOPS_BEFORE = 8, 3


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
        counts = normative((PLUGIN / "PRINCIPLES.md").read_text(encoding="utf-8"))
        for word, before in NORMATIVE_BEFORE.items():
            with self.subTest(word=word):
                self.assertGreaterEqual(counts[word], before)
        core = (PLUGIN / "context/core.md").read_text(encoding="utf-8")
        rules = core.split("**Reglas que no se negocian:**")[1].split("**Te detienes")[0]
        stops = core.split("**Te detienes y avisas solo si:**")[1].split("Principios completos")[0]
        self.assertGreaterEqual(len(re.findall(r"^- ", rules, re.M)), CORE_RULES_BEFORE)
        self.assertGreaterEqual(stops.count(";") + 1, CORE_STOPS_BEFORE)


if __name__ == "__main__":
    unittest.main()
