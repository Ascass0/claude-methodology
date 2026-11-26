"""Application of the automatic gaps on a dedicated branch (SPEC-0021, ADR-0017).

Nothing is created before everything that can fail has been computed and validated: the new
configuration text parses, and there is something to apply.
"""
from __future__ import annotations

import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__, adoption, agent_guard, agents, commits, config, lang, setup, update
from .config import CONFIG_PATH, load, parse
from .errors import MthError
from .files import atomic_write
from .git import Git
from .ids import IdRegistry
from .log import say, warn

BRANCH = "chore/update-methodology"
SLUG = {"es": "actualizacion-de-claude-methodology", "en": "update-of-claude-methodology"}
_TEXT = {
    "es": {"title": "Actualización de claude-methodology", "status": "Estado", "accepted": "aceptado",
           "date": "Fecha", "category": "Categoría",
           "context": "- Se pone el repo al día con claude-methodology {version} con `mth update`.",
           "previous": "- Parte de las decisiones registradas en {previous}.",
           "applied": "Se aplican las brechas automáticas de esta ejecución (sin cambiar ningún valor ya decidido):",
           "pending": "Quedan pendientes; las conduce la skill `mth-update` o la persona:",
           "none": "No quedan brechas pendientes.",
           "rejected": "- Cambiar valores ya decididos: es trabajo de `mth reconfigure`.\n"
                       "- Convertir documentos sin aprobación: es una migración que decide la persona.",
           "plus": "- **+** `mth update --plan` lista lo que falta y queda en «al día» al terminar.",
           "minus": "- **−** Lo pendiente exige trabajo aparte de esta rama.",
           "imposes": "- [script] `mth update --plan`: lista las brechas con su clase."},
    "en": {"title": "Update of claude-methodology", "status": "Status", "accepted": "accepted",
           "date": "Date", "category": "Category",
           "context": "- The repo is brought up to date with claude-methodology {version} using `mth update`.",
           "previous": "- It builds on the decisions recorded in {previous}.",
           "applied": "The automatic gaps of this run are applied (no decided value changes):",
           "pending": "Still pending; the `mth-update` skill or the person handles them:",
           "none": "No gaps are left.",
           "rejected": "- Changing decided values: that is the job of `mth reconfigure`.\n"
                       "- Converting documents without approval: a migration the person decides.",
           "plus": "- **+** `mth update --plan` lists what is missing and ends at \"up to date\".",
           "minus": "- **−** What is pending needs work outside this branch.",
           "imposes": "- [script] `mth update --plan`: lists the gaps with their class."},
}


def _nest(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    for key in reversed(path):
        value = {key: value}
    return value


def _lookup(tree: dict[str, Any], path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(tree, dict) or key not in tree:
            return None
        tree = tree[key]
    return tree


def _resolved(path: tuple[str, ...], value: Any) -> Any:
    """The default of a missing key: the configuration default, or the template value when there is none."""
    if isinstance(value, dict):
        return {k: _resolved((*path, k), v) for k, v in value.items()}
    default = _lookup(config.DEFAULTS, path)
    return value if default is None else default


def with_keys(text: str, template: dict[str, Any], missing: list[tuple[str, ...]]) -> str:
    """``text`` with every missing key added at its default; existing lines are never touched."""
    for path in missing:
        value = _resolved(path, _lookup(template, path))
        if isinstance(value, dict):
            text = text.rstrip("\n") + "\n\n" + adoption.dump_toml(_nest(path, value))
            continue
        line = adoption.dump_toml({path[-1]: value})
        if len(path) == 1:  # top-level scalars go before the first table
            first = re.search(r"^\[", text, re.M)
            at = first.start() if first else len(text)
            text = text[:at] + line + ("\n" if first else "") + text[at:]
            continue
        header = re.search(rf"^\[{re.escape('.'.join(path[:-1]))}\][ \t]*(#.*)?$", text, re.M)
        if header is None:
            text = text.rstrip("\n") + f"\n\n[{'.'.join(path[:-1])}]\n{line}"
        else:
            at = header.end() + 1 if header.end() < len(text) else header.end()
            text = text[:at] + line + text[at:]
    return text


def adr_text(ident: str, previous: str | None, applied: list[update.Gap], pending: list[update.Gap],
             vocab: lang.Vocabulary, today: date | None = None) -> str:
    """Update ADR of the target repository in its documentation language, in the compact format (ADR-0014)."""
    t = _TEXT[vocab.code]
    context, decision, rejected, consequences, imposes = vocab.adr_fields
    items = [f"   - `{g.id}`: {g.evidence}" for g in applied]
    rest = [f"   - `{g.id}` ({g.clase}): {g.evidence}" for g in pending]
    return "\n".join([
        *adoption.adr_header(ident, t, vocab, today),
        f"## {context}", "", t["context"].format(version=__version__),
        *([t["previous"].format(previous=previous)] if previous else []), "",
        f"## {decision}", "", f"1. {t['applied']}", *items,
        f"2. {t['pending'] if pending else t['none']}", *rest, "",
        f"## {rejected}", "", t["rejected"], "",
        f"## {consequences}", "", t["plus"], t["minus"], "",
        f"## {imposes}", "", t["imposes"], "",
    ])


def _begin(git: Git) -> bool:
    """Check the preconditions; returns whether the run resumes on the update branch itself."""
    if git.current_branch() == BRANCH:
        return True
    git.require_clean()
    git.fetch()
    if git.remote_has(BRANCH) or git.local_has(BRANCH):
        raise MthError(f"La rama {BRANCH} ya existe.", hint="Intégrala o bórrala antes de actualizar.")
    return False


def _unpushed(git: Git, development: str) -> bool:
    base = git.remote_ref(BRANCH) if git.remote_has(BRANCH) else git.remote_ref(development)
    return git.ahead_count(base) > 0


def _unfinished(repo: update.Repo) -> bool:
    """Work a previous run left on the branch: uncommitted changes in what it owns or a commit never pushed."""
    git = repo.git
    return bool(git.out("status", "--porcelain", "--", *_owned_paths(repo))) or _unpushed(git, repo.cfg.development)


def _existing_adr(git: Git, folder: Path, development: str) -> Path | None:
    """The update ADR this branch already wrote (not in ``development`` yet), so a resumed run reuses it."""
    dev = git.remote_ref(development)
    for path in sorted(folder.glob(f"*-{SLUG['es']}.md")) + sorted(folder.glob(f"*-{SLUG['en']}.md")):
        if not git.ok("cat-file", "-e", f"{dev}:{path.relative_to(git.root).as_posix()}"):
            return path
    return None


def _read_applied(text: str) -> list[update.Gap]:
    """Gaps an earlier run of this branch recorded in its ADR (the list under the first decision)."""
    found, inside = [], False
    for line in text.splitlines():
        if line.startswith("1. "):
            inside = True
        elif line.startswith("2. "):
            break
        elif inside and (m := re.match(r"   - `([^`]+)`: (.*)$", line)):
            found.append(update.Gap(m.group(1), update.AUTOMATIC, m.group(2), ""))
    return found


def _ident(adr: Path) -> str:
    """``ADR-0007`` from ``ADR-0007-actualizacion-de-claude-methodology.md``."""
    return "-".join(adr.name.split("-")[:2])


def _record(repo: update.Repo, automatic: list[update.Gap], pending: list[update.Gap]) -> Path:
    """Write (or extend) the update ADR before anything else changes, so a crash never loses what was planned."""
    git, cfg = repo.git, repo.cfg
    folder = git.root / cfg["paths"]["adr"] / setup.ADR_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    adr = _existing_adr(git, folder, cfg.development)
    previous_text = adr.read_text(encoding="utf-8") if adr else ""
    ident = _ident(adr) if adr else IdRegistry(cfg, git.files()).next_id(cfg["trace"]["adr_kind"])
    adr = adr or folder / f"{ident}-{SLUG[cfg.vocab.code]}.md"
    earlier = _read_applied(previous_text)
    seen = {(g.id, g.evidence) for g in earlier}
    applied = earlier + [g for g in automatic if (g.id, g.evidence) not in seen]
    others = sorted(p.name[:m.start()] for p in folder.glob("*.md")
                    if (m := setup.METHODOLOGY_ADR.search(p.name)) and p != adr)
    adr.write_text(adr_text(ident, others[-1] if others else None, applied, pending, cfg.vocab), encoding="utf-8")
    return adr


def _apply(repo: update.Repo, automatic: list[update.Gap], config_text: str) -> None:
    """Run every automatic gap (SPEC-0021): config keys, outdated agents, the CLAUDE.md block and the hook."""
    git = repo.git
    root = git.root
    ids = {g.id for g in automatic}
    outdated = update.outdated_agents(repo) if "agentes-desactualizados" in ids else []
    atomic_write(root / CONFIG_PATH, config_text)
    cfg = load(root)
    if outdated:
        agents.Manager(cfg).sync(outdated, False)
    if "bloque" in ids:
        setup.upsert_claude_md(root, cfg["paths"], cfg.vocab)
    if "hook" in ids:
        setup.install_hook(git, cfg["hooks"]["commit_msg"])


def _agent_files(name: str) -> list[Path]:
    return [agent_guard.AGENTS_DIR / f"{name}.md", agent_guard.GUARDS_DIR / f"{name}.guard.toml"]


def _owned_paths(repo: update.Repo) -> list[str]:
    """Only what ``mth update`` writes: a resumed run must not commit anything else in the tree."""
    root, cfg = repo.git.root, repo.cfg
    candidates = [CONFIG_PATH, Path(cfg["paths"]["claude_md"]), agents.SHIM, agents.SETTINGS, agents.GITIGNORE,
                  Path(cfg["paths"]["adr"]) / setup.ADR_SUBDIR,
                  *(f for name in agents.catalog_names(root) for f in _agent_files(name))]
    return [p.as_posix() for p in candidates if (root / p).exists()]


def _finish(repo: update.Repo, adr: Path) -> None:
    git = repo.git
    git.out("add", "--", *_owned_paths(repo))
    for name in update.edited_agents(repo):  # a hand-edited agent is the person's decision, never committed here
        git.out("reset", "-q", "--", *(f.as_posix() for f in _agent_files(name)))
    if not git.ok("diff", "--cached", "--quiet"):  # staged changes; otherwise a previous run committed them
        git.commit_message(commits.build("chore", "methodology", "update claude-methodology",
                                         "Bring the repository up to date with the installed plugin: apply the "
                                         "automatic gaps and record them.", [_ident(adr)]))
    git.push(BRANCH)


def _report(adr: Path, automatic: list[update.Gap], pending: list[update.Gap]) -> None:
    say(f"· ADR de actualización: {adr}")
    for gap in automatic:
        say(f"· aplicado {gap.id}: {gap.evidence}")
    for gap in pending:
        warn(f"Pendiente ({gap.clase}) {gap.id}: {gap.evidence}")
    say(f"✓ Actualización en {BRANCH}. Haz lo pendiente con la skill mth-update y después mth integrate.")


def apply(start: Path) -> None:
    """Apply the automatic gaps of the repository at ``start`` on ``chore/update-methodology``.

    Running it again on that branch resumes: it applies what is left, commits only the paths it owns,
    pushes a commit that was never pushed and extends the ADR it already wrote.

    Raises:
        MthError: Not adopted, dirty tree or the branch already exists (outside it), invalid
            configuration, or nothing to apply or finish.
    """
    repo = update.open_repo(start)
    git, cfg = repo.git, repo.cfg
    resuming = _begin(git)
    gaps = update.diagnose(repo)
    automatic = [g for g in gaps if g.clase == update.AUTOMATIC]
    pending = [g for g in gaps if g.clase != update.AUTOMATIC]
    if not automatic and not (resuming and _unfinished(repo)):
        raise MthError("Nada que aplicar: no hay brechas automáticas.", hint="mth update --plan muestra lo pendiente.")
    text = (git.root / CONFIG_PATH).read_text(encoding="utf-8")
    if any(g.id == "config" for g in automatic):
        text = with_keys(text, tomllib.loads(update.TEMPLATE.read_text(encoding="utf-8")), update.missing_keys(repo))
        parse(git.root, text)  # validate before any mutation
    if not resuming:
        git.checkout_synced(cfg.development)
        git.out("checkout", "-b", BRANCH)
    adr = _record(repo, automatic, pending)
    _apply(repo, automatic, text)
    _finish(repo, adr)
    _report(adr.relative_to(git.root), automatic, pending)
