"""Per-agent guard of the catalog agents: ``mth agent-guard`` (SPEC-0012, ADR-0008).

A single PreToolUse hook in the repository's ``.claude/settings.json`` sends every
Bash/Write/Edit call of the session to the shim ``.claude/hooks/mth-agent-guard``; the shim
calls this guard only for subagent payloads (``agent_id``/``agent_type``). The guard lets
through agents that do not come from the catalog and applies to catalog agents the rules
rendered in ``.claude/mth/agents/<agent>.guard.toml``.

It fails CLOSED (exit 2) on any error: missing rules, unreadable payload, a subagent without
``agent_type``, a command that cannot be tokenised, an internal bug. This is the opposite of
the global guard (``mthlib.guard``), which fails open by design; the two policies share no
entry point (ADR-0008, decision 7). It is a safeguard against agent mistakes, not a security
boundary: a script run by the agent can do anything.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import catalog, globs
from .errors import MthError
from .proc import run

BLOCK = 2  # Claude Code: exit code 2 blocks the tool call and shows stderr to the model.
AGENTS_DIR = Path(".claude") / "agents"
GUARDS_DIR = Path(".claude") / "mth" / "agents"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

_SEP = re.compile(r"(\|\||&&|;|\||\n)")
_FD_DUP = re.compile(r"(?<![\w&>])\d?>&\d\b")  # 2>&1, >&2: duplicate descriptors, write no file
_MTH_SPELLINGS = {"$MTH", "${MTH}"}
_MTH_NAMES = {"mth", "mth.py"}
_WRAPPERS = {"env", "nohup", "time", "nice", "command", "exec", "xargs", "stdbuf"}
_TEMPLATE_HEADER = "<!-- mth:template "


class Denied(Exception):
    """The call is blocked; the message reaches the model through stderr."""


# -- Bash ---------------------------------------------------------------------
def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError as exc:  # unbalanced quotes: the command cannot be reasoned about
        raise Denied(f"Comando no tokenizable ({exc}).") from exc


def _normalize(tok: list[str]) -> list[str]:
    """The command with its program normalised: ``mth`` in any spelling, basename otherwise."""
    if not tok:
        return tok
    first = tok[0]
    if first in ("sh", "bash", "python", "python3") and len(tok) > 1 and tok[1].rsplit("/", 1)[-1] in _MTH_NAMES:
        return ["mth", *tok[2:]]
    if first in _MTH_SPELLINGS or first.rsplit("/", 1)[-1] in _MTH_NAMES:
        return ["mth", *tok[1:]]
    return [first.rsplit("/", 1)[-1], *tok[1:]]


def _git_safe(words: list[str]) -> list[str]:
    """Drop ``-C <path>`` and reject the global git options that run code."""
    if not words or words[0] != "git":
        return words
    out, i = ["git"], 1
    while i < len(words) and words[i].startswith("-"):
        opt = words[i]
        if opt == "-C" and i + 1 < len(words):
            i += 2
            continue
        if opt == "-c" or opt.startswith(("--exec-path", "--config-env", "-c")):
            raise Denied("`git -c`, `--config-env` y `--exec-path` no están permitidos: permiten ejecutar código.")
        out.append(opt)
        i += 1
    return out + words[i:]


def _starts(words: list[str], prefix: str) -> bool:
    p = prefix.split()
    return words[:len(p)] == p


def _has_flag(args: list[str], flags: list[str]) -> str | None:
    for a in args:
        for f in flags:
            if a == f or (f.startswith("--") and a.startswith(f + "=")):
                return f
            if len(f) == 2 and f.startswith("-") and not a.startswith("--") and a.startswith(f) and len(a) > 2:
                return f  # -XPOST, -Ffoo
    return None


def _allow_segment(bash: dict, tok: list[str], after_pipe: bool) -> None:
    words = _git_safe(_normalize(tok))
    for prefix in bash.get("allow", []):
        if _starts(words, prefix):
            flag = _has_flag(words[len(prefix.split()):], bash.get("deny_flags", []))
            if flag:
                raise Denied(f"Opción no permitida en `{prefix}`: `{flag}`.")
            return
    if after_pipe and words and words[0] in bash.get("filters", []):
        return
    raise Denied(f"Comando no permitido para este agente: `{' '.join(tok[:3])}`.")


def _deny_segment(bash: dict, tok: list[str]) -> None:
    words = _normalize(tok)
    while words and words[0] in _WRAPPERS:  # env/xargs/nohup git push → git push
        words = words[1:]
        while words and (words[0].startswith("-") or words[0].isdigit() or "=" in words[0]):
            words = words[1:]
        words = _normalize(words)
    words = _git_safe(words)
    candidates = [words]
    for i, w in enumerate(words):  # find ... -exec git push \;
        if w in ("-exec", "-execdir", "-ok"):
            candidates.append(_git_safe(_normalize(words[i + 1:])))
    for cand in candidates:
        for prefix in bash.get("deny", []):
            if _starts(cand, prefix):
                raise Denied(f"Este agente no puede ejecutar `{prefix}`.")


def check_bash(rules: dict, command: str) -> None:
    """Raise Denied unless ``command`` is allowed by the ``[bash]`` rules."""
    bash = rules.get("bash")
    if not bash or bash.get("mode") == "deny":
        raise Denied("Este agente no puede usar Bash.")
    mode = bash.get("mode")
    if mode not in ("allowlist", "denylist"):
        raise Denied(f"Modo de guard desconocido: {mode!r}.")
    command = _FD_DUP.sub(" ", command)
    for op in bash.get("deny_operators", []):
        if op in command:
            raise Denied(f"Operador no permitido: `{op}`.")
    parts = _SEP.split(command)
    if "&" in "".join(parts[0::2]):
        raise Denied("No se permiten procesos en segundo plano (`&`).")
    for idx in range(0, len(parts), 2):
        seg = parts[idx].strip()
        if not seg:
            continue
        tok = _tokens(seg)
        if tok and "=" in tok[0] and not tok[0].startswith("-"):
            raise Denied("No se permiten asignaciones de entorno delante del comando.")
        if mode == "allowlist":
            _allow_segment(bash, tok, after_pipe=idx > 0 and parts[idx - 1] == "|")
        else:
            _deny_segment(bash, tok)


# -- Write / Edit -------------------------------------------------------------
@dataclass(frozen=True)
class Place:
    """Where a call happens: the session project and the git working tree of its ``cwd``."""

    project: Path
    top: Path          # top level of the working tree that contains the call's cwd
    linked: bool       # ``top`` is a linked worktree (git-dir != git-common-dir)


def locate(project: Path, cwd: Path) -> Place:
    """Resolve the working tree of ``cwd`` and check it belongs to the project's repository.

    Raises:
        Denied: ``cwd`` is not a git working tree of the same repository.
    """
    project = project.resolve()
    cwd = cwd.resolve()
    if cwd == project:
        return Place(project, project, False)
    if not cwd.is_dir():
        raise Denied(f"El directorio de trabajo ({cwd}) no existe.")

    def rev_parse(where: Path, *what: str) -> list[str]:
        proc = run(["git", "rev-parse", "--path-format=absolute", *what], cwd=where, check=False)
        if proc.returncode != 0:
            raise Denied(f"No se puede resolver el repositorio de {where}.")
        return proc.stdout.splitlines()
    git_dir, common, top = rev_parse(cwd, "--git-dir", "--git-common-dir", "--show-toplevel")
    (project_common,) = rev_parse(project, "--git-common-dir")
    if Path(common).resolve() != Path(project_common).resolve():
        raise Denied(f"El directorio de trabajo ({cwd}) no pertenece a este repositorio.")
    return Place(project, Path(top).resolve(), Path(git_dir).resolve() != Path(common).resolve())


def check_write(rules: dict, tool_input: dict, place: Place) -> None:
    """Raise Denied unless the target path is allowed by the ``[write]`` rules."""
    write = rules.get("write") or {}
    allow = write.get("allow")
    if not allow:
        raise Denied("Este agente no puede escribir ficheros.")
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        raise Denied("Llamada de escritura sin ruta.")
    root = place.project
    if write.get("in_worktree"):  # ADR-0008, decision 6
        if not place.linked or place.top == place.project:
            raise Denied("Este agente solo escribe dentro de su worktree aislado, no en el árbol principal.")
        root = place.top
    target = Path(raw)
    target = (target if target.is_absolute() else root / target).resolve()
    try:
        rel = target.relative_to(root).as_posix()
    except ValueError as exc:
        raise Denied(f"Ruta fuera {'de su worktree' if write.get('in_worktree') else 'del repositorio'}: {raw}") from exc
    if not globs.match_any(rel, allow):
        raise Denied(f"Este agente solo puede escribir en: {', '.join(allow)}. Ruta: {rel}")


# -- dispatch -----------------------------------------------------------------
def catalog_agent(project: Path, agent: str) -> bool:
    """Whether ``agent`` is an agent installed from the catalog (template header present)."""
    if not catalog.NAME.match(agent):
        return False  # plugin agents (methodology:verificador), built-ins (Explore)
    path = project / AGENTS_DIR / f"{agent}.md"
    try:
        return _TEMPLATE_HEADER in path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False


def load_rules(project: Path, agent: str) -> dict:
    """Rendered guard rules of a catalog agent.

    Raises:
        Denied: The rules are missing or invalid.
    """
    path = project / GUARDS_DIR / f"{agent}.guard.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Denied(f"Faltan las reglas del agente {agent} ({path}). Ejecuta `mth agents sync`.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise Denied(f"Reglas inválidas en {path}: {exc}") from exc


def evaluate(payload: dict, project: Path) -> None:
    """Decide on one hook payload; raise Denied to block it."""
    if not isinstance(payload, dict):
        raise Denied("Payload del hook inesperado.")
    agent = payload.get("agent_type")
    if not agent:
        if "agent_id" in payload:
            raise Denied("Llamada de un subagente sin agent_type: no se puede identificar al agente.")
        return  # main session: the per-agent guard does not apply
    if not isinstance(agent, str) or not catalog_agent(project, agent):
        return
    rules = load_rules(project, agent)
    if rules.get("delegate") == "global":
        return  # principal agent: the global guard of the session applies
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    place = locate(project, Path(payload.get("cwd") or project))
    if tool == "Bash":
        check_bash(rules, str(tool_input.get("command", "")))
    elif tool in WRITE_TOOLS:
        check_write(rules, tool_input, place)
    else:
        raise Denied(f"Herramienta no prevista por el guard: {tool}.")


def main(stdin: str, environ: dict[str, str] | None = None) -> int:
    """Hook entry point. Returns 0 to allow and 2 to block; never raises (fails closed)."""
    environ = os.environ if environ is None else environ
    try:
        project = environ.get("CLAUDE_PROJECT_DIR")
        if not project:
            raise Denied("CLAUDE_PROJECT_DIR no está definido.")
        try:
            payload = json.loads(stdin)
        except json.JSONDecodeError as exc:
            raise Denied(f"Payload del hook ilegible: {exc}.") from exc
        evaluate(payload, Path(project))
        return 0
    except Denied as exc:
        print(f"[mth-agent-guard] {exc}", file=sys.stderr)
        return BLOCK
    except MthError as exc:
        print(f"[mth-agent-guard] {exc.message}", file=sys.stderr)
        return BLOCK
    except Exception as exc:  # noqa: BLE001 — hook boundary: fail closed.
        print(f"[mth-agent-guard] Error interno ({type(exc).__name__}: {exc}); se bloquea por seguridad.",
              file=sys.stderr)
        return BLOCK
