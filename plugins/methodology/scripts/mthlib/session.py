"""SessionStart hook: inject the core rules and the repository state into context.

A repository without ``.claude/methodology.toml`` gets only the adoption
notice (SPEC-0004). The rules follow ``autonomy.level`` (SPEC-0007) and
``language.docs`` (SPEC-0008).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import agents, branches, plans, work
from .config import CONFIG_PATH, Config, load
from .errors import MthError
from .git import Git
from .setup import install_hook, register_launcher, sync_secrets_hook

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
MTH = PLUGIN_ROOT / "scripts" / "mth"  # launcher: picks a Python >= 3.11

AUTONOMY = {
    "full": ("Trabajas de forma **autónoma** sobre las specs del repositorio: no pides permiso para crear ramas, "
             "hacer commits, integrar ni publicar versiones. Las skills `mth-*` se usan sin preguntar."),
    "until-pr": ("Trabajas de forma **autónoma hasta el PR** (`autonomy.level = \"until-pr\"`): creas ramas y haces "
                 "commits sin pedir permiso, pero integrar (`mth integrate`) y publicar (`mth release`, "
                 "`mth hotfix finish`) piden confirmación a la persona. Si la rechaza, no lo reintentes por otra vía. "
                 "Las skills `mth-*` se usan sin preguntar."),
    "supervised": ("Trabajas **supervisado** (`autonomy.level = \"supervised\"`): cada rama nueva, commit, push, "
                   "integración y publicación pide confirmación a la persona. Si la rechaza, no lo reintentes por "
                   "otra vía. Las skills `mth-*` se usan sin preguntar."),
}


def rules(cfg: Config | None, cmd: str) -> str:
    """Core rules for an adopted repo; ``cfg`` is None when its configuration is invalid (fail-safe)."""
    core = (PLUGIN_ROOT / "context" / "core.md").read_text(encoding="utf-8")
    autonomy = cfg["autonomy"]["level"] if cfg else "supervised"
    language = cfg.vocab.name if cfg else "español"
    extra = cfg["work"]["dirs"] if cfg else []
    work_extra = f"; y los propios del repo: {', '.join(f'`{d}/`' for d in extra)}" if extra else ""
    return (core.replace("{{AUTONOMY}}", AUTONOMY[autonomy]).replace("{{DOCS_LANGUAGE}}", language)
            .replace("{{WORK_EXTRA}}", work_extra)
            .replace("{{MTH}}", cmd).replace("{{PRINCIPLES}}", str(PLUGIN_ROOT / "PRINCIPLES.md")))


def _plan_lines(git: Git, cfg: Config, info: branches.BranchInfo) -> list[str]:
    """Open agreed plans and a warning when the branch needs one it lacks (SPEC-0023/AC-13)."""
    found, broken = plans.listing(git.root / work.WORK_DIR / "plans")
    lines = []
    if open_ := [p for p in found if p.state in plans.ACTIVE]:
        lines.append("Planes abiertos (.work/plans/): " + "; ".join(f"{p.ident} {p.state}: {p.title}" for p in open_) + ".")
    if broken:
        lines.append(f"⚠ Planes ilegibles en .work/plans/: {', '.join(p.name for p in broken)}.")
    if info.kind in cfg["plans"]["required_for"] and plans.running_for(found, info.top) is None:
        lines.append(f"⚠ La rama {info.top} no tiene un plan «en curso» que la liste: sin él no se integra (skill mth-plan).")
    return lines


def _state(cwd: Path) -> list[str]:
    try:
        git = Git.discover(cwd)
    except MthError:
        return ["Estado: fuera de un repositorio git."]
    try:
        cfg = load(git.root)
    except MthError as exc:
        return [f"Estado: {exc.message} → {exc.hint or ''}".strip()]
    lines = []
    try:
        hook = install_hook(git, cfg["hooks"]["commit_msg"])
    except MthError as exc:
        hook = "error"
        lines.append(f"⚠ Hook commit-msg: {exc.message} → {exc.hint or ''}".strip())
    try:
        sync_secrets_hook(git, cfg)  # SPEC-0024: keep the opt-in pre-commit hook in step with secrets.hook
    except (MthError, OSError) as exc:
        detail = f"{exc.message} → {exc.hint or ''}" if isinstance(exc, MthError) else str(exc)
        lines.append(f"⚠ Hook pre-commit: {detail}".strip())
    try:
        register_launcher(git)  # SPEC-0012: the agent-guard shim reads it
    except (MthError, OSError) as exc:
        lines.append(f"⚠ Lanzador para el guard de los agentes: {exc} (los agentes del catálogo quedan bloqueados).")
    try:
        work.ensure(git, cfg["work"]["dirs"])  # SPEC-0010
    except MthError as exc:
        lines.append(f"⚠ Directorio {work.WORK_DIR}/: {exc.message} → {exc.hint or ''}".strip())
    try:
        from . import smoke  # lazy: smoke builds on setup (SPEC-0014)
        lines += [f"⚠ {notice}" for notice in smoke.warnings(git, bool(agents.catalog_names(git.root)))]
    except (MthError, OSError) as exc:  # a notice must never break the session start
        lines.append(f"⚠ No se pudo comprobar la prueba de humo: {exc}")
    if hook == "foreign":
        lines.append("⚠ Hay un hook commit-msg ajeno: la validación de mensajes no está activa (mth doctor).")
    try:
        branch = git.current_branch()
        info = branches.parse(branch, cfg)
        if info is None:
            lines.append(f"Rama actual: {branch} (rama protegida: crea una rama de trabajo antes de cambiar nada).")
        else:
            lines.append(f"Rama actual: {branch} → se integra en {branches.target_of(info, cfg)}.")
            lines += _plan_lines(git, cfg, info)
    except MthError as exc:
        lines.append(f"Rama actual: {exc.message}")
    changes = git.root / cfg["paths"]["changes"]
    pending = len(list(changes.glob("*.md"))) if changes.is_dir() else 0
    lines.append(f"Fragmentos de changelog pendientes de publicar: {pending}.")
    return lines


def context(cwd: Path, cmd: str) -> str:
    """Everything the hook prints for ``cwd``."""
    try:
        git = Git.discover(cwd)
    except MthError:
        return "[claude-methodology] Fuera de un repositorio git: la metodología no aplica."
    if not (git.root / CONFIG_PATH).is_file():
        notice = (PLUGIN_ROOT / "context" / "unadopted.md").read_text(encoding="utf-8")
        return notice.replace("{{MTH}}", cmd)
    try:
        cfg: Config | None = load(git.root)
    except MthError:
        cfg = None
    return rules(cfg, cmd) + "\n" + "\n".join(_state(cwd))


def main() -> int:
    """Print context for Claude. Never fails: a broken hook must not block the session."""
    try:
        cmd = f'sh "{MTH}"'
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"export MTH='{cmd}'\n")
        print(context(Path.cwd(), cmd))
    except Exception as exc:  # noqa: BLE001 — hook boundary.
        print(f"[claude-methodology] contexto no disponible: {exc}", file=sys.stderr)
    return 0
