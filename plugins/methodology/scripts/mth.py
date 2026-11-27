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

if len(sys.argv) == 3 and sys.argv[1] == "check-msg":  # commit-msg hook: runs on every commit
    from mthlib.commits import check_file
    from mthlib.errors import MthError
    try:
        sys.exit(check_file(sys.argv[2]))
    except MthError as exc:
        exc.report()
        sys.exit(1)

if sys.argv[1:2] == ["session"]:  # SessionStart hook: every session pays for the CLI imports otherwise
    from mthlib.session import main as session_main
    sys.exit(session_main())

if sys.argv[1:2] == ["guard"]:  # SPEC-0007: runs on every Bash call; skip the CLI imports
    from mthlib.guard import main as guard_main
    sys.exit(guard_main(sys.stdin.read()))

from mthlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
