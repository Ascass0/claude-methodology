"""Shared fixtures for the agent catalog tests (SPEC-0012)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import catalog  # noqa: E402
from mthlib.config import Config, parse  # noqa: E402
from mthlib.lang import TEMPLATES  # noqa: E402

CATALOG = catalog.CATALOG_DIR


def template_with_agents(test_command: str = "pytest -q") -> str:
    """The shipped configuration template with its ``[agents.*]`` example block uncommented."""
    text = (TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
    text = text.replace('test = ""', f'test = "{test_command}"', 1)
    start = text.index("# [agents.")
    block = "\n".join(re.sub(r"\s+#.*$", "", line[2:]) if line.startswith("# ") else line
                      for line in text[start:].splitlines())
    return text[:start] + block + "\n"


def fixture_config(root: Path = Path("/nonexistent")) -> Config:
    """Valid configuration with every optional agent variable set."""
    return parse(root, template_with_agents())
