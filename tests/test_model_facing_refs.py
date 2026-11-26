"""The text the plugin loads into another repo's model never cites this repo's specs or ADR."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "methodology"
CITATION = re.compile(r"\b(?:SPEC|ADR)-\d{4}\b")
EXAMPLES = {"SPEC-0001"}  # the first number a repo that archives its specs starts from
MODEL_FACING = [PLUGIN / "PRINCIPLES.md", *PLUGIN.glob("skills/*/*.md"), *PLUGIN.glob("agents/*.md"),
                *PLUGIN.glob("context/*.md"), *PLUGIN.glob("catalog/*/agent.md.tmpl")]


class ModelFacingTextTests(unittest.TestCase):
    def test_loaded_text_has_no_citations_of_this_repo(self):
        # regression: skills and principles cited SPEC/ADR numbers that mean something else, or nothing, in another repo
        self.assertTrue(MODEL_FACING)
        found = [f"{path.relative_to(PLUGIN)}:{n}: {m}"
                 for path in MODEL_FACING
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 for m in CITATION.findall(line) if m not in EXAMPLES]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
