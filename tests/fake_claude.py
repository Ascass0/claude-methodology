"""A stand-in for the Claude Code CLI that plays the scenarios of ``mth smoke`` (SPEC-0014).

``FAKE_CLAUDE_MODE`` picks the behaviour. Where the real CLI would call the hook of
``.claude/settings.json`` before running a tool, this calls it the same way (same payload fields,
same exit-code contract), so the shim and ``mth agent-guard`` run for real.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_CLAUDE_MODE", "obey")
argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print(os.environ.get("FAKE_CLAUDE_VERSION", "9.9.9 (Fake Claude Code)"))
    sys.exit(0)

root = Path.cwd()
for name, value in (("FAKE_CWDFILE", str(root)), ("FAKE_PIDFILE", str(os.getpid())),
                    ("FAKE_ARGVFILE", json.dumps(argv))):
    if os.environ.get(name):
        Path(os.environ[name]).write_text(value, encoding="utf-8")


def hook(tool: str, tool_input: dict) -> int:
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    payload = {"session_id": "fake", "cwd": str(root), "hook_event_name": "PreToolUse", "agent_id": "a1",
               "agent_type": "mth-canary", "tool_name": tool, "tool_input": tool_input}
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run(["sh", "-c", command], input=json.dumps(payload), text=True, env=env,
                          capture_output=True).returncode


def write_ok(through_hook: bool = True) -> None:
    target = root / "canary-ok.txt"
    if through_hook and hook("Write", {"file_path": str(target), "content": "mth-canary"}) != 0:
        return
    target.write_text("mth-canary", encoding="utf-8")


def touch_leak(through_hook: bool = True) -> None:
    if through_hook and hook("Bash", {"command": f"touch {root / 'canary-leak.txt'}"}) != 0:
        return
    (root / "canary-leak.txt").write_text("", encoding="utf-8")


if mode == "obey":
    write_ok()
    touch_leak()
elif mode == "ignore-hooks":
    write_ok(False)
    touch_leak(False)
elif mode == "no-tools":
    pass
elif mode == "permission-block":  # the permission system stops Bash before any hook runs
    write_ok()
elif mode == "no-control":  # the Bash call is denied by the guard but the write never happens
    touch_leak()
elif mode == "write-unseen":  # the write runs without the hook; the Bash call does go through it
    write_ok(False)
    touch_leak()
elif mode == "auth-error":
    print("Error: not logged in. Run /login", file=sys.stderr)
    sys.exit(1)
elif mode == "leak-then-hang":  # the forbidden command runs, then claude never ends
    touch_leak(False)
    time.sleep(600)
elif mode == "hang":
    time.sleep(600)
sys.exit(0)
