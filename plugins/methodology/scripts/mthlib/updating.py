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

from . import adoption, agents, commits, config, lang, setup, update
from .config import CONFIG_PATH, load, parse
from .errors import MthError
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
        f"# {ident} · {t['title']}", "",
        f"- {t['status']}: {t['accepted']}", f"- {t['date']}: {(today or date.today()).isoformat()}",
        f"- {t['category']}: methodology", f"- {vocab.format_label}: {vocab.compact}", "",
        f"## {context}", "", t["context"].format(version=update.__version__),
        *([t["previous"].format(previous=previous)] if previous else []), "",
        f"## {decision}", "", f"1. {t['applied']}", *items,
        f"2. {t['pending'] if pending else t['none']}", *rest, "",
        f"## {rejected}", "", t["rejected"], "",
        f"## {consequences}", "", t["plus"], t["minus"], "",
        f"## {imposes}", "", t["imposes"], "",
    ])


def apply(start: Path) -> None:
    """Apply the automatic gaps of the repository at ``start`` on ``chore/update-methodology``.

    Raises:
        MthError: Not adopted, dirty tree or the branch already exists (outside it), invalid
            configuration, or no automatic gap to apply.
    """
    repo = update.open_repo(start)
    git, cfg = repo.git, repo.cfg
    root = git.root
    resuming = git.current_branch() == BRANCH
    if not resuming:
        git.require_clean()
        git.fetch()
        if git.remote_has(BRANCH) or git.local_has(BRANCH):
            raise MthError(f"La rama {BRANCH} ya existe.", hint="Intégrala o bórrala antes de actualizar.")
    gaps = {g.id: g for g in update.diagnose(repo) if g.clase == update.AUTOMATIC}
    if not gaps:
        raise MthError("Nada que aplicar: no hay brechas automáticas.", hint="mth update --plan muestra lo pendiente.")
    text = (root / CONFIG_PATH).read_text(encoding="utf-8")
    if "config" in gaps:
        text = with_keys(text, tomllib.loads(update.TEMPLATE.read_text(encoding="utf-8")), update.missing_keys(repo))
        parse(root, text)  # validate before any mutation
    outdated = update.outdated_agents(repo) if "agentes-desactualizados" in gaps else []

    if not resuming:
        git.checkout_synced(cfg.development)
        git.out("checkout", "-b", BRANCH)
    (root / CONFIG_PATH).write_text(text, encoding="utf-8")
    new_cfg = load(root)
    if outdated:
        agents.Manager(new_cfg).sync(outdated, False)
    if "bloque" in gaps:
        setup.upsert_claude_md(root, new_cfg["paths"], new_cfg.vocab)
    if "hook" in gaps:
        setup.install_hook(git, new_cfg["hooks"]["commit_msg"])

    pending = [g for g in update.diagnose(update.Repo(git, new_cfg)) if g.clase != update.AUTOMATIC]
    folder = root / new_cfg["paths"]["adr"] / update.METHODOLOGY_ADRS
    previous = sorted(p.name[:m.start()] for p in folder.glob("*.md") if (m := setup.METHODOLOGY_ADR.search(p.name)))
    ident = IdRegistry(new_cfg, git.files()).next_id(new_cfg["trace"]["adr_kind"])
    folder.mkdir(parents=True, exist_ok=True)
    adr = folder / f"{ident}-{SLUG[new_cfg.vocab.code]}.md"
    adr.write_text(adr_text(ident, previous[-1] if previous else None, list(gaps.values()), pending, new_cfg.vocab),
                   encoding="utf-8")
    git.out("add", "-A")
    git.commit_message(commits.build("chore", "methodology", "update claude-methodology",
                                     "Bring the repository up to date with the installed plugin: apply the "
                                     "automatic gaps and record them.", [ident]))
    git.push(BRANCH)
    say(f"· ADR de actualización: {adr.relative_to(root)}")
    for gap in gaps.values():
        say(f"· aplicado {gap.id}: {gap.evidence}")
    for gap in pending:
        warn(f"Pendiente ({gap.clase}) {gap.id}: {gap.evidence}")
    say(f"✓ Actualización en {BRANCH}. Haz lo pendiente con la skill mth-update y después mth integrate.")
