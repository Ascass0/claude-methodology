"""Adoption of the methodology in a repository: init, doctor and git hooks."""
from __future__ import annotations

import json
import shlex
import sys
import tempfile
from pathlib import Path

from . import adoption, changelog, commits, lang, survey, versions
from .config import CONFIG_PATH, load, parse
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
MARKETPLACE = "claude-methodology"
PLUGIN = "methodology"


# -- git hook -----------------------------------------------------------------
CHAINED_HOOK = "commit-msg.local"
REPLACED_HOOK = "commit-msg.pre-mth"


def hook_script(chain: bool = False) -> str:
    mth = shlex.quote(str(MTH))
    chained = ""
    if chain:  # SPEC-0006: the repo's own hook runs first and can reject the message
        chained = ('chained="$(dirname "$0")/' + CHAINED_HOOK + '"\n'
                   'if [ ! -x "$chained" ]; then\n'
                   f"  echo '✗ falta el hook encadenado {CHAINED_HOOK} o no es ejecutable: restáuralo o cambia hooks.commit_msg' >&2\n"
                   "  exit 1\nfi\n"
                   '"$chained" "$1" || exit $?\n')
    return ("#!/bin/sh\n" f"{HOOK_MARK}\n"
            f"if [ ! -f {mth} ]; then\n"
            "  echo '✗ claude-methodology no encontrado: abre una sesión de Claude Code o ejecuta mth doctor' >&2\n"
            "  exit 1\nfi\n"
            f"{chained}"
            f'exec sh {mth} check-msg "$1"\n')


def _versioned_hooks(git: Git) -> bool:
    hooks = git.hooks_dir().resolve()
    return hooks.is_relative_to(git.root.resolve()) and not hooks.is_relative_to(git.git_dir().resolve())


def check_hook_mode(git: Git, mode: str) -> None:
    """Fail before any change when ``mode`` cannot be applied to a foreign hook.

    Raises:
        MthError: Same conditions as :func:`install_hook`.
    """
    path = git.hooks_dir() / "commit-msg"
    if mode == "own" or not path.exists() or HOOK_MARK in path.read_text(encoding="utf-8", errors="replace"):
        return
    if _versioned_hooks(git):
        raise MthError(f"El directorio de hooks ({git.hooks_dir()}) está versionado: lo gestiona otra herramienta.",
                       hint='Añade `mth check-msg "$1"` al hook commit-msg de tu gestor de hooks.')
    backup = git.hooks_dir() / (CHAINED_HOOK if mode == "chain" else REPLACED_HOOK)
    if backup.exists():
        raise MthError(f"No se puede guardar el hook commit-msg ajeno: {backup.name} ya existe.",
                       hint="Revisa ese fichero y bórralo o renómbralo antes de volver a instalar.")


def install_hook(git: Git, mode: str = "own") -> str:
    """Install or refresh the commit-msg hook according to ``hooks.commit_msg``. Returns a status word.

    ``own`` never touches a foreign hook (``foreign``); ``replace`` keeps it as
    ``commit-msg.pre-mth`` (``replaced``); ``chain`` keeps it as ``commit-msg.local``
    and runs it first (``chained``).

    Raises:
        MthError: ``replace``/``chain`` on a versioned hooks directory, or the backup name is taken.
    """
    hooks = git.hooks_dir()
    path = hooks / "commit-msg"
    desired = hook_script(chain=mode == "chain")
    status = "installed"
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARK in current:
            if current == desired:
                return "current"
        elif mode == "own":
            return "foreign"
        else:
            check_hook_mode(git, mode)
            path.rename(hooks / (CHAINED_HOOK if mode == "chain" else REPLACED_HOOK))
            status = "chained" if mode == "chain" else "replaced"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desired, encoding="utf-8")
    path.chmod(0o755)
    return status


# -- scaffolding ----------------------------------------------------------------
def _claude_block(paths: dict, vocab: lang.Vocabulary) -> str:
    text = (vocab.templates / "claude-block.md").read_text(encoding="utf-8")
    for key, value in paths.items():
        text = text.replace("{{" + key.upper() + "}}", str(value))
    return text.strip()


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
         answers_file: str | None = None) -> None:
    """Adopt the methodology on a dedicated branch and commit the scaffolding.

    Creates ``development`` from ``main`` when missing, then ``chore/adopt-methodology``
    with config, folders, changelog, CLAUDE.md block and plugin settings.

    Args:
        start: Any directory inside the repository.
        marketplace_repo: ``owner/repo`` of the marketplace to declare in settings.
        github: Apply merge settings and ruleset on GitHub.
        config_file: Prepared configuration (outside the repo) used instead of the template.
        answers_file: Interview answers (SPEC-0004): the configuration and an adoption ADR are generated from them.

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
        if not (root / ".github" / "workflows").is_dir():
            config = config.replace("required = true", "required = false  # TODO: activar cuando el repo tenga CI")
    cfg = parse(root, config, config_file or answers_file or "plantilla")  # validate before any mutation
    check_hook_mode(git, cfg["hooks"]["commit_msg"])
    for ref in cfg["commits"]["external_refs"]:
        if not git.ok("rev-parse", "--verify", "--quiet", ref):
            raise MthError(f"No existe la referencia externa {ref}.", hint="Trae el remoto externo (git fetch upstream).")

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
    if plan is not None:
        _write_adoption_adr(root, cfg, git, inventory, plan)

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
    if github:
        configure_github(root, cfg.main, cfg.development)
    say(f"✓ Metodología adoptada en {ADOPT_BRANCH}. Revisa .claude/methodology.toml y "
        "completa commands.test y review.agents; después, mth integrate.")


# -- GitHub settings ------------------------------------------------------------
def _write_adoption_adr(root: Path, cfg, git: Git, inventory: survey.Survey, plan: adoption.Plan) -> None:
    ident = IdRegistry(cfg, git.files()).next_id(cfg["trace"]["adr_kind"])
    folder = root / cfg["paths"]["adr"] / "methodology"
    folder.mkdir(parents=True, exist_ok=True)
    slug = "adopcion-de-claude-methodology" if cfg.vocab.code == "es" else "adoption-of-claude-methodology"
    (folder / f"{ident}-{slug}.md").write_text(adoption.adr_text(ident, inventory, plan, cfg.vocab), encoding="utf-8")
    say(f"· ADR de adopción: {(folder / f'{ident}-{slug}.md').relative_to(root)}")


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
    gh_ok = GitHub(git.root)._gh("auth", "status", check=False).returncode == 0 if _has_gh() else False
    report(gh_ok, "gh instalado y autenticado")
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
    report(bool(cfg["review"]["agents"]) or not cfg["review"]["required_for"],
           "review.agents declarado (la revisión es obligatoria)", blocking=False)
    report(cfg.test_command != "", "commands.test configurado", blocking=False)
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
