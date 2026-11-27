"""Docs test of the tools manager (SPEC-0025)."""
from __future__ import annotations

import unittest
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


class ReadmeCase(unittest.TestCase):
    # verifies: SPEC-0025/AC-16
    def test_readme_documents_the_tools_manager(self):
        text = README.read_text(encoding="utf-8")
        start = text.index("### Herramientas externas (`mth tools`)")
        end = text.find("\n## ", start)
        section = text[start:end if end != -1 else None]
        for needle in ("mth tools install", "mth tools prune", "PATH", "MTH_TOOLS_DIR", "SHA-256", "manifest.toml"):
            self.assertIn(needle, section)


if __name__ == "__main__":
    unittest.main()
