"""Whether a release is worth publishing and at which level (SPEC-0017, ADR-0013).

Pure decision over the changelog fragments, the last version and the open work branches: no I/O,
so ``mth release --plan`` and ``mth release`` always agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import changelog, lang

PUBLISH, WAIT, SKIP, BLOCKED = "publicar", "esperar", "no publicar", "bloqueado"
STABLE = changelog.STABLE


@dataclass
class Plan:
    decision: str
    reasons: list[str]
    fragments: list[tuple[str, str]] = field(default_factory=list)  # (name, declared level)
    level: str | None = None
    version: str | None = None
    latest: tuple[int, int, int] = (0, 0, 0)

    def lines(self) -> list[str]:
        out = [f"Fragmentos ({len(self.fragments)}):"] + [f"  · {name}: {level}" for name, level in self.fragments]
        if self.level:
            out.append(f"Nivel: {self.level} → versión {self.version} (última: {'.'.join(map(str, self.latest))})")
        out.append(f"Decisión: {self.decision}")
        out += [f"  - {reason}" for reason in self.reasons]
        return out


def decide(fragments: list[changelog.Fragment], latest: tuple[int, int, int], open_work: list[str],
           allow_major: bool = False, vocab: lang.Vocabulary = lang.ES) -> Plan:
    """The decision for ``fragments`` on top of ``latest``; ``open_work`` are open branches that bring a fragment."""
    if not fragments:
        return Plan(SKIP, ["no hay fragmentos: el mantenimiento sin fragmento (docs, CI, tests, refactor) no versiona"],
                    latest=latest)
    listed = [(f.path.name, f.bump) for f in fragments]
    errors = [e for f in fragments for e in changelog.bump_errors(f, latest, vocab)]
    if errors:
        return Plan(BLOCKED, errors + ["corrige el `bump` del fragmento (o el contenido) y vuelve a decidir"],
                    listed, latest=latest)
    level = changelog.highest_bump(fragments)
    version = changelog.next_version(latest, level)
    plan = Plan(PUBLISH, [], listed, level, version, latest)
    if level == "major" and latest < STABLE and not allow_major:
        plan.decision = BLOCKED
        plan.reasons = [f"el nivel major publicaría {version}: 1.0.0 declara la API estable y lo decide la persona "
                        "(`mth release --allow-major`); antes de 1.0.0 un cambio incompatible es minor"]
    elif open_work:
        plan.decision = WAIT
        plan.reasons = [f"hay trabajo abierto que aporta fragmento: {', '.join(open_work)}; su contenido puede deber "
                        "entrar en esta versión (si es independiente, `mth release` sigue disponible)"]
    else:
        plan.reasons = [f"{len(fragments)} fragmento(s) con cambios visibles, niveles coherentes y sin trabajo abierto"]
    return plan
