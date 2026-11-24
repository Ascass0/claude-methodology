"""PreToolUse guard for Bash: blocks commands that bypass the flow or rewrite history.

It is a guardrail for the agent, not a security boundary: GitHub rulesets
are the enforcement layer for shared branches. If the guard itself fails it
lets the command through (deliberate fail-open: a broken guard must not
paralyse the agent) and reports the failure on stderr.

It does nothing in a repository that has not adopted the methodology
(SPEC-0004). It also asks the person to confirm the steps that
``autonomy.level`` reserves (SPEC-0007, ADR-0004).
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AUTONOMY_LEVELS, CONFIG_PATH, load
from .errors import MthError
from .git import Git
from .work import WORK_DIR

_SPLIT = re.compile(r"\|\||&&|;|\||\n")
BLOCK = 2  # Claude Code: exit code 2 blocks the tool call and shows stderr to the model.
_MTH_SPELLINGS = ("$MTH", "${MTH}")
_MTH_NAMES = ("mth", "mth.py")
_WHOLE_TREE = {"", ".", ":/", ":/.", "*", ":/*"}  # after removing "./"

# Commands each autonomy level asks the person to confirm (cumulative).
_UNTIL_PR = {("mth", "integrate"), ("mth", "release"), ("mth", "hotfix finish")}
CONFIRM: dict[str, set[tuple[str, str]]] = {
    "full": set(),
    "until-pr": _UNTIL_PR,
    "supervised": _UNTIL_PR | {("mth", "commit"), ("mth", "branch"), ("mth", "reconfigure"),
                               ("git", "commit"), ("git", "push")},
}
assert set(CONFIRM) == set(AUTONOMY_LEVELS)


@dataclass(frozen=True)
class Context:
    adopted: bool
    protected: set[str]
    current: str | None
    autonomy: str


def _context(cwd: Path) -> Context:
    try:
        git = Git.discover(cwd)
    except MthError:
        return Context(False, set(), None, "full")
    if not (git.root / CONFIG_PATH).is_file():
        return Context(False, set(), None, "full")
    try:
        cfg = load(git.root)
        names, autonomy = {cfg.main, cfg.development}, cfg["autonomy"]["level"]
    except MthError:  # invalid configuration: protect the defaults and confirm everything (fail-safe)
        names, autonomy = {"main", "development"}, "supervised"
    try:
        current = git.current_branch()
    except MthError:
        current = None
    return Context(True, names, current, autonomy)


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _invocations(command: str):
    """(program, subcommand) of each segment, with ``mth`` in any of its spellings."""
    for segment in _SPLIT.split(command):
        tok = _tokens(segment.strip())
        while tok and "=" in tok[0] and not tok[0].startswith("-"):
            tok = tok[1:]
        for i, token in enumerate(tok):
            if token in _MTH_SPELLINGS or token.rsplit("/", 1)[-1] in _MTH_NAMES:
                rest = tok[i + 1:]
                if rest[:2] == ["hotfix", "finish"]:
                    yield "mth", "hotfix finish"
                elif rest:
                    yield "mth", rest[0]
                break
        else:
            if tok and tok[0].rsplit("/", 1)[-1] == "git":
                rest = tok[1:]
                while rest and rest[0].startswith("-"):
                    rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
                if rest:
                    yield "git", rest[0]


def confirmation(command: str, autonomy: str) -> str | None:
    """Why ``command`` needs the person's confirmation at this autonomy level, or None."""
    for prog, sub in _invocations(command):
        if (prog, sub) in CONFIRM[autonomy]:
            return f"autonomy.level = {autonomy}: `{prog} {sub}` requiere confirmación"
    return None


def _forces_work_dir(args: list[str]) -> bool:
    """A forced ``git add`` whose pathspecs reach ``.work/`` (it would add excluded files)."""
    force = any(a == "--force" or (a.startswith("-") and not a.startswith("--") and "f" in a[1:]) for a in args)
    if not force:
        return False
    if any(a in ("-A", "--all") or (a.startswith("-") and not a.startswith("--") and "A" in a[1:]) for a in args):
        return True
    paths = [a.removeprefix("./") for a in args if not a.startswith("-")]
    return any(p in _WHOLE_TREE or p.rstrip("/") == WORK_DIR or p.startswith(f"{WORK_DIR}/") for p in paths)


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
        if (prog, sub) in (("gh", "pr"), ("glab", "mr")) and args[:1] == ["merge"]:
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
        if sub == "add" and _forces_work_dir(args):
            return f"{WORK_DIR}/ es local y no se versiona (SPEC-0010)"
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
        if not re.search(r"\b(git|gh|mth)\b", command, re.IGNORECASE):
            return 0
        ctx = _context(Path(event.get("cwd") or "."))
        if not ctx.adopted:
            return 0
        reason = violation(command, ctx.protected, ctx.current)
        ask = None if reason else confirmation(command, ctx.autonomy)
    except Exception as exc:  # noqa: BLE001 — boundary of a hook: fail-open, see module doc.
        print(f"[claude-methodology] guard no disponible: {exc}", file=sys.stderr)
        return 0
    if reason:
        print(f"[claude-methodology] Bloqueado: {reason}.", file=sys.stderr)
        return BLOCK
    if ask:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                 "permissionDecisionReason": f"[claude-methodology] {ask}."}}))
    return 0
