"""Update of an adopted repository to a newer plugin (SPEC-0021, ADR-0017).

The diagnosis is a registry of gaps: each one has an id, a class, a detector and an action.
Detectors only read. A spec that adds a requirement for adopted repositories registers its gap here.
"""
from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__, agents, catalog, compact, setup, smoke
from .config import CONFIG_PATH, Config, load
from .errors import MthError
from .git import Git
from .trace import Tracer

AUTOMATIC = "automatica"
DECISION = "decision"
INFORMATIVE = "informativa"
CLASSES = (AUTOMATIC, DECISION, INFORMATIVE)

TEMPLATE = setup.TEMPLATES / "methodology.toml"
# Tables the person owns: a missing key there is a choice, not a gap.
OWNED = {("ids",), ("review", "paths"), ("release", "version_files"), ("branches", "extra")}
PATH_KEYS = ("docs", "specs", "adr", "changes", "changelog", "claude_md")


@dataclass(frozen=True)
class Gap:
    id: str
    clase: str
    evidence: str
    action: str


@dataclass(frozen=True)
class Repo:
    git: Git
    cfg: Config


@dataclass(frozen=True)
class GapKind:
    id: str
    clase: str
    action: str
    detect: Callable[[Repo], str | None]  # evidence, or None when the repo has no such gap


def missing_config(template: dict[str, Any], raw: dict[str, Any], path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Keys the template documents that the repository file lacks (a missing table counts once)."""
    out: list[tuple[str, ...]] = []
    for key, value in template.items():
        here = (*path, key)
        if here in OWNED:
            continue
        if key not in raw:
            out.append(here)
        elif isinstance(value, dict) and isinstance(raw[key], dict):
            out += missing_config(value, raw[key], here)
    return out


def missing_keys(repo: Repo) -> list[tuple[str, ...]]:
    """Template keys the repository configuration lacks."""
    raw = tomllib.loads((repo.cfg.root / CONFIG_PATH).read_text(encoding="utf-8"))
    return missing_config(tomllib.loads(TEMPLATE.read_text(encoding="utf-8")), raw)


def _config(repo: Repo) -> str | None:
    return ", ".join(".".join(p) for p in missing_keys(repo)) or None


def _agents_with(repo: Repo, status: Callable[[str], bool], names: list[str] | None = None) -> list[str]:
    manager = agents.Manager(repo.cfg)
    return [n for n in (names if names is not None else agents.catalog_names(repo.cfg.root))
            if status(manager.status(n))]


def outdated_agents(repo: Repo) -> list[str]:
    """Installed catalog agents that ``mth agents sync`` brings up to date."""
    return _agents_with(repo, lambda s: s.startswith("desactualizado"))


def _outdated(repo: Repo) -> str | None:
    return ", ".join(outdated_agents(repo)) or None


def edited_agents(repo: Repo) -> list[str]:
    """Installed catalog agents whose generated part was edited by hand: the person decides about them."""
    return _agents_with(repo, lambda s: s == "editado a mano")


def _edited(repo: Repo) -> str | None:
    return ", ".join(edited_agents(repo)) or None


def _profile(repo: Repo) -> str | None:
    base = catalog.profiles(catalog.CATALOG_DIR)["base"]["agents"]
    return ", ".join(_agents_with(repo, lambda s: s == "no instalado", base)) or None


def _block(repo: Repo) -> str | None:
    state = setup.claude_block_state(repo.cfg.root, repo.cfg["paths"], repo.cfg.vocab)
    return None if state == "current" else f"bloque {state} en {repo.cfg['paths']['claude_md']}"


def _hook(repo: Repo) -> str | None:
    state = setup.hook_state(repo.git, repo.cfg["hooks"]["commit_msg"])
    return f"hook commit-msg {state}" if state in ("stale", "absent") else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MthError(f"No se puede leer {path.name} para el diagnóstico: {exc}.",
                       hint="Corrige el fichero o su codificación (UTF-8) y repite.") from exc


def _format(repo: Repo) -> str | None:
    cfg, vocab = repo.cfg, repo.cfg.vocab
    generated = f"{cfg['paths']['adr']}/{setup.ADR_SUBDIR}/"
    roots = (f"{cfg['paths']['specs']}/", f"{cfg['paths']['adr']}/")
    docs = [f for f in repo.git.files() if f.endswith(".md") and f.startswith(roots) and not f.startswith(generated)]
    old = [f for f in docs if not compact.is_compact(_read(cfg.root / f), vocab)]
    return f"{len(old)} de {len(docs)} documentos sin «{vocab.format_label}: {vocab.compact}»" if old else None


def _secrets(repo: Repo) -> str | None:
    return "secrets.mode sin decidir: no se buscan secretos al integrar" if repo.cfg["secrets"]["mode"] == "" else None


def _smoke(repo: Repo) -> str | None:
    notices = smoke.warnings(repo.git, bool(agents.catalog_names(repo.cfg.root)))
    return notices[0] if notices else None


def _single(repo: Repo) -> str | None:
    found = Tracer(repo.cfg, repo.git.files()).single_test()
    return f"{len(found)} criterios con un único test" if found else None


REGISTRY: tuple[GapKind, ...] = (
    GapKind("config", AUTOMATIC, "Añadir cada clave ausente con su valor por defecto", _config),
    GapKind("agentes-desactualizados", AUTOMATIC, "mth agents sync", _outdated),
    GapKind("agentes-editados", DECISION, "Elegir entre mth agents sync --force y conservar la edición", _edited),
    GapKind("agentes-perfil", DECISION, "mth agents add de los que acepte la persona", _profile),
    GapKind("bloque", AUTOMATIC, "Regenerar el bloque de la metodología", _block),
    GapKind("hook", AUTOMATIC, "Reinstalar el hook según hooks.commit_msg", _hook),
    GapKind("formato", DECISION, "Migración: convertir los documentos o dejarlos como están", _format),
    GapKind("secretos", DECISION, "Activar el gate de secretos (secrets.mode = \"block\") o desactivarlo (\"off\")", _secrets),
    GapKind("humo", INFORMATIVE, "Ejecutar mth smoke", _smoke),
    GapKind("triangulacion", INFORMATIVE, "Trabajo de tests por spec (mth trace --single)", _single),
)


def diagnose(repo: Repo) -> list[Gap]:
    """Gaps between the repository and what the installed plugin requires, in registry order."""
    return [Gap(kind.id, kind.clase, evidence, kind.action)
            for kind in REGISTRY if (evidence := kind.detect(repo))]


def render(gaps: list[Gap]) -> str:
    """Human summary of a diagnosis, grouped by class."""
    lines = [f"claude-methodology {__version__}"]
    if not gaps:
        return "\n".join([*lines, "✓ al día: el repositorio cumple lo que exige el plugin."])
    for clase in CLASSES:
        group = [g for g in gaps if g.clase == clase]
        if group:
            lines.append(f"[{clase}]")
            lines += [f"  {g.id}: {g.evidence}\n      → {g.action}" for g in group]
    return "\n".join(lines)


def to_json(gaps: list[Gap]) -> str:
    """The diagnosis as JSON: the plugin version and each gap with its id, class, evidence and action."""
    return json.dumps({"plugin": __version__, "gaps": [asdict(g) for g in gaps]}, ensure_ascii=False, indent=2)


def _confine(cfg: Config) -> None:
    """Every configured path must stay inside the repository: ``mth update`` writes through them."""
    root = cfg.root.resolve()
    for key in PATH_KEYS:
        rel = cfg["paths"][key]
        inside = (root / rel).resolve()
        if Path(rel).is_absolute() or inside == root or not inside.is_relative_to(root):
            raise MthError(f"paths.{key} = '{rel}' sale del repositorio o es la raíz.",
                           hint="Usa una ruta relativa que quede dentro del repo.")
    generated = (root / cfg["paths"]["adr"] / setup.ADR_SUBDIR).resolve()
    if not generated.is_relative_to(root):
        raise MthError(f"{cfg['paths']['adr']}/{setup.ADR_SUBDIR} apunta fuera del repositorio.",
                       hint="Sustituye el enlace por una carpeta dentro del repo.")


def open_repo(start: Path) -> Repo:
    """The adopted repository at ``start``.

    Raises:
        MthError: The repository has not adopted the methodology, or a configured path leaves it.
    """
    git = Git.discover(start)
    if not (git.root / CONFIG_PATH).is_file():
        raise MthError("El repositorio no ha adoptado la metodología.", hint="Usa la skill mth-init.")
    cfg = load(git.root)
    _confine(cfg)
    git.remote = cfg.remote
    return Repo(git, cfg)


def plan(start: Path, as_json: bool) -> None:
    """Print the diagnosis of the repository at ``start`` without writing anything (SPEC-0021/AC-02)."""
    gaps = diagnose(open_repo(start))
    print(to_json(gaps) if as_json else render(gaps))
