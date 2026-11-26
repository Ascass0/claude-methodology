"""Adoption of the methodology in a repository: init, doctor and git hooks."""
from __future__ import annotations

import json
import re
import shlex
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import adoption, agents, changelog, commits, forge, lang, secretci, secretgate, survey, versions, work
from .files import atomic_write
from .config import CONFIG_PATH, Config, load, parse
from .ids import IdRegistry
from .errors import MthError
from .gh import GitHub
from .git import Git
from .log import say, warn

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
PLUGIN_AGENTS = Path(__file__).resolve().parents[2] / "agents"
MTH = Path(__file__).resolve().parents[1] / "mth"  # launcher: picks a Python >= 3.11
HOOK_MARK = "# managed-by: claude-methodology"
BLOCK_START = "<!-- claude-methodology:start -->"
BLOCK_END = "<!-- claude-methodology:end -->"
ADOPT_BRANCH = "chore/adopt-methodology"
RECONFIGURE_BRANCH = "chore/reconfigure-methodology"  # SPEC-0011
ADR_SUBDIR = "methodology"  # generated adoption, reconfiguration and update ADRs live under <paths.adr>/
RECONFIGURED_HEADER = "# claude-methodology · regenerado por `mth reconfigure` (ver el ADR de reestructuración).\n"
METHODOLOGY_ADR = re.compile(r"-(adopcion|adoption|reestructuracion|reconfiguration|actualizacion|update)-(de|of)-claude-methodology\.md$")
MARKETPLACE = "claude-methodology"
PLUGIN = "methodology"


# -- git hooks ----------------------------------------------------------------
@dataclass(frozen=True)
class HookKind:
    """A git hook that mth manages: the file name, its ``[hooks]`` key and what its script runs."""
    name: str
    key: str
    command: str  # mth subcommand and arguments
    argument: str  # what the foreign hook it chains to receives
    instruction: str  # what a versioned hooks directory needs by hand


COMMIT_MSG = HookKind("commit-msg", "commit_msg", 'check-msg "$1"', ' "$1"',
                      'Añade `mth check-msg "$1"` al hook commit-msg de tu gestor de hooks.')
PRE_COMMIT = HookKind("pre-commit", "pre_commit", "secrets --staged", "",
                      "Añade `mth secrets --staged` al hook pre-commit de tu gestor de hooks.")
CHAINED_HOOK = f"{COMMIT_MSG.name}.local"
REPLACED_HOOK = f"{COMMIT_MSG.name}.pre-mth"


def _chained(kind: HookKind) -> str:
    return f"{kind.name}.local"


def _replaced(kind: HookKind) -> str:
    return f"{kind.name}.pre-mth"


def hook_script(chain: bool = False, kind: HookKind = COMMIT_MSG) -> str:
    mth = shlex.quote(str(MTH))
    chained = ""
    if chain:  # SPEC-0006: the repo's own hook runs first and can reject the message
        chained = ('chained="$(dirname "$0")/' + _chained(kind) + '"\n'
                   'if [ ! -x "$chained" ]; then\n'
                   f"  echo '✗ falta el hook encadenado {_chained(kind)} o no es ejecutable: restáuralo o cambia hooks.{kind.key}' >&2\n"
                   "  exit 1\nfi\n"
                   f'"$chained"{kind.argument} || exit $?\n')
    return ("#!/bin/sh\n" f"{HOOK_MARK}\n"
            f"if [ ! -f {mth} ]; then\n"
            "  echo '✗ claude-methodology no encontrado: abre una sesión de Claude Code o ejecuta mth doctor' >&2\n"
            "  exit 1\nfi\n"
            f"{chained}"
            f"exec sh {mth} {kind.command}\n")


def _versioned_hooks(git: Git) -> bool:
    hooks = git.hooks_dir().resolve()
    return hooks.is_relative_to(git.root.resolve()) and not hooks.is_relative_to(git.git_dir().resolve())


def check_hook_mode(git: Git, mode: str, kind: HookKind = COMMIT_MSG) -> None:
    """Fail before any change when ``mode`` cannot be applied to a foreign hook.

    Raises:
        MthError: Same conditions as :func:`install_hook`.
    """
    path = git.hooks_dir() / kind.name
    if mode == "own" or not path.exists() or HOOK_MARK in path.read_text(encoding="utf-8", errors="replace"):
        return
    if _versioned_hooks(git):
        raise MthError(f"El directorio de hooks ({git.hooks_dir()}) está versionado: lo gestiona otra herramienta.",
                       hint=kind.instruction)
    backup = git.hooks_dir() / (_chained(kind) if mode == "chain" else _replaced(kind))
    if backup.exists():
        raise MthError(f"No se puede guardar el hook {kind.name} ajeno: {backup.name} ya existe.",
                       hint="Revisa ese fichero y bórralo o renómbralo antes de volver a instalar.")


def install_hook(git: Git, mode: str = "own", kind: HookKind = COMMIT_MSG) -> str:
    """Install or refresh a hook according to ``hooks.<key>``. Returns a status word.

    ``own`` never touches a foreign hook (``foreign``); ``replace`` keeps it as
    ``<name>.pre-mth`` (``replaced``); ``chain`` keeps it as ``<name>.local``
    and runs it first (``chained``).

    Raises:
        MthError: ``replace``/``chain`` on a versioned hooks directory, or the backup name is taken.
    """
    hooks = git.hooks_dir()
    path = hooks / kind.name
    desired = hook_script(chain=mode == "chain", kind=kind)
    status = "installed"
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARK in current:
            if current == desired:
                return "current"
        elif mode == "own":
            return "foreign"
        else:
            check_hook_mode(git, mode, kind)
            path.rename(hooks / (_chained(kind) if mode == "chain" else _replaced(kind)))
            status = "chained" if mode == "chain" else "replaced"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desired, encoding="utf-8")
    path.chmod(0o755)
    return status


def hook_state(git: Git, mode: str = "own", kind: HookKind = COMMIT_MSG) -> str:
    """Read-only state of a hook: ``current``, ``stale`` (ours, outdated), ``foreign`` or ``absent``."""
    path = git.hooks_dir() / kind.name
    if not path.exists():
        return "absent"
    current = path.read_text(encoding="utf-8", errors="replace")
    if HOOK_MARK not in current:
        return "foreign"
    return "current" if current == hook_script(chain=mode == "chain", kind=kind) else "stale"


def secrets_workflow_applies(cfg: Config) -> bool:
    """The secrets workflow is written only with ``secrets.ci = "on"``, GitHub and a required CI (SPEC-0024)."""
    return cfg["secrets"]["ci"] == "on" and cfg.forge == forge.GITHUB and cfg["ci"]["required"]


def sync_secrets_workflow(root: Path, cfg: Config) -> str | None:
    """Write the secrets workflow when it applies. Returns the previous state (``foreign`` = left alone) or None.

    Raises:
        MthError: ``secrets.baseline`` has characters that are unsafe inside the workflow.
    """
    return secretci.install(root, cfg["secrets"]["baseline"]) if secrets_workflow_applies(cfg) else None


def remove_hook(git: Git, kind: HookKind) -> bool:
    """Delete our hook (never a foreign one nor the saved copies). True when something was removed."""
    path = git.hooks_dir() / kind.name
    if path.is_file() and HOOK_MARK in path.read_text(encoding="utf-8", errors="replace"):
        path.unlink()
        return True
    return False


def sync_secrets_hook(git: Git, cfg: Config) -> str | None:
    """Apply ``secrets.hook`` to the pre-commit hook (SPEC-0024): install on ``on``, retire ours on ``off``.

    Returns the install status, ``removed``, or None when there is nothing to do (undecided).

    Raises:
        MthError: Same conditions as :func:`install_hook`.
    """
    switch = cfg["secrets"]["hook"]
    if switch == "on":
        return install_hook(git, cfg["hooks"]["pre_commit"], PRE_COMMIT)
    if switch == "off" and remove_hook(git, PRE_COMMIT):
        return "removed"
    return None


LAUNCHER = Path("mth") / "launcher"
MTH_PY = MTH.parent / "mth.py"


def register_launcher(git: Git) -> Path:
    """Record the interpreter and ``mth.py`` in ``<git-common-dir>/mth/launcher`` for the agent-guard shim.

    The plugin path changes with every version, like the commit-msg hook. The interpreter is
    the one already validated for this session (>= 3.11): the shim runs it directly, skipping
    the launcher's interpreter search on every subagent tool call (SPEC-0012).
    """
    path = git.common_dir() / LAUNCHER
    record = f"{sys.executable}\n{MTH_PY}\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != record:
        atomic_write(path, record)  # concurrent sessions never leave a half-written record
    return path


# -- scaffolding ----------------------------------------------------------------
def _claude_block(paths: dict, vocab: lang.Vocabulary) -> str:
    text = (vocab.templates / "claude-block.md").read_text(encoding="utf-8")
    for key, value in paths.items():
        text = text.replace("{{" + key.upper() + "}}", str(value))
    return text.strip()


def claude_block_state(root: Path, paths: dict, vocab: lang.Vocabulary = lang.ES) -> str:
    """Read-only state of the methodology block in ``paths.claude_md``: ``current``, ``stale`` or ``absent``."""
    path = root / paths["claude_md"]
    try:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise MthError(f"No se puede leer {path.name}: {exc}.", hint="Corrige el fichero o su codificación (UTF-8).") from exc
    if BLOCK_START not in current or BLOCK_END not in current:
        return "absent"
    block = BLOCK_START + current.split(BLOCK_START, 1)[1].split(BLOCK_END, 1)[0] + BLOCK_END
    return "current" if block == _claude_block(paths, vocab) else "stale"


def upsert_claude_md(root: Path, paths: dict, vocab: lang.Vocabulary = lang.ES) -> None:
    """Insert or refresh the methodology block in ``paths.claude_md`` (other content untouched)."""
    path = root / paths["claude_md"]
    path.parent.mkdir(parents=True, exist_ok=True)
    block = _claude_block(paths, vocab)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if BLOCK_START in current and BLOCK_END in current:
        head, rest = current.split(BLOCK_START, 1)
        tail = rest.split(BLOCK_END, 1)[1]
        new = f"{head}{block}{tail}"
    else:
        new = (current.rstrip() + "\n\n" if current.strip() else "") + block + "\n"
    path.write_text(new, encoding="utf-8")


def _ensure_changelog(path: Path, vocab: lang.Vocabulary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text((vocab.templates / "CHANGELOG.md").read_text(encoding="utf-8"), encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    if changelog.MARKER in text:
        return
    lines = text.splitlines()
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
    lines[idx:idx] = [changelog.MARKER, ""]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    warn(f"Marcador de versiones añadido a {path.name}.")


def _merge_settings(root: Path, marketplace_repo: str) -> None:
    path = root / ".claude" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("extraKnownMarketplaces", {})[MARKETPLACE] = {
        "source": {"source": "github", "repo": marketplace_repo}}
    data.setdefault("enabledPlugins", {})[f"{PLUGIN}@{MARKETPLACE}"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def decline(start: Path) -> None:
    """Disable the plugin for this repository in ``.claude/settings.local.json`` (SPEC-0004).

    Raises:
        MthError: The settings file exists but is not a JSON object (it is not overwritten).
    """
    root = Git.discover(start).root
    path = root / ".claude" / "settings.local.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise MthError(f"{path.relative_to(root)} no es JSON válido; no se modifica.",
                       hint="Corrígelo a mano y vuelve a ejecutar mth init --decline.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("enabledPlugins", {}), dict):
        raise MthError(f"{path.relative_to(root)} no tiene la forma esperada; no se modifica.")
    data.setdefault("enabledPlugins", {})[f"{PLUGIN}@{MARKETPLACE}"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"✓ claude-methodology desactivado en este repo ({path.relative_to(root)}, no versionado).")


def init(start: Path, marketplace_repo: str | None, github: bool, config_file: str | None = None,
         answers_file: str | None = None, plan_only: bool = False) -> None:
    """Adopt the methodology on a dedicated branch and commit the scaffolding.

    Creates ``development`` from ``main`` when missing, then ``chore/adopt-methodology``
    with config, folders, changelog, CLAUDE.md block and plugin settings.

    Args:
        start: Any directory inside the repository.
        marketplace_repo: ``owner/repo`` of the marketplace to declare in settings.
        github: Apply merge settings and ruleset on GitHub.
        config_file: Prepared configuration (outside the repo) used instead of the template.
        answers_file: Interview answers (SPEC-0004): the configuration and an adoption ADR are generated from them.
        plan_only: Validate the answers and show the plan (SPEC-0015) without writing anything.

    Raises:
        MthError: Dirty tree, missing remote/main, already adopted or invalid configuration.
    """
    git = Git.discover(start)
    root = git.root
    git.require_clean()
    git.fetch()
    if not git.remote_has("main") and not git.remote_has("master"):
        raise MthError("El remoto no tiene rama main.", hint="Crea el repo con un commit inicial en main.")
    main = "main" if git.remote_has("main") else "master"
    if (root / CONFIG_PATH).exists():
        raise MthError("El repo ya tiene configuración de la metodología.", hint="Usa `mth doctor`.")
    plan = inventory = None
    if plan_only and not answers_file:
        raise MthError("--plan necesita --answers.", hint="mth init --answers FICHERO --plan")
    if answers_file:
        inventory = survey.run(git)
        answers = adoption.load_answers(Path(answers_file).expanduser())
        adoption.validate(inventory, answers)
        start_ref = "development" if git.remote_has("development") else main
        plan = adoption.build((TEMPLATES / "methodology.toml").read_text(encoding="utf-8"), inventory, answers,
                              main, git.sha(git.remote_ref(start_ref)))
        config = ("# claude-methodology · generado por `mth init --answers` (ver el ADR de adopción).\n"
                  "# Referencia comentada de cada clave: templates/methodology.toml del plugin.\n"
                  + adoption.dump_toml(plan.data))
    elif config_file:
        source = Path(config_file).expanduser()
        if not source.is_file():
            raise MthError(f"No existe el fichero de configuración {source}.")
        config = source.read_text(encoding="utf-8")
    else:
        config = (TEMPLATES / "methodology.toml").read_text(encoding="utf-8").replace('main = "main"', f'main = "{main}"')
        detected = forge.forge_of(git.remote_url())
        config = config.replace('forge = "github"', f'forge = "{detected}"')
        if detected != forge.GITHUB or not (root / ".github" / "workflows").is_dir():
            config = config.replace("required = true", "required = false  # TODO: activar cuando el repo tenga CI")
    cfg = parse(root, config, config_file or answers_file or "plantilla")  # validate before any mutation
    check_hook_mode(git, cfg["hooks"]["commit_msg"])
    if cfg["secrets"]["hook"] == "on":
        check_hook_mode(git, cfg["hooks"]["pre_commit"], PRE_COMMIT)
    if secrets_workflow_applies(cfg):
        secretci.render(cfg["secrets"]["baseline"])  # fail before any mutation on an unsafe baseline
    chosen = plan.catalog if plan is not None else []
    blockers = agents.Manager(cfg).blockers(chosen)  # SPEC-0012: before any mutation
    if blockers:
        raise MthError("No se pueden instalar los agentes del catálogo elegidos:\n"
                       + "\n".join(f"  - {b}" for b in blockers),
                       hint="Quítalos de 'catalog' en la respuesta 'revisores' o completa su configuración.")
    for ref in cfg["commits"]["external_refs"]:
        if not git.ok("rev-parse", "--verify", "--quiet", ref):
            raise MthError(f"No existe la referencia externa {ref}.", hint="Trae el remoto externo (git fetch upstream).")
    if plan is not None:
        print(adoption.summary_text(inventory, plan))
    if plan_only:
        return

    if not git.remote_has(cfg.development):
        git.out("branch", cfg.development, git.remote_ref(cfg.main))
        git.push(cfg.development)
        say(f"· Rama {cfg.development} creada desde {cfg.main}")
    git.checkout_synced(cfg.development)
    if git.remote_has(ADOPT_BRANCH) or git.local_has(ADOPT_BRANCH):
        raise MthError(f"La rama {ADOPT_BRANCH} ya existe.")
    git.out("checkout", "-b", ADOPT_BRANCH)

    (root / CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_PATH).write_text(config, encoding="utf-8")
    for key in ("docs", "specs", "adr", "changes"):
        folder = root / cfg["paths"][key]
        folder.mkdir(parents=True, exist_ok=True)
        if not any(folder.iterdir()):
            (folder / ".gitkeep").touch()
    _ensure_changelog(root / cfg["paths"]["changelog"], cfg.vocab)
    upsert_claude_md(root, cfg["paths"], cfg.vocab)
    if marketplace_repo:
        _merge_settings(root, marketplace_repo)
    install_hook(git, cfg["hooks"]["commit_msg"])
    sync_secrets_hook(git, cfg)
    sync_secrets_workflow(root, cfg)
    if plan is not None:
        _write_adoption_adr(root, cfg, git, inventory, plan)
    if chosen and agents.Manager(load(root)).add(chosen, None, False):
        raise MthError("No se instalaron todos los agentes del catálogo elegidos.")

    git.out("add", "-A")
    message = commits.build("chore", "methodology", "adopt claude-methodology",
                            "Add the methodology configuration, document folders, changelog "
                            "with release marker and the Claude Code integration block.", [])
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fh:
        fh.write(message)
    try:
        git.out("commit", "-F", fh.name)
    finally:
        Path(fh.name).unlink(missing_ok=True)
    git.push(ADOPT_BRANCH)
    try:
        work.ensure(git, cfg["work"]["dirs"])  # SPEC-0010: local, so it never blocks the adoption
    except MthError as exc:
        warn(f"{exc.message} {exc.hint or ''}".strip())
    if github:
        configure_github(root, cfg.main, cfg.development)
    say(f"✓ Metodología adoptada en {ADOPT_BRANCH}. Revisa .claude/methodology.toml y "
        "completa commands.test y review.agents; después, mth integrate.")


# -- GitHub settings ------------------------------------------------------------
def _write_adoption_adr(root: Path, cfg, git: Git, inventory: survey.Survey, plan: adoption.Plan) -> None:
    ident = IdRegistry(cfg, git.files()).next_id(cfg["trace"]["adr_kind"])
    folder = root / cfg["paths"]["adr"] / ADR_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    slug = "adopcion-de-claude-methodology" if cfg.vocab.code == "es" else "adoption-of-claude-methodology"
    (folder / f"{ident}-{slug}.md").write_text(adoption.adr_text(ident, inventory, plan, cfg.vocab), encoding="utf-8")
    say(f"· ADR de adopción: {(folder / f'{ident}-{slug}.md').relative_to(root)}")


def _chainable(git: Git) -> bool:
    """A foreign commit-msg hook exists, or was already kept as the chained one."""
    hooks = git.hooks_dir()
    hook = hooks / "commit-msg"
    foreign = hook.is_file() and HOOK_MARK not in hook.read_text(encoding="utf-8", errors="replace")
    return foreign or (hooks / CHAINED_HOOK).is_file()


def reconfigure(start: Path, answers_file: str, only: str | None = None) -> None:
    """Apply reconfiguration answers on a dedicated branch (SPEC-0011, ADR-0007).

    Everything is validated before the branch is created: the answers against the
    reconfiguration inventory, the resulting configuration and the hook mode.

    Raises:
        MthError: Not adopted, dirty tree, branch already exists, invalid answers or
            configuration, missing integration branch, or nothing to change.
    """
    git = Git.discover(start)
    root = git.root
    if not (root / CONFIG_PATH).is_file():
        raise MthError("El repositorio no ha adoptado la metodología.", hint="Usa la skill mth-init.")
    cfg = load(root)
    git.remote = cfg.remote
    git.require_clean()
    git.fetch()
    if git.remote_has(RECONFIGURE_BRANCH) or git.local_has(RECONFIGURE_BRANCH):
        raise MthError(f"La rama {RECONFIGURE_BRANCH} ya existe.", hint="Intégrala o bórrala antes de reestructurar.")
    inventory = survey.reconfigure(git, cfg, only)
    answers = adoption.load_answers(Path(answers_file).expanduser())
    adoption.validate(inventory, answers)
    text = (root / CONFIG_PATH).read_text(encoding="utf-8")
    plan, tables, changes = adoption.rebuild(cfg.data, tomllib.loads(text), inventory, answers,
                                             git.sha(git.remote_ref(cfg.development)))
    config_text = RECONFIGURED_HEADER + adoption.dump_toml(tables)
    new_cfg = parse(root, config_text, answers_file)  # validate before any mutation
    check_hook_mode(git, new_cfg["hooks"]["commit_msg"])
    if new_cfg["secrets"]["hook"] == "on":
        check_hook_mode(git, new_cfg["hooks"]["pre_commit"], PRE_COMMIT)
    if secrets_workflow_applies(new_cfg):
        secretci.render(new_cfg["secrets"]["baseline"])
    if new_cfg["hooks"]["commit_msg"] == "chain" and not _chainable(git):
        raise MthError("hooks.commit_msg = chain necesita un hook commit-msg ajeno que encadenar, y no hay ninguno.",
                       hint="Conserva el modo actual: encadenar sin hook rechazaría todos los commits.")
    pending = [d for d in plan.decisions if d.migration]
    if not changes and not pending:
        raise MthError("Las respuestas no cambian nada: nada que cambiar.", hint="La configuración ya es esa.")
    if new_cfg.development != cfg.development and not git.remote_has(new_cfg.development):
        if answers.get("ramas", {}).get("option") != "crear":
            raise MthError(f"La rama {new_cfg.development} no existe en el remoto.",
                           hint="Créala antes o responde 'crear'.")
        git.out("branch", new_cfg.development, git.remote_ref(cfg.main))
        git.push(new_cfg.development)
        say(f"· Rama {new_cfg.development} creada desde {cfg.main}")

    git.checkout_synced(cfg.development)
    git.out("checkout", "-b", RECONFIGURE_BRANCH)
    (root / CONFIG_PATH).write_text(config_text, encoding="utf-8")
    previous = sorted(p.name[:m.start()] for p in (root / cfg["paths"]["adr"] / ADR_SUBDIR).glob("*.md")
                      if (m := METHODOLOGY_ADR.search(p.name)))
    ident = IdRegistry(new_cfg, git.files()).next_id(new_cfg["trace"]["adr_kind"])
    folder = root / new_cfg["paths"]["adr"] / ADR_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    slug = "reestructuracion-de-claude-methodology" if new_cfg.vocab.code == "es" else "reconfiguration-of-claude-methodology"
    adr = folder / f"{ident}-{slug}.md"
    adr.write_text(adoption.reconfigure_adr_text(ident, previous[-1] if previous else None, plan, changes, new_cfg.vocab), encoding="utf-8")
    install_hook(git, new_cfg["hooks"]["commit_msg"])
    sync_secrets_hook(git, new_cfg)
    sync_secrets_workflow(root, new_cfg)

    git.out("add", "-A")
    message = commits.build("chore", "methodology", "reconfigure claude-methodology",
                            "Apply the answers of the reconfiguration interview on top of the current "
                            "configuration and record the decisions.", [ident])
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fh:
        fh.write(message)
    try:
        git.out("commit", "-F", fh.name)
    finally:
        Path(fh.name).unlink(missing_ok=True)
    git.push(RECONFIGURE_BRANCH)
    say(f"· ADR de reestructuración: {adr.relative_to(root)}")
    for change in changes:
        say(f"· {change.key}: {change.before!r} → {change.after!r}")
    for decision in pending:
        warn(f"Migración pendiente en {RECONFIGURE_BRANCH}: {decision.question} ({decision.option}) — {decision.effect}")
    say(f"✓ Reestructuración en {RECONFIGURE_BRANCH}. Haz las migraciones pendientes y después mth integrate.")


def configure_github(root: Path, main: str, development: str) -> None:
    """Merge commits only, no auto-delete (mth deletes branches) and protected long-lived branches.

    Failures are reported, not fatal: repository settings need admin rights and
    the local flow stays correct without them (mth enforces the same rules).
    """
    hub = GitHub(root, Git(root).github_repo())
    hub.ensure_ready()
    repo = hub.api("GET", "repos/{owner}/{repo}").stdout
    full = json.loads(repo)["full_name"]
    settings = {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False,
                "delete_branch_on_merge": False, "merge_commit_title": "PR_TITLE",
                "merge_commit_message": "PR_BODY"}
    if hub.api("PATCH", f"repos/{full}", settings, check=False).returncode != 0:
        warn("No se pudieron aplicar los ajustes de merge (¿permisos de admin?).")
    else:
        say("· Ajustes de merge aplicados: solo merge commits")
    ruleset = {"name": "claude-methodology", "target": "branch", "enforcement": "active",
               "conditions": {"ref_name": {"include": [f"refs/heads/{main}", f"refs/heads/{development}"],
                                           "exclude": []}},
               "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                         {"type": "pull_request", "parameters": {
                             "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                             "require_code_owner_review": False, "require_last_push_approval": False,
                             "required_review_thread_resolution": False, "allowed_merge_methods": ["merge"]}}]}
    existing = json.loads(hub.api("GET", f"repos/{full}/rulesets", check=False).stdout or "[]")
    current = next((r for r in existing if isinstance(r, dict) and r.get("name") == ruleset["name"]), None)
    method, path = ("PUT", f"repos/{full}/rulesets/{current['id']}") if current else ("POST", f"repos/{full}/rulesets")
    if hub.api(method, path, ruleset, check=False).returncode != 0:
        warn(f"No se pudo crear el ruleset de {main}/{development} (¿permisos o plan de GitHub?).")
    else:
        say(f"· Ruleset aplicado: {main} y {development} solo por PR, sin borrado ni force-push")


# -- doctor ---------------------------------------------------------------------
def _report_work(report, status: work.Status) -> None:
    name = f"Directorio de trabajo {work.WORK_DIR}/"
    if status.blocked:
        report(False, f"{name}: {status.blocked}")
    elif status.ready:
        report(True, f"{name} (local, excluido de git)")
    else:
        gaps = ([f"faltan {', '.join(status.missing)}"] if status.missing else []) + \
               ([] if status.excluded else ["sin excluir de git"])
        report(False, f"{name}: {'; '.join(gaps)} (lo prepara la próxima sesión)", blocking=False)


def _doctor_secrets_pieces(git: Git, cfg: Config, report) -> None:
    """Hook, workflow and tool version of the secrets gate: warnings, never blocking (SPEC-0024/AC-14)."""
    switch = cfg["secrets"]["hook"]
    if switch == "":
        report(False, "secrets.hook sin decidir: no se escanea lo preparado antes de cada commit (mth update --plan)",
               blocking=False)
    elif switch == "on":
        try:
            state = hook_state(git, cfg["hooks"]["pre_commit"], PRE_COMMIT)
        except OSError as exc:
            state = f"ilegible ({exc})"
        report(state == "current", f"Hook pre-commit de secretos: {state}", blocking=False)
    if cfg["secrets"]["ci"] == "":
        if cfg.forge == forge.GITHUB and cfg["ci"]["required"]:
            report(False, "secrets.ci sin decidir: la CI no escanea secretos en cada PR (mth update --plan)",
                   blocking=False)
    elif cfg["secrets"]["ci"] == "on" and secrets_workflow_applies(cfg):
        state = secretci.state(git.root, cfg["secrets"]["baseline"])
        report(state == "current", f"Workflow de secretos: {state}", blocking=False)
    if cfg["secrets"]["mode"] == "block" or switch == "on":
        found = secretgate.version()
        if secretgate.is_installed():
            minimum = ".".join(map(str, secretgate.MIN_VERSION))
            report(found is not None and found >= secretgate.MIN_VERSION,
                   f"gitleaks {'.'.join(map(str, found)) if found else 'de versión no reconocida'} (mínima {minimum})",
                   blocking=False)


def doctor(start: Path) -> int:
    """Check the repository adoption. Returns the number of blocking problems."""
    problems = 0

    def report(ok: bool, msg: str, blocking: bool = True) -> None:
        nonlocal problems
        mark = "✓" if ok else ("✗" if blocking else "⚠")
        print(f"{mark} {msg}")
        if not ok and blocking:
            problems += 1

    report(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}")
    git = Git.discover(start)
    try:
        cfg = load(git.root)
    except MthError as exc:
        report(False, f"Configuración: {exc.message}" + (f"\n  → {exc.hint}" if exc.hint else ""))  # SPEC-0009
        return problems
    report(True, f"Configuración válida ({CONFIG_PATH})")
    git.remote = cfg.remote
    report(git.has_remote(), f"Remoto '{cfg.remote}'")
    if git.has_remote():
        git.fetch()
        for branch in (cfg.main, cfg.development):
            report(git.remote_has(branch), f"Rama {branch} en el remoto")
    if cfg.forge == forge.GITHUB:
        gh_ok = GitHub(git.root)._gh("auth", "status", check=False).returncode == 0 if _has_gh() else False
        report(gh_ok, "gh instalado y autenticado")
    else:
        report(True, f"forge = {cfg.forge}: mth integrate y mth release hacen solo la parte local")
    try:
        status = install_hook(git, cfg["hooks"]["commit_msg"])
        report(status != "foreign", f"Hook commit-msg: {status}")
    except MthError as exc:
        report(False, f"Hook commit-msg: {exc.message}")
    for key in ("docs", "specs", "adr", "changes"):
        report((git.root / cfg["paths"][key]).is_dir(), f"Directorio {cfg['paths'][key]}/")
    log_path = git.root / cfg["paths"]["changelog"]
    report(log_path.is_file() and changelog.MARKER in log_path.read_text(encoding="utf-8"),
           f"{cfg['paths']['changelog']} con marcador de versiones")
    latest = ".".join(map(str, git.latest_version(cfg.tag_prefix)))
    for item in versions.from_config(cfg["release"]["version_files"]):
        try:
            declared = versions.read(git.root, item)
        except MthError as exc:
            report(False, f"Fichero de versión: {exc.message}")
            continue
        report(declared == latest, f"Fichero de versión {item.path}: {declared}"
               + ("" if declared == latest else f" (última etiqueta: {latest})"), blocking=False)
    _report_work(report, work.inspect(git, cfg["work"]["dirs"]))
    claude_md = git.root / cfg["paths"]["claude_md"]
    report(claude_md.is_file() and BLOCK_START in claude_md.read_text(encoding="utf-8"),
           f"Bloque de la metodología en {cfg['paths']['claude_md']}")
    for ref in cfg["commits"]["external_refs"]:
        report(git.ok("rev-parse", "--verify", "--quiet", ref), f"Referencia externa {ref}")
    for agent in cfg["review"]["agents"]:
        where = agent_location(git.root, agent)
        scope = f" solo si cambian {', '.join(cfg['review']['paths'][agent])}" if agent in cfg["review"]["paths"] else ""
        report(where is not None, f"Revisor {agent} ({where or 'no encontrado'}){scope}")
    for role, agent in cfg["roles"].items():
        if agent:
            where = agent_location(git.root, agent)
            report(where is not None, f"Rol {role} → {agent} ({where or 'no encontrado'})")
    installed = agents.catalog_names(git.root)
    if installed:  # SPEC-0012: warnings only
        findings = agents.doctor_findings(git.root, cfg, git.common_dir() / LAUNCHER)
        for finding in findings:
            report(False, finding, blocking=False)
        if not findings:
            report(True, f"Agentes del catálogo: {', '.join(installed)}")
        from . import smoke  # lazy: smoke builds on setup (SPEC-0014)
        for notice in smoke.warnings(git, True, explain_unknown=True):
            report(False, notice, blocking=False)
    mode = cfg["secrets"]["mode"]
    if mode == "block" or cfg["secrets"]["hook"] == "on":
        report(secretgate.is_installed(), "gitleaks instalado (secrets.mode = block o secrets.hook = on)")
    else:
        report(False, "secrets.mode " + ("sin decidir" if mode == "" else "= off")
               + ": no se buscan secretos al integrar (mth update --plan)", blocking=False)
    _doctor_secrets_pieces(git, cfg, report)
    report(bool(cfg["review"]["agents"]) or not cfg["review"]["required_for"],
           "review.agents declarado (la revisión es obligatoria)", blocking=False)
    report(cfg.test_command != "", "commands.test configurado", blocking=False)
    if cfg.forge == forge.GITHUB:
        report(cfg["ci"]["required"], "ci.required = true", blocking=False)
    return problems


def agent_location(root: Path, agent: str) -> str | None:
    """Where an agent is defined: the repository or this plugin (shared agents)."""
    if (root / ".claude" / "agents" / f"{agent}.md").is_file():
        return f".claude/agents/{agent}.md"
    if (PLUGIN_AGENTS / f"{agent}.md").is_file():
        return "plugin claude-methodology"
    return None


def _has_gh() -> bool:
    from shutil import which
    return which("gh") is not None
