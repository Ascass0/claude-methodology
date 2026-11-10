"""PreToolUse guard for Bash: blocks commands that bypass the flow or rewrite history.

It is a guardrail for the agent, not a security boundary: GitHub rulesets
are the enforcement layer for shared branches. If the guard itself fails it
lets the command through (deliberate fail-open: a broken guard must not
paralyse the agent) and reports the failure on stderr.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from .config import load
from .errors import MthError
from .git import Git

_SPLIT = re.compile(r"\|\||&&|;|\||\n")
BLOCK = 2  # Claude Code: exit code 2 blocks the tool call and shows stderr to the model.


def _protected(cwd: Path) -> tuple[set[str], str | None]:
    try:
        git = Git.discover(cwd)
    except MthError:
        return set(), None
    names = {"main", "development"}
    try:
        cfg = load(git.root)
        names = {cfg.main, cfg.development}
    except MthError:
        pass
    try:
        current = git.current_branch()
    except MthError:
        current = None
    return names, current


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def violation(command: str, protected: set[str], current: str | None) -> str | None:
    """Reason why ``command`` must be blocked, or None."""
    for segment in _SPLIT.split(command):
        tok = _tokens(segment.strip())
        while tok and "=" in tok[0] and not tok[0].startswith("-"):
            tok = tok[1:]  # leading VAR=value assignments
        prog = tok[0].rsplit("/", 1)[-1] if tok else ""
        rest = tok[1:]
        if prog == "git":  # skip global options: git -C dir -c k=v --no-pager push ...
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
        if not rest:
            continue
        sub, args = rest[0], rest[1:]
        if prog == "gh" and sub == "pr" and args[:1] == ["merge"]:
            return "los merges se hacen con `mth integrate`, `mth release` o `mth hotfix finish`"
        if prog != "git":
            continue
        on_protected = current in protected
        if "--no-verify" in args or (sub == "commit" and "-n" in args):
            return "--no-verify salta los hooks de la metodología"
        if sub == "push":
            if any(a in ("-f", "--force", "--force-with-lease") or a.startswith("--force") or
                   a.startswith("+") for a in args):
                return "force-push reescribe historia compartida"
            if any(a in ("-d", "--delete") or a.startswith(":") for a in args):
                return "el borrado de ramas o tags remotos lo hace mth al integrar"
            refspecs = [a for a in args if not a.startswith("-")][1:]
            if any(r.split(":")[-1] in protected for r in refspecs) or (not refspecs and on_protected):
                return f"no se hace push directo a {'/'.join(sorted(protected))}: usa mth integrate"
        if sub == "rebase" and not ({"--abort", "--quit"} & set(args)):
            return "rebase reescribe historia: usa `mth sync` (merge)"
        if sub == "pull" and ({"--rebase", "-r"} & set(args) or any(a.startswith("--rebase=") for a in args)):
            return "pull --rebase reescribe historia: usa `mth sync`"
        if sub in ("commit", "merge", "cherry-pick", "revert") and on_protected and "--abort" not in args:
            return f"no se trabaja directamente en {current}: crea una rama (skill mth-branch)"
        if sub == "reset" and "--hard" in args and on_protected:
            return f"reset --hard sobre {current} no está permitido"
        if sub == "branch" and {"-D", "-d", "--delete"} & set(args) and protected & set(args):
            return "las ramas main y development no se borran"
        if sub == "tag" and {"-d", "--delete", "-f", "--force"} & set(args):
            return "las etiquetas de versión son inmutables"
    return None


def main(stdin: str) -> int:
    try:
        event = json.loads(stdin or "{}")
        command = event.get("tool_input", {}).get("command", "")
        if not re.search(r"\b(git|gh)\b", command):
            return 0
        protected, current = _protected(Path(event.get("cwd") or "."))
        reason = violation(command, protected, current)
    except Exception as exc:  # noqa: BLE001 — boundary of a hook: fail-open, see module doc.
        print(f"[claude-methodology] guard no disponible: {exc}", file=sys.stderr)
        return 0
    if reason:
        print(f"[claude-methodology] Bloqueado: {reason}.", file=sys.stderr)
        return BLOCK
    return 0
