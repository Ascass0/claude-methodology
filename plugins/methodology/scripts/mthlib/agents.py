"""``mth agents``: install, update and remove catalog agents in a repository (SPEC-0012, ADR-0008).

Every command validates and renders everything before writing the first file. Nothing is
committed: the session commits the result like any other change.

Installed files (versioned): ``.claude/agents/<agent>.md``, ``.claude/mth/agents/<agent>.guard.toml``,
the shim ``.claude/hooks/mth-agent-guard``, one PreToolUse entry in ``.claude/settings.json``
and, for worktree agents, ``.claude/worktrees/`` in ``.gitignore``.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import catalog
from .agent_guard import AGENTS_DIR, GUARDS_DIR
from .config import CONFIG_PATH, Config, parse
from .errors import MthError
from .log import say, warn

SHIM = Path(".claude") / "hooks" / "mth-agent-guard"
SETTINGS = Path(".claude") / "settings.json"
GITIGNORE = Path(".gitignore")
WORKTREES_IGNORE = ".claude/worktrees/"
HOOK_MATCHER = "Bash|Write|Edit|MultiEdit|NotebookEdit"
# The shim may be missing (deleted, partial checkout): subagents are blocked, the main session goes on.
HOOK_COMMAND = (
    'f="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/mth-agent-guard"; '
    'if [ -f "$f" ]; then exec sh "$f"; fi; '
    "if grep -q -e '\"agent_id\"' -e '\"agent_type\"'; then "
    'echo "[mth-agent-guard] Falta .claude/hooks/mth-agent-guard: ejecuta mth agents sync." >&2; exit 2; fi; '
    "exit 0")
VERIFIER = "verificador"
_COMMENT = re.compile(r"<!--.*?-->", re.S)


# -- reading the repository ---------------------------------------------------------
@dataclass(frozen=True)
class Copy:
    """What is installed for one agent name."""

    md: str | None
    guard: str | None
    origin: catalog.Installed | None  # None: not from the catalog (or not installed)


def read_copy(root: Path, name: str) -> Copy:
    md_path, guard_path = root / AGENTS_DIR / f"{name}.md", root / GUARDS_DIR / f"{name}.guard.toml"
    md = md_path.read_text(encoding="utf-8") if md_path.is_file() else None
    guard = guard_path.read_text(encoding="utf-8") if guard_path.is_file() else None
    return Copy(md, guard, catalog.installed(md, guard) if md is not None else None)


def installed_names(root: Path) -> list[str]:
    """Agents of ``.claude/agents/`` that come from the catalog (template header)."""
    folder = root / AGENTS_DIR
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.md")
                  if catalog.installed(p.read_text(encoding="utf-8"), None) is not None)


def local_is_empty(agent_md: str) -> bool:
    """Whether the local section holds nothing but comments and blanks."""
    section = catalog.local_section(agent_md)
    return section is not None and not _COMMENT.sub("", section).strip()


# -- .claude/settings.json ------------------------------------------------------------
def read_settings(root: Path) -> dict[str, Any]:
    """``.claude/settings.json`` (empty when absent).

    Raises:
        MthError: The file is not a JSON object (nothing is written).
    """
    path = root / SETTINGS
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MthError(f"{SETTINGS} no es JSON válido: {exc}.", hint="Corrígelo y vuelve a intentarlo.") from exc
    if not isinstance(data, dict):
        raise MthError(f"{SETTINGS} debe ser un objeto JSON.")
    return data


def _is_ours(entry: Any) -> bool:
    return isinstance(entry, dict) and any(
        isinstance(h, dict) and str(SHIM) in str(h.get("command", "")) for h in entry.get("hooks", []) or [])


def has_hook(settings: dict[str, Any]) -> bool:
    return any(_is_ours(e) for e in ((settings.get("hooks") or {}).get("PreToolUse") or []))


def with_hook(settings: dict[str, Any]) -> dict[str, Any]:
    """Settings with exactly one, current, agent-guard entry; every other key is kept."""
    out = json.loads(json.dumps(settings))
    hooks = out.setdefault("hooks", {})
    entries = [e for e in hooks.get("PreToolUse") or [] if not _is_ours(e)]
    entries.append({"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    hooks["PreToolUse"] = entries
    return out


def without_hook(settings: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(settings))
    hooks = out.get("hooks") or {}
    if "PreToolUse" in hooks:
        hooks["PreToolUse"] = [e for e in hooks["PreToolUse"] if not _is_ours(e)]
        if not hooks["PreToolUse"]:
            del hooks["PreToolUse"]
    if "hooks" in out and not out["hooks"]:
        del out["hooks"]
    return out


def _settings_text(settings: dict[str, Any]) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


# -- .claude/methodology.toml: review.agents and [review.paths] -------------------------
def _section(text: str, header: str) -> tuple[int, int] | None:
    """Span of a TOML table body (after its header line) or None."""
    m = re.search(rf"^\[{re.escape(header)}\][ \t]*(#.*)?$", text, re.M)
    if not m:
        return None
    start = m.end() + 1 if m.end() < len(text) else m.end()
    nxt = re.search(r"^\[", text[start:], re.M)
    return start, start + nxt.start() if nxt else len(text)


def _toml_list(values: list[str], key: str) -> str:
    """A TOML array of strings in the file's style; one item per line when it gets long."""
    items = [json.dumps(v, ensure_ascii=False) for v in values]
    inline = "[" + ", ".join(items) + "]"
    if len(key) + 3 + len(inline) <= 100:
        return inline
    return "[\n" + "".join(f"  {item},\n" for item in items) + "]"


def _set_key(text: str, header: str, key: str, value: list[str] | None) -> str:
    """Set (or delete, with None) list ``key`` of table ``header``, creating the table if needed."""
    line = None if value is None else f"{_toml_key(key)} = {_toml_list(value, key)}\n"
    span = _section(text, header)
    if span is None:
        if line is None:
            return text
        return text.rstrip("\n") + f"\n\n[{header}]\n{line}"
    start, end = span
    body = text[start:end]
    pattern = re.compile(rf"^{re.escape(_toml_key(key))}\s*=\s*\[.*?\][ \t]*(#.*)?\n?", re.M | re.S)
    if pattern.search(body):
        body = pattern.sub(lambda _m: line or "", body, count=1)
    elif line is not None:
        content_end = len(body.rstrip("\n").rstrip())
        body = body[:content_end] + ("\n" if content_end else "") + line + body[content_end:].lstrip("\n")
        if not body.endswith("\n\n") and end < len(text):
            body += "\n"
    return text[:start] + body + text[end:]


def _toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def ordered_reviewers(current: list[str], name: str, order: int, orders: dict[str, int]) -> list[str]:
    """``review.agents`` with ``name`` at its place: after verificador, by catalog ``review.order``.

    Agents that are not catalog reviewers keep their relative position.
    """
    agents = [a for a in current if a != name]
    for i, agent in enumerate(agents):
        if agent in orders and orders[agent] > order:
            index = i
            break
    else:
        index = len(agents)
    if VERIFIER in agents:
        index = max(index, agents.index(VERIFIER) + 1)
    return agents[:index] + [name] + agents[index:]


def _reviewer_orders(catalog_dir: Path) -> dict[str, int]:
    out = {}
    for name in catalog.names(catalog_dir):
        meta = catalog.load_meta(catalog_dir, name)
        if "review" in meta:
            out[name] = meta["review"]["order"]
    return out


# -- planning and applying changes -----------------------------------------------------
@dataclass
class Changes:
    """Everything a command will write, computed and validated before writing."""

    root: Path
    files: dict[Path, str | None] = field(default_factory=dict)  # relative path → text (None: delete)
    config_text: str | None = None
    settings: dict[str, Any] | None = None
    executable: set[Path] = field(default_factory=set)

    def apply(self) -> None:
        for rel, text in self.files.items():
            path = self.root / rel
            if text is None:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            if rel in self.executable:
                path.chmod(0o755)
        if self.settings is not None:
            (self.root / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
            (self.root / SETTINGS).write_text(_settings_text(self.settings), encoding="utf-8")
        if self.config_text is not None:
            (self.root / CONFIG_PATH).write_text(self.config_text, encoding="utf-8")


class Manager:
    """Catalog agents of one repository.

    Args:
        cfg: Validated configuration of the repository.
        catalog_dir: The plugin catalog (injected so tests can use a modified copy).
    """

    def __init__(self, cfg: Config, catalog_dir: Path = catalog.CATALOG_DIR) -> None:
        self.cfg = cfg
        self.root = cfg.root
        self.catalog = catalog_dir
        self.orders = _reviewer_orders(catalog_dir)

    # -- helpers --------------------------------------------------------------------
    def _config_text(self) -> str:
        return (self.root / CONFIG_PATH).read_text(encoding="utf-8")

    def _with_review(self, text: str, name: str, review: dict[str, Any] | None, remove: bool) -> str:
        """Config text with ``name`` added to (or removed from) review.agents and [review.paths]."""
        data = parse(self.root, text)
        agents = list(data["review"]["agents"])
        paths = dict(data["review"]["paths"])
        expected_paths = {k: v for k, v in paths.items() if k != name}
        if remove:
            agents = [a for a in agents if a != name]
            if name in paths:
                text = _set_key(text, "review.paths", name, None)
        else:
            agents = ordered_reviewers(agents, name, review["order"], self.orders)
            current = paths.get(name, [])
            merged = current + [p for p in review["paths"] if p not in current]  # the repo may widen them
            if merged:
                expected_paths[name] = merged
                if merged != current:
                    text = _set_key(text, "review.paths", name, merged)
        text = _set_key(text, "review", "agents", agents)
        check = parse(self.root, text)  # fail before writing
        if check["review"]["agents"] != agents or check["review"]["paths"] != expected_paths:
            raise MthError(f"No se pudo actualizar [review] en {CONFIG_PATH} de forma segura.",
                           hint="Revisa el formato de review.agents y [review.paths] y vuelve a intentarlo.")
        return text

    def _infrastructure(self, changes: Changes, settings: dict[str, Any], worktree: bool) -> None:
        shim = (self.catalog / "_shared" / "mth-agent-guard.sh").read_text(encoding="utf-8")
        current = self.root / SHIM
        if not current.is_file() or current.read_text(encoding="utf-8") != shim:
            changes.files[SHIM] = shim
            changes.executable.add(SHIM)
        updated = with_hook(settings)
        if updated != settings:
            changes.settings = updated
        if worktree:
            path = self.root / GITIGNORE
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if not any(line.strip() in (WORKTREES_IGNORE, WORKTREES_IGNORE.rstrip("/"))
                       for line in text.splitlines()):
                changes.files[GITIGNORE] = text + ("" if not text or text.endswith("\n") else "\n") + \
                    f"# Worktrees de los agentes del catálogo (isolation: worktree)\n{WORKTREES_IGNORE}\n"

    def _write_agent(self, changes: Changes, rendered: catalog.Rendered) -> None:
        changes.files[AGENTS_DIR / f"{rendered.name}.md"] = rendered.agent_md
        changes.files[GUARDS_DIR / f"{rendered.name}.guard.toml"] = rendered.guard_toml

    def _language_notice(self) -> None:
        if self.cfg["language"]["docs"] != "es":
            warn("Las plantillas del catálogo están en español y language.docs = "
                 f"\"{self.cfg['language']['docs']}\": los agentes se instalan en español.")

    # -- commands -------------------------------------------------------------------
    def status(self, name: str) -> str:
        """State of one catalog agent in the repository, for ``mth agents list``."""
        meta = catalog.load_meta(self.catalog, name)
        copy = read_copy(self.root, name)
        if copy.md is not None and copy.origin is None:
            return "agente propio del repo (sin cabecera del catálogo)"
        if copy.origin is None:
            missing = catalog.missing_requirements(meta, self.cfg.data)
            return f"requisitos sin cumplir: {', '.join(missing)}" if missing else "no instalado"
        if copy.origin.edited:
            return "editado a mano"
        try:
            fresh = catalog.render(self.catalog, name, self.cfg.data, installed_md=copy.md)
        except catalog.TemplateError as exc:
            return f"instalado (v{copy.origin.version}); no se puede renderizar: {exc.message}"
        if copy.origin.version != meta["version"]:
            return f"desactualizado (catálogo v{meta['version']})"
        if fresh.agent_md != copy.md or fresh.guard_toml != copy.guard:
            return "desactualizado (la configuración cambió)"
        return f"instalado (v{copy.origin.version})"

    def list(self) -> None:
        for prof, spec in catalog.profiles(self.catalog).items():
            say(f"[{prof}] {spec['description']}")
            for name in spec["agents"]:
                meta = catalog.load_meta(self.catalog, name)
                say(f"  {name} v{meta['version']} · {meta['kind']} · modelo sugerido: {meta['model_hint']} "
                    f"→ {self.status(name)}")
                say(f"      {meta['summary']}")

    def add(self, names: list[str], profile: str | None, replace: bool) -> int:
        """Install agents. Returns the number of requested agents that could not be installed."""
        requested = set(names)  # unmet requirements fail only for agents named explicitly
        if profile:
            profiles = catalog.profiles(self.catalog)
            if profile not in profiles:
                raise MthError(f"Perfil desconocido: '{profile}'. Perfiles: {', '.join(profiles)}.")
            names = [*names, *(a for a in profiles[profile]["agents"] if a not in names)]
        if not names:
            raise MthError("Indica uno o más agentes o --profile <perfil>.")
        failures = 0
        changes = Changes(self.root)
        settings = read_settings(self.root)
        text = self._config_text()
        worktree = False
        installed: list[str] = []
        for name in names:
            meta = catalog.load_meta(self.catalog, name)
            copy = read_copy(self.root, name)
            if copy.origin is not None:
                say(f"· {name} ya está instalado: para actualizarlo, mth agents sync {name}.")
                continue
            if copy.md is not None and not replace:
                warn(f"{name}: ya existe {AGENTS_DIR}/{name}.md y no viene del catálogo; no se sobrescribe "
                     "(usa --replace después de pasar su contenido propio a la sección local).")
                failures += 1
                continue
            missing = catalog.missing_requirements(meta, self.cfg.data)
            if missing:
                warn(f"{name}: no se instala; requisitos sin configurar: {', '.join(missing)}.")
                failures += name in requested
                continue
            rendered = catalog.render(self.catalog, name, self.cfg.data)
            self._write_agent(changes, rendered)
            if rendered.review is not None:
                text = self._with_review(text, name, rendered.review, remove=False)
            worktree |= catalog.frontmatter(rendered.agent_md).get("isolation") == "worktree"
            installed.append(name)
        if installed:
            self._infrastructure(changes, settings, worktree)
            if text != self._config_text():
                changes.config_text = text
            changes.apply()
            self._language_notice()
            say(f"✓ Instalados: {', '.join(installed)}. Rellena su sección local si la tienen y haz commit.")
        return failures

    def _render_sync(self, name: str, copy: Copy) -> catalog.Rendered:
        return catalog.render(self.catalog, name, self.cfg.data, installed_md=copy.md)

    def sync(self, names: list[str], force: bool) -> int:
        """Re-render installed agents keeping their local section. Returns the number refused."""
        targets = names or installed_names(self.root)
        if not targets:
            say("No hay agentes del catálogo instalados.")
            return 0
        refused = 0
        changes = Changes(self.root)
        text = self._config_text()
        worktree = False
        for name in targets:
            copy = read_copy(self.root, name)
            if copy.origin is None:
                raise MthError(f"{name} no es un agente instalado desde el catálogo.",
                               hint=f"Instálalo con mth agents add {name}.")
            rendered = self._render_sync(name, copy)
            if copy.origin.edited and not force:
                warn(f"{name}: la parte generada se editó a mano; no se sincroniza sin --force. Diferencias:")
                print(self._diff(name, copy, rendered))
                refused += 1
                continue
            self._write_agent(changes, rendered)
            if rendered.review is not None:
                text = self._with_review(text, name, rendered.review, remove=False)
            worktree |= catalog.frontmatter(rendered.agent_md).get("isolation") == "worktree"
        self._infrastructure(changes, read_settings(self.root), worktree)
        if text != self._config_text():
            changes.config_text = text
        changes.files = {k: v for k, v in changes.files.items()
                         if v is None or not (self.root / k).is_file() or (self.root / k).read_text(encoding="utf-8") != v}
        changes.apply()
        say("✓ Agentes sincronizados." if not refused else f"{refused} agentes sin sincronizar.")
        return refused

    def _diff(self, name: str, copy: Copy, rendered: catalog.Rendered) -> str:
        parts = []
        for label, old, new in ((f"{AGENTS_DIR}/{name}.md", copy.md or "", rendered.agent_md),
                                (f"{GUARDS_DIR}/{name}.guard.toml", copy.guard or "", rendered.guard_toml)):
            parts += difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                          f"{label} (instalado)", f"{label} (catálogo)")
        return "".join(parts)

    def diff(self, name: str) -> str:
        copy = read_copy(self.root, name)
        if copy.origin is None:
            raise MthError(f"{name} no es un agente instalado desde el catálogo.")
        return self._diff(name, copy, self._render_sync(name, copy))

    def remove(self, name: str) -> None:
        copy = read_copy(self.root, name)
        if copy.origin is None:
            raise MthError(f"{name} no es un agente instalado desde el catálogo: no se borra.",
                           hint="Un agente propio del repo se borra a mano.")
        changes = Changes(self.root)
        changes.files[AGENTS_DIR / f"{name}.md"] = None
        changes.files[GUARDS_DIR / f"{name}.guard.toml"] = None
        text = self._config_text()
        if name in self.cfg["review"]["agents"] or name in self.cfg["review"]["paths"]:
            changes.config_text = self._with_review(text, name, None, remove=True)
        if installed_names(self.root) == [name]:  # the last one: drop the shared infrastructure
            changes.files[SHIM] = None
            settings = read_settings(self.root)
            if has_hook(settings):
                changes.settings = without_hook(settings)
        changes.apply()
        say(f"✓ {name} desinstalado.")


# -- doctor ------------------------------------------------------------------------
def doctor_findings(root: Path, cfg: Config, launcher: Path, catalog_dir: Path = catalog.CATALOG_DIR) -> list[str]:
    """Warnings about the installed catalog agents (empty when everything is in order)."""
    names = installed_names(root)
    if not names:
        return []
    out = []
    manager = Manager(cfg, catalog_dir)
    for name in names:
        copy = read_copy(root, name)
        if copy.guard is None:
            out.append(f"Agente {name}: falta {GUARDS_DIR}/{name}.guard.toml (sus herramientas quedan bloqueadas; "
                       "mth agents sync).")
            continue
        state = manager.status(name)
        if state.startswith(("desactualizado", "editado")):
            out.append(f"Agente {name}: {state} (mth agents diff {name}).")
        try:
            required = catalog.load_meta(catalog_dir, name).get("local_required")
        except MthError:
            required = False
        if required and local_is_empty(copy.md or ""):
            out.append(f"Agente {name}: su sección local obligatoria está vacía.")
    if not (root / SHIM).is_file():
        out.append(f"Falta {SHIM}: los subagentes quedan bloqueados (mth agents sync).")
    try:
        settings = read_settings(root)
    except MthError as exc:
        settings = {}
        out.append(exc.message)
    if not has_hook(settings):
        out.append(f"Falta la entrada PreToolUse de {SETTINGS}: los agentes del catálogo no tienen guard "
                   "(mth agents sync).")
    for rel in (SETTINGS, Path(".claude") / "settings.local.json"):
        path = root / rel
        try:
            if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("disableAllHooks"):
                out.append(f"{rel} declara disableAllHooks: el guard de los agentes no se ejecuta.")
        except (json.JSONDecodeError, AttributeError):
            pass
    lines = launcher.read_text(encoding="utf-8").splitlines() if launcher.is_file() else []
    if len(lines) < 2 or not all(Path(p).is_file() for p in lines[:2]):
        out.append("No hay lanzador registrado para el guard de los agentes: abre una sesión nueva de Claude Code.")
    if cfg["language"]["docs"] != "es":
        out.append(f"language.docs = \"{cfg['language']['docs']}\" y los agentes del catálogo están en español.")
    return out
