#!/usr/bin/env python3
"""Entry point of the claude-methodology CLI (``mth``)."""
import os
import sys

if sys.version_info < (3, 11):  # tomllib is required (fail-fast).
    sys.stderr.write("✗ claude-methodology requiere Python >= 3.11.\n")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.argv[1:2] == ["agent-guard"]:  # SPEC-0012: runs on every subagent tool call; skip the CLI imports
    from mthlib.agent_guard import main as agent_guard_main
    sys.exit(agent_guard_main(sys.stdin.read()))

if sys.argv[1:2] == ["guard"]:  # SPEC-0007: runs on every Bash call; skip the CLI imports
    from mthlib.guard import main as guard_main
    sys.exit(guard_main(sys.stdin.read()))

from mthlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
