#!/usr/bin/env python3
"""Entry point of the claude-methodology CLI (``mth``)."""
import os
import sys

if sys.version_info < (3, 11):  # tomllib is required (fail-fast).
    sys.stderr.write("✗ claude-methodology requiere Python >= 3.11.\n")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mthlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
