"""Per-agent guard of the catalog agents: ``mth agent-guard`` (SPEC-0012, ADR-0008).

A single PreToolUse hook in the repository's ``.claude/settings.json`` sends every
Bash/Write/Edit call of the session to the shim ``.claude/hooks/mth-agent-guard``; the shim
calls this guard only for subagent payloads (``agent_id``/``agent_type``). The guard lets
through agents that do not come from the catalog and applies to catalog agents the rules
rendered in ``.claude/mth/agents/<agent>.guard.toml``.

It fails CLOSED (exit 2) on any error: missing rules, unreadable payload, a subagent without
``agent_type``, a command that cannot be tokenised, git not answering in time, an internal
bug. This is the opposite of the global guard (``mthlib.guard``), which fails open by design;
the two policies share no entry point (ADR-0008, decision 7). It is a safeguard against agent
mistakes, not a security boundary: a script run by a denylist agent can do anything.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path

from . import catalog, globs
from .errors import MthError
from .log import Tracer
from .proc import run

BLOCK = 2  # Claude Code: exit code 2 blocks the tool call and shows stderr to the model.
AGENTS_DIR = Path(".claude") / "agents"
GUARDS_DIR = Path(".claude") / "mth" / "agents"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
GIT_TIMEOUT = 5  # seconds per git call; the shim and the hook entry allow more (SPEC-0012)
LOG_NAME = "agent-guard.jsonl"
LOG_MAX_BYTES = 1024 * 1024
# Files that define the restrictions themselves: never writable by a catalog agent (SPEC-0012/AC-25).
PROTECTED = (".git", ".git/**", ".claude/hooks/**", ".claude/mth/**", ".claude/agents/**",
             ".claude/settings*.json", ".claude/methodology.toml")
_OWN_SCRIPTS = Path(__file__).resolve().parents[1]
_OWN_MTH = {(_OWN_SCRIPTS / "mth").resolve(), (_OWN_SCRIPTS / "mth.py").resolve()}

_SEP = re.compile(r"(\|\||&&|;|\||\n)")
_FD_DUP = re.compile(r"(?<![\w&>])\d?>&\d\b")  # 2>&1, >&2: duplicate descriptors, write no file
_MTH_VAR = re.compile(r"(^|[;&|\n])(\s*)\$(?:\{MTH\}|MTH)(?=\s|$)")  # $MTH in program position
_MTH_NAMES = {"mth", "mth.py"}
_INTERPRETERS = re.compile(r"^(sh|bash|python|python3(\.\d+)?)$")
_WRAPPERS = {"env", "nohup", "time", "nice", "command", "exec", "xargs", "stdbuf"}
_UNQUOTED_EXPANSIONS = set("${}*?[~`")
_TEMPLATE_HEADER = "<!-- mth:template "
# Filter options that write a file or run a program; GNU long options accept unique prefixes.
_FILTER_DENIED = {"sort": {"short": "oT", "long": ("output", "compress-program", "temporary-directory",
                                                   "files0-from")}}
_UNIQ_VALUE_OPTIONS = {"-f", "-s", "-w"}


class Denied(Exception):
    """The call is blocked; the message reaches the model through stderr."""

    def __init__(self, message: str, category: str = "rule") -> None:
        super().__init__(message)
        self.category = category


# -- Bash ---------------------------------------------------------------------
def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError as exc:  # unbalanced quotes: the command cannot be reasoned about
        raise Denied(f"Comando no tokenizable ({exc}).") from exc


def _is_own_mth(path: str) -> bool:
    try:
        return Path(path).resolve() in _OWN_MTH
    except OSError:
        return False


def _normalize(tok: list[str], strict: bool) -> list[str]:
    """The command with its program normalised: ``mth`` in any spelling, basename otherwise.

    In ``strict`` (allowlist) mode a program with a path is denied unless it is this plugin's
    own ``mth``: ``./git`` or ``/tmp/x/git`` must not pass for ``git`` (SPEC-0012/AC-23).
    """
    if not tok:
        return tok
    first = tok[0]
    if _INTERPRETERS.match(first) and len(tok) > 1 and tok[1].rsplit("/", 1)[-1] in _MTH_NAMES:
        if strict and not _is_own_mth(tok[1]):
            raise Denied(f"Solo se admite el mth de este plugin, no `{tok[1]}`.")
        return ["mth", *tok[2:]]
    if first == "mth":
        return tok
    if "/" in first:
        if first.rsplit("/", 1)[-1] in _MTH_NAMES and (not strict or _is_own_mth(first)):
            return ["mth", *tok[1:]]
        if strict:
            raise Denied(f"No se admiten programas con ruta: `{first}`.")
    return [first.rsplit("/", 1)[-1], *tok[1:]]


def unquoted_expansion(command: str) -> str | None:
    """First shell expansion the tokenizer does not model, outside the quotes that disable it.

    ``$`` and backticks expand outside single quotes; braces, ``~`` and wildcards only outside
    any quotes. ``$MTH`` in program position must have been replaced before.
    """
    quote = None
    escaped = False
    for ch in command:
        if escaped:
            escaped = False
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            continue
        if quote == "'":
            quote = None if ch == "'" else quote
            continue
        if quote == '"':
            if ch == '"':
                quote = None
            elif ch in "$`":
                return ch
            continue
        if ch in "'\"":
            quote = ch
        elif ch in _UNQUOTED_EXPANSIONS:
            return ch
    return None


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


def _check_filter(words: list[str], deny_flags: list[str]) -> None:
    """A filter after ``|`` reads stdin and writes stdout: nothing else (SPEC-0012/AC-23)."""
    program, args = words[0], words[1:]
    flag = _has_flag(args, deny_flags)
    if flag:
        raise Denied(f"Opción no permitida en `{program}`: `{flag}`.")
    rules = _FILTER_DENIED.get(program)
    if rules:
        for a in args:
            if a.startswith("--"):
                name = a[2:].split("=", 1)[0]
                if name and any(long.startswith(name) for long in rules["long"]):
                    raise Denied(f"Opción no permitida en `{program}`: `{a}`.")
            elif a.startswith("-") and any(c in rules["short"] for c in a[1:]):
                raise Denied(f"Opción no permitida en `{program}`: `{a}`.")
    if program == "uniq":  # uniq [INPUT [OUTPUT]]: a positional argument may be an output file
        previous = ""
        for a in args:
            if not a.startswith("-") and not (previous in _UNIQ_VALUE_OPTIONS and a.isdigit()):
                raise Denied("`uniq` solo se admite como filtro, sin ficheros.")
            previous = a


def _allow_segment(bash: dict, tok: list[str], after_pipe: bool) -> None:
    words = _git_safe(_normalize(tok, strict=True))
    for exact in bash.get("allow_exact", []):
        if words == exact.split():
            return
    for prefix in bash.get("allow", []):
        if _starts(words, prefix):
            flag = _has_flag(words[len(prefix.split()):], bash.get("deny_flags", []))
            if flag:
                raise Denied(f"Opción no permitida en `{prefix}`: `{flag}`.")
            return
    if after_pipe and words and words[0] in bash.get("filters", []):
        _check_filter(words, bash.get("deny_flags", []))
        return
    raise Denied(f"Comando no permitido para este agente: `{' '.join(tok[:3])}`.")


def _deny_segment(bash: dict, tok: list[str]) -> None:
    words = _normalize(tok, strict=False)
    while words and words[0] in _WRAPPERS:  # env/xargs/nohup git push → git push
        words = words[1:]
        while words and (words[0].startswith("-") or words[0].isdigit() or "=" in words[0]):
            words = words[1:]
        words = _normalize(words, strict=False)
    words = _git_safe(words)
    candidates = [words]
    for i, w in enumerate(words):  # find ... -exec git push \;
        if w in ("-exec", "-execdir", "-ok"):
            candidates.append(_git_safe(_normalize(words[i + 1:], strict=False)))
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
    if mode == "allowlist":
        command = _MTH_VAR.sub(r"\1\2mth", command)
        found = unquoted_expansion(command)
        if found:
            raise Denied(f"Expansión de shell no permitida: `{found}` (usa comillas simples para texto literal).")
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


def _rev_parse(where: Path, *what: str) -> list[str]:
    try:
        proc = run(["git", "rev-parse", "--path-format=absolute", *what], cwd=where, check=False,
                   timeout=GIT_TIMEOUT)
    except MthError as exc:
        raise Denied(exc.message, "timeout") from exc
    if proc.returncode != 0:
        raise Denied(f"No se puede resolver el repositorio de {where}.")
    return proc.stdout.splitlines()


def locate(project: Path, cwd: Path) -> Place:
    """Resolve the working tree of ``cwd`` and check it belongs to the project's repository.

    Raises:
        Denied: ``cwd`` is not a git working tree of the same repository, or git timed out.
    """
    project = project.resolve()
    cwd = cwd.resolve()
    if cwd == project:
        return Place(project, project, False)
    if not cwd.is_dir():
        raise Denied(f"El directorio de trabajo ({cwd}) no existe.")
    git_dir, common, top = _rev_parse(cwd, "--git-dir", "--git-common-dir", "--show-toplevel")
    (project_common,) = _rev_parse(project, "--git-common-dir")
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
    if globs.match_any(rel, list(PROTECTED)):
        raise Denied(f"Este agente no puede modificar los ficheros que definen sus restricciones: {rel}")
    if not globs.match_any(rel, allow):
        raise Denied(f"Este agente solo puede escribir en: {', '.join(allow)}. Ruta: {rel}")


# -- dispatch -----------------------------------------------------------------
def load_rules(project: Path, agent: str) -> dict:
    """Rendered guard rules of a catalog agent.

    Raises:
        Denied: The rules are missing or invalid.
    """
    path = project / GUARDS_DIR / f"{agent}.guard.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Denied(f"Faltan las reglas del agente {agent} ({path}). Ejecuta `mth agents sync`.",
                     "missing-rules") from exc
    except tomllib.TOMLDecodeError as exc:
        raise Denied(f"Reglas inválidas en {path}: {exc}", "invalid-rules") from exc


def catalog_rules(project: Path, agent: str) -> dict | None:
    """Rules of ``agent`` if it is a catalog agent, None if it is not.

    A catalog agent has a template header in its ``.md`` or a rendered guard: losing the
    header must not lift the restrictions (SPEC-0012/AC-21).

    Raises:
        Denied: Guard without header, header without guard, or invalid rules.
    """
    if not catalog.NAME.match(agent):
        return None  # plugin agents (methodology:verificador), built-ins (Explore)
    try:
        header = _TEMPLATE_HEADER in (project / AGENTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        header = False
    guard = (project / GUARDS_DIR / f"{agent}.guard.toml").is_file()
    if not header and not guard:
        return None
    if guard and not header:
        raise Denied(f"Agente del catálogo editado ({agent}: su .md perdió la cabecera de plantilla): "
                     f"mth agents sync --force {agent} o mth agents remove {agent}.", "edited")
    return load_rules(project, agent)


def evaluate(payload: dict, project: Path) -> str | None:
    """Decide on one hook payload; raise Denied to block it.

    Returns:
        The catalog agent the decision applied to, or None (main session, foreign agent).
    """
    if not isinstance(payload, dict):
        raise Denied("Payload del hook inesperado.", "payload")
    agent = payload.get("agent_type")
    if not agent:
        if "agent_id" in payload:
            raise Denied("Llamada de un subagente sin agent_type: no se puede identificar al agente.", "payload")
        return None  # main session: the per-agent guard does not apply
    if not isinstance(agent, str):
        raise Denied("agent_type no es un texto.", "payload")
    rules = catalog_rules(project, agent)
    if rules is None:
        return None
    if rules.get("delegate") == "global":
        return agent  # principal agent: the global guard of the session applies
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    place = locate(project, Path(payload.get("cwd") or project))
    if tool == "Bash":
        check_bash(rules, str(tool_input.get("command", "")))
    elif tool in WRITE_TOOLS:
        check_write(rules, tool_input, place)
    else:
        raise Denied(f"Herramienta no prevista por el guard: {tool}.")
    return agent


def _common_dir(project: Path) -> Path | None:
    dot_git = project / ".git"
    if dot_git.is_dir():
        return dot_git
    try:
        return Path(_rev_parse(project, "--git-common-dir")[0])
    except (Denied, IndexError):
        return None


def _record(project: str | None, payload: object, result: str, category: str, reason: str,
            agent: str | None, detail: str | None = None) -> None:
    """Append the decision to ``<git-common-dir>/mth/agent-guard.jsonl`` (SPEC-0012/AC-27)."""
    if not project:
        return
    data = payload if isinstance(payload, dict) else {}
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    target = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    event = {"agent": agent or data.get("agent_type"), "agent_id": data.get("agent_id"),
             "session": data.get("session_id"), "tool": data.get("tool_name"), "target": str(target)[:300],
             "result": result, "category": category, "reason": reason}
    if detail:
        event["traceback"] = detail
    Tracer(_common_dir(Path(project)), "agent-guard", LOG_NAME, LOG_MAX_BYTES).event("agent_guard.decision", **event)


def main(stdin: str, environ: dict[str, str] | None = None) -> int:
    """Hook entry point. Returns 0 to allow and 2 to block; never raises (fails closed)."""
    environ = os.environ if environ is None else environ
    project = environ.get("CLAUDE_PROJECT_DIR")
    payload: object = None
    try:
        if not project:
            raise Denied("CLAUDE_PROJECT_DIR no está definido.", "environment")
        try:
            payload = json.loads(stdin)
        except json.JSONDecodeError as exc:
            raise Denied(f"Payload del hook ilegible: {exc}.", "payload") from exc
        agent = evaluate(payload, Path(project))
        if agent:
            _record(project, payload, "allow", "rule", "", agent)
        return 0
    except Denied as exc:
        print(f"[mth-agent-guard] {exc}", file=sys.stderr)
        _record(project, payload, "deny", exc.category, str(exc), None)
        return BLOCK
    except MthError as exc:
        print(f"[mth-agent-guard] {exc.message}", file=sys.stderr)
        _record(project, payload, "deny", "error", exc.message, None)
        return BLOCK
    except Exception as exc:  # noqa: BLE001 — hook boundary: fail closed, keep the traceback.
        print(f"[mth-agent-guard] Error interno ({type(exc).__name__}: {exc}); se bloquea por seguridad.",
              file=sys.stderr)
        # If the log itself fails, the process exits non-zero and the shim still blocks.
        _record(project, payload, "deny", "internal", f"{type(exc).__name__}: {exc}", None, traceback.format_exc())
        return BLOCK
