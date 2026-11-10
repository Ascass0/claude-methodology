"""Branch model: Git Flow with nested child branches.

    main ── hotfix/<slug>
    development ── feat|fix|chore/<slug> ── <top>--<kind>-<slug> ── ...
                └─ release/vX.Y.Z (internal, created by `mth release`)

Children use ``--`` instead of ``/`` because git cannot hold ``feat/x`` and
``feat/x/y`` at the same time (a ref cannot be both a file and a directory).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config
from .errors import MthError

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
CHILD_KINDS = ("feat", "fix", "refactor", "test", "docs", "chore")
TOP_FLOWS = {"feat": "feature", "fix": "feature", "chore": "feature", "hotfix": "hotfix"}
_SLUG_RE = re.compile(rf"^{SLUG}$")
_RELEASE_RE = re.compile(r"^release/v\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class BranchInfo:
    """Position of a work branch in the flow."""

    name: str
    kind: str          # top-level kind: feat, fix, chore, hotfix or an extra prefix
    slug: str          # top-level slug
    flow: str          # "feature" (from development) or "hotfix" (from main)
    parent: str | None  # parent branch for children, None for top-level

    @property
    def top(self) -> str:
        return f"{self.kind}/{self.slug}"

    @property
    def is_child(self) -> bool:
        return self.parent is not None


def flows(cfg: Config) -> dict[str, str]:
    out = dict(TOP_FLOWS)
    out.update({k: v["flow"] for k, v in cfg["branches"]["extra"].items()})
    return out


def base_of(flow: str, cfg: Config) -> str:
    return cfg.main if flow == "hotfix" else cfg.development


def target_of(info: BranchInfo, cfg: Config) -> str:
    """Branch into which ``info`` integrates."""
    return info.parent or base_of(info.flow, cfg)


def is_release(name: str) -> bool:
    return bool(_RELEASE_RE.match(name))


def parse(name: str, cfg: Config) -> BranchInfo | None:
    """Classify a branch; None for main, development and release branches.

    Raises:
        MthError: The name does not follow the branch model.
    """
    if name in (cfg.main, cfg.development) or is_release(name):
        return None
    known = flows(cfg)
    kinds = "|".join(map(re.escape, known))
    m = re.match(rf"^(?P<kind>{kinds})/(?P<slug>{SLUG})(?P<children>(?:--(?:{'|'.join(CHILD_KINDS)})-{SLUG})*)$", name)
    if not m:
        raise MthError(f"La rama '{name}' no sigue el modelo de ramas.",
                       hint=f"Top: <{'|'.join(known)}>/<slug>; hija: <rama>--<{'|'.join(CHILD_KINDS)}>-<slug>.")
    parent = name.rsplit("--", 1)[0] if m.group("children") else None
    return BranchInfo(name=name, kind=m.group("kind"), slug=m.group("slug"),
                      flow=known[m.group("kind")], parent=parent)


def validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise MthError(f"Slug inválido: '{slug}'.", hint="Usa minúsculas, dígitos y guiones simples: mi-cambio.")


def fragment_name(info: BranchInfo) -> str:
    """Changelog fragment file of the top-level branch (``feat-runner.md``)."""
    return f"{info.kind}-{info.slug}.md"
