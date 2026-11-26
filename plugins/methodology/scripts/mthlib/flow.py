"""Git Flow operations: start, commit, sync, integrate, release and hotfix.

Every operation validates first and mutates last, and every remote step is
idempotent, so a failed run can simply be repeated (design for failure).
"""
from __future__ import annotations

import shlex
import tempfile
import unicodedata
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import branches, changelog, commits, forge, globs, limits, plans, releaseplan, review, secretgate, versions, work
from .config import Config
from .errors import MthError
from .files import atomic_write
from .gh import GitHub
from .git import Git
from .ids import IdRegistry
from .log import Tracer, say, warn
from .proc import run_shell
from .trace import Finding, partition
from .trace import Tracer as TraceChecker
from .trace import check as trace_check
from .work import WORK_DIR

_MAX_LISTED = 50


@dataclass
class Ctx:
    """Everything an operation needs; built once per CLI invocation."""

    cfg: Config
    git: Git
    tracer: Tracer

    @property
    def root(self) -> Path:
        return self.cfg.root

    def registry(self) -> IdRegistry:
        return IdRegistry(self.cfg, self.git.files())

    def path(self, key: str) -> Path:
        return self.root / self.cfg["paths"][key]

    def gh(self) -> GitHub:
        hub = GitHub(self.root, self.git.github_repo())
        hub.ensure_ready()
        return hub

    def own_commits(self, rev_range: str) -> list[tuple[str, str]]:
        """Commits of ``rev_range`` that belong to this repo (external history excluded).

        Raises:
            MthError: A configured external ref is missing (its history would be
                validated as ours, so we refuse instead of guessing).
        """
        external = self.cfg["commits"]["external_refs"]
        missing = [r for r in external if not self.git.ok("rev-parse", "--verify", "--quiet", r)]
        if missing:
            raise MthError(f"No existe la referencia externa {', '.join(missing)}.",
                           hint="Trae el remoto externo (por ejemplo, `git fetch upstream`) o corrige commits.external_refs.")
        return self.git.commits(rev_range, exclude=external)


# -- shared gates -------------------------------------------------------------
def line_limits(ctx: Ctx) -> tuple[list[Finding], list[Finding]]:
    """Errors and warnings of the line limit per file (ADR-0016, SPEC-0020).

    Raises:
        MthError: A file is over the limit, the branch has a parent and the parent cannot be read.
    """
    cfg = ctx.cfg["limits"]
    root = ctx.git.root
    counts: dict[str, int] = {}
    for rel in ctx.git.files():
        if globs.match_any(rel, cfg["exclude"]):
            continue
        try:
            with (root / rel).open("rb") as handle:
                lines = limits.count_lines(iter(lambda: handle.read(limits.CHUNK), b""))
        except OSError as exc:
            raise MthError(f"No se puede leer {rel} para medir sus líneas: {exc.strerror or exc}.",
                           hint="Comprueba los permisos del fichero o exclúyelo en limits.exclude.") from exc
        if lines is not None:
            counts[rel] = lines
    binary = ctx.git.binary_by_attributes([p for p, n in counts.items() if n > cfg["max_file_lines"]])
    counts = {p: n for p, n in counts.items() if p not in binary}
    base = _line_base(ctx)
    errors, warnings = limits.evaluate(counts, cfg["max_file_lines"], limits.validate(cfg), base,
                                       ".claude/methodology.toml")
    return [Finding(p.path, 1, p.message) for p in errors], [Finding(p.path, 1, p.message) for p in warnings]


def _line_base(ctx: Ctx):
    """Function giving a file's lines at the branch base, or None when the branch has no parent."""
    try:
        info = branches.parse(ctx.git.current_branch(), ctx.cfg)
    except MthError as exc:
        warn(f"Sin rama padre para comparar el tamaño de los ficheros: {exc.message}")
        return None
    if info is None:
        return None
    target = branches.target_of(info, ctx.cfg)
    ref = ctx.git.remote_ref(target) if ctx.git.remote_has(target) else target
    state: dict[str, Any] = {}

    def lines_at_base(path: str) -> int:
        if "base" not in state:  # computed on first use: repos without long files never need it
            state["base"] = ctx.git.merge_base(ref)
            state["renamed"] = ctx.git.renamed_from(state["base"])
        origin = state["renamed"].get(path, path)
        return limits.count_lines(ctx.git.blob_chunks(state["base"], origin)) or 0
    return lines_at_base


def run_trace(ctx: Ctx) -> tuple[list[Finding], list[Finding]]:
    """Traceability errors and legacy findings (SPEC-0005: unchanged since trace.legacy_base)."""
    findings = trace_check(ctx.cfg, ctx.git.files()) + line_limits(ctx)[0]
    base = ctx.cfg["trace"]["legacy_base"]
    return partition(findings, ctx.git.unchanged_since(base)) if base else (findings, [])


def limit_notes(ctx: Ctx) -> list[Finding]:
    """Files over the line limit that the branch does not make grow: a warning for `mth trace`."""
    return line_limits(ctx)[1]


def single_test_notes(ctx: Ctx) -> list[Finding]:
    """Acceptance criteria with a single test (ADR-0015): a warning for `mth trace`, never a gate."""
    return TraceChecker(ctx.cfg, ctx.git.files()).single_test()


def legacy_summary(ctx: Ctx, legacy: list[Finding]) -> str:
    base = ctx.cfg["trace"]["legacy_base"][:7]
    return f"⚠ {len(legacy)} hallazgos en contenido legado (anterior a {base}): mth trace --legacy los lista"


def _gate_trace(ctx: Ctx) -> None:
    findings, legacy = run_trace(ctx)
    if legacy:
        warn(legacy_summary(ctx, legacy))
    if findings:
        listing = "\n".join(f"  - {f}" for f in findings[:50])
        more = f"\n  … y {len(findings) - 50} más" if len(findings) > 50 else ""
        raise MthError(f"Trazabilidad rota ({len(findings)} hallazgos):\n{listing}{more}",
                       hint="Corrige las referencias (skill mth-trace) y vuelve a intentarlo.")
    say("· Trazabilidad OK")


def _gate_secrets(ctx: Ctx, rev_range: str) -> None:
    # ADR-0020 §1-2: block scans and fails closed; "" warns and continues; "off" does nothing.
    mode = ctx.cfg["secrets"]["mode"]
    if mode == "":
        warn("secrets.mode sin decidir: no se buscan secretos (mth update --plan lo detalla).")
    elif mode == "block":
        secretgate.enforce(ctx.root, ctx.cfg["secrets"], rev_range)
        say("· Secretos: sin hallazgos nuevos")


def scan_secrets(ctx: Ctx, history: bool, accept: bool, staged: bool = False) -> None:
    """``mth secrets``: scan the branch over its target, the whole history or what is staged."""
    section = ctx.cfg["secrets"]
    if accept and not history:
        raise MthError("--accept solo se usa con --history.")
    if staged:
        if history:
            raise MthError("--staged no se combina con --history.")
        secretgate.enforce_staged(ctx.root, section)
        say("✓ Sin secretos en lo preparado")
        return
    if history:
        if accept:
            count = secretgate.accept_history(ctx.root, section)
            say(f"✓ {count} hallazgos aceptados en {section['baseline']}")
            warn(secretgate.ACCEPT_WARNING)
            return
        secretgate.enforce(ctx.root, section, None)
    else:
        info = branches.parse(ctx.git.current_branch(), ctx.cfg)
        if info is None:
            raise MthError("La rama actual no tiene destino con el que comparar.", hint="Usa `mth secrets --history`.")
        secretgate.enforce(ctx.root, section, f"{ctx.git.remote_ref(branches.target_of(info, ctx.cfg))}..HEAD")
    say("✓ Sin secretos nuevos")


def plans_dir(ctx: Ctx) -> Path:
    return ctx.root / work.WORK_DIR / "plans"


def _gate_plan(ctx: Ctx, info: branches.BranchInfo) -> None:
    """ADR-0021: a branch of a required kind needs a running plan that lists its top-level branch."""
    if info.kind in ctx.cfg["plans"]["required_for"]:
        try:
            plan = plans.for_branch(plans_dir(ctx), info.top)
        except MthError:
            ctx.tracer.event("plan.denied", branch=info.top)
            raise
        say(f"· Plan: {plan.ident}")


def _gate_tests(ctx: Ctx) -> str:
    command = ctx.cfg.test_command
    if not command:
        warn("commands.test está vacío: no se ejecutan tests.")
        return "sin tests configurados"
    say(f"· Tests: {command}")
    if run_shell(command, ctx.root) != 0:
        raise MthError("Los tests fallan.", hint="Corrige antes de integrar.")
    say("· Tests en verde")
    return f"`{command}` en verde"


def _gate_commits(ctx: Ctx, rev_range: str) -> list[tuple[str, str]]:
    found = ctx.own_commits(rev_range)
    if not found:
        if ctx.git.count(rev_range) == 0:
            raise MthError("No hay commits nuevos que integrar.")
        say("· Solo hay merges de historia externa: no hay commits propios que validar")
        return []
    registry = ctx.registry()
    errors = [f"  - {sha[:8]}: {e}" for sha, msg in found
              for e in commits.validate(msg, ctx.cfg, registry)]
    if errors:
        raise MthError("Hay commits con un mensaje inválido:\n" + "\n".join(errors),
                       hint="Nunca se reescribe historia: añade un commit nuevo si falta información "
                            "o, si la rama no se ha compartido, rehaz el trabajo en una rama nueva.")
    return found


def _fragment(ctx: Ctx, info: branches.BranchInfo) -> changelog.Fragment | None:
    if info.is_child or info.kind not in ctx.cfg["changes"]["required_for"]:
        return None
    frag = changelog.parse(ctx.path("changes") / branches.fragment_name(info))
    refs_required = info.kind in ctx.cfg["commits"]["require_refs"] or info.kind == "hotfix"
    registry = ctx.registry()
    errors = changelog.validate(frag, registry, refs_required, ctx.cfg.vocab)
    errors += changelog.bump_errors(frag, ctx.git.latest_version(ctx.cfg.tag_prefix), ctx.cfg.vocab)  # SPEC-0017
    spec_kind = ctx.cfg["trace"]["spec_kind"]
    if info.kind == "feat" and not any(registry.kind_of(r) == spec_kind for r in frag.refs):
        errors.append(f"{frag.path.name}: una feature debe referenciar su spec ({spec_kind}) en refs")
    if errors:
        raise MthError("Fragmento de changelog inválido:\n" + "\n".join(f"  - {e}" for e in errors))
    return frag


def required_reviewers(ctx: Ctx, info: branches.BranchInfo) -> list[str]:
    """Reviewers that apply to the branch, given the files it changes."""
    if info.is_child or info.kind not in ctx.cfg["review"]["required_for"]:
        return []
    changed = ctx.git.changed_files(ctx.git.remote_ref(branches.target_of(info, ctx.cfg)))
    return review.required(ctx.cfg["review"]["agents"], ctx.cfg["review"]["paths"], changed)


def _review(ctx: Ctx, info: branches.BranchInfo, branch: str) -> dict[str, dict]:
    if info.is_child or info.kind not in ctx.cfg["review"]["required_for"]:
        return {}
    if not ctx.cfg["review"]["agents"]:
        review.check(ctx.git.git_dir(), branch, "", [])  # raises: review is mandatory
    agents = required_reviewers(ctx, info)
    if not agents:
        say("· Ningún revisor aplica a los ficheros cambiados")
        return {}
    return review.check(ctx.git.git_dir(), branch, ctx.git.sha("HEAD"), agents)


def _require_synced(ctx: Ctx, target: str) -> None:
    if not ctx.git.is_ancestor(ctx.git.remote_ref(target), "HEAD"):
        raise MthError(f"La rama no contiene el último {target}.",
                       hint="Ejecuta `mth sync` y repite las revisiones sobre el nuevo HEAD.")


def _require_no_children(ctx: Ctx, branch: str) -> None:
    open_children = [b for b in ctx.git.remote_branches() if b.startswith(branch + "--")]
    if open_children:
        raise MthError(f"Hay ramas hijas sin integrar: {', '.join(open_children)}.",
                       hint="Intégralas primero en su rama padre (mth integrate desde cada una).")


def _merge_message(title: str, number: int, head: str, base: str,
                   found: list[tuple[str, str]], extra_refs: list[str]) -> tuple[str, str]:
    """Merge commit subject and body: English, descriptive, with references."""
    refs = list(dict.fromkeys([r for _, m in found for r in commits.refs_of(m)] + extra_refs))
    lines = [f"Merge {head} into {base}.", "", "Commits:"]
    lines += [f"- {m.splitlines()[0]}" for _, m in found[:_MAX_LISTED]]
    if len(found) > _MAX_LISTED:
        lines.append(f"- ... and {len(found) - _MAX_LISTED} more")
    if not found:
        lines.append("- none of its own (merges external history only)")
    lines += ["", f"Refs: {', '.join(refs) if refs else commits.NO_REFS}"]
    return f"{title} (#{number})", "\n".join(lines)


def _cell(text: str) -> str:
    """A table cell from free text: one line, pipes escaped (no backslash inside an f-string: Python 3.11)."""
    return " ".join(text.split()).replace("|", "\\|")


def _pr_body(summary: str, refs: list[str], frag: changelog.Fragment | None,
             tests: str, reviews: dict[str, dict]) -> str:
    parts = ["## Resumen", summary.strip(), "", "## Referencias",
             ", ".join(refs) if refs else "—", ""]
    if frag:
        parts += ["## Changelog", frag.path.read_text(encoding="utf-8").split("---", 2)[-1].strip(), ""]
    parts += ["## Verificación", f"- Tests: {tests}", "- Trazabilidad: OK"]
    if reviews:
        parts += ["", "## Revisión", "| Revisor | Bloqueantes | Resumen |", "|---|---|---|"]
        parts += [f"| {a} | {r['blocking']} | {_cell(r['summary'])} |"
                  for a, r in reviews.items()]
    parts += ["", "---", "_Generado por claude-methodology._"]
    return "\n".join(parts) + "\n"


# -- start --------------------------------------------------------------------
def start(ctx: Ctx, kind: str, slug: str, child: bool, spec: str | None, plan: str | None = None) -> str:
    """Create a top-level branch from its base, or a child of the current branch."""
    g, cfg = ctx.git, ctx.cfg
    branches.validate_slug(slug)
    g.require_clean()
    g.fetch()
    if child:
        if kind not in branches.CHILD_KINDS:
            raise MthError(f"Tipo de rama hija inválido: {kind} ({', '.join(branches.CHILD_KINDS)}).")
        parent = g.current_branch()
        if branches.parse(parent, cfg) is None:
            raise MthError(f"No se crean ramas hijas de '{parent}'.", hint="Las hijas cuelgan de una rama de trabajo.")
        name = f"{parent}--{kind}-{slug}"
        branches.parse(name, cfg)
        g.out("checkout", "-b", name)
        g.push(name)
        ctx.tracer.event("branch.start", branch=name, parent=parent)
        say(f"✓ Rama hija {name} creada desde {parent}")
        return name

    flows = branches.flows(cfg)
    if kind not in flows:
        raise MthError(f"Tipo de rama inválido: {kind} ({', '.join(flows)}).")
    name = f"{kind}/{slug}"
    info = branches.parse(name, cfg)
    base = branches.base_of(info.flow, cfg)
    refs: list[str] = []
    if spec:
        registry = ctx.registry()
        if not registry.is_defined(spec):
            raise MthError(f"{spec} no existe.", hint="Crea la spec primero (skill mth-spec).")
        refs.append(spec)
    if g.remote_has(name) or g.local_has(name):
        raise MthError(f"La rama {name} ya existe.")
    plan_path = plans.for_start(plans_dir(ctx), plan, kind) if plan or kind in cfg["plans"]["required_for"] else None
    if plan_path is not None:  # the first change: if the plan cannot be written, no branch is created (SPEC-0023/FM-10)
        say(f"· Plan {plans.add_branch(plan_path, name).ident}: rama {name} registrada")
    g.checkout_synced(base)
    g.out("checkout", "-b", name)
    if kind in cfg["changes"]["required_for"]:
        frag_path = ctx.path("changes") / branches.fragment_name(info)
        frag_path.parent.mkdir(parents=True, exist_ok=True)
        frag_path.write_text(changelog.template(kind, refs, cfg.vocab), encoding="utf-8")
        say(f"· Fragmento creado: {frag_path.relative_to(ctx.root)} (complétalo antes de integrar)")
    g.push(name)
    ctx.tracer.event("branch.start", branch=name, base=base, spec=spec, plan=plan_path.name[:9] if plan_path else None)
    say(f"✓ Rama {name} creada desde {base}")
    return name


# -- commit -------------------------------------------------------------------
def commit(ctx: Ctx, ctype: str, scope: str | None, summary: str, body: str,
           refs: list[str], breaking: str | None) -> None:
    g, cfg = ctx.git, ctx.cfg
    branch = g.current_branch()
    if branch in (cfg.main, cfg.development):
        raise MthError(f"No se hace commit directamente en {branch}.", hint="Trabaja en una rama (skill mth-branch).")
    if not g.has_staged():
        raise MthError("No hay cambios en el área de preparación.",
                       hint="Añade con `git add <rutas>` solo los cambios de este tema.")
    message = commits.build(ctype, scope, summary, body, refs, breaking)
    errors = commits.validate(message, cfg, ctx.registry())
    if errors:
        raise MthError("Mensaje de commit inválido:\n" + "\n".join(f"  - {e}" for e in errors))
    pre = cfg["commands"]["precommit"]
    if pre:
        say(f"· Comprobación previa: {pre}")
        if run_shell(pre, ctx.root) != 0:
            raise MthError("La comprobación previa al commit falla.")
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fh:
        fh.write(message)
    try:
        g.out("commit", "-F", fh.name)
    finally:
        Path(fh.name).unlink(missing_ok=True)
    ctx.tracer.event("commit", branch=branch, sha=g.sha("HEAD"), header=message.splitlines()[0])
    say(f"✓ {message.splitlines()[0]}")


# -- sync ---------------------------------------------------------------------
def sync(ctx: Ctx) -> None:
    """Merge the integration target into the current branch (never rebase)."""
    g = ctx.git
    branch = g.current_branch()
    info = branches.parse(branch, ctx.cfg)
    if info is None:
        raise MthError(f"'{branch}' no es una rama de trabajo.")
    target = branches.target_of(info, ctx.cfg)
    g.require_clean()
    g.fetch()
    ref = g.remote_ref(target)
    if g.is_ancestor(ref, "HEAD"):
        say(f"✓ {branch} ya contiene {target}")
        return
    proc = g.try_run("merge", "--no-ff", "-m", f"Merge {target} into {branch}", ref)
    if proc.returncode != 0:
        conflicts = g.out("diff", "--name-only", "--diff-filter=U")
        raise MthError(f"Conflictos al traer {target}:\n{conflicts}",
                       hint="Resuélvelos, `git add` y `git commit --no-edit`. Después, `mth sync` de nuevo.")
    g.push(branch)
    ctx.tracer.event("sync", branch=branch, target=target, sha=g.sha("HEAD"))
    say(f"✓ {target} integrado en {branch}")


# -- integrate ----------------------------------------------------------------
def integrate(ctx: Ctx, title: str, summary: str) -> None:
    """Merge the current work branch into its target through a PR."""
    g, cfg = ctx.git, ctx.cfg
    branch = g.current_branch()
    info = branches.parse(branch, cfg)
    if info is None:
        raise MthError(f"'{branch}' no se integra con mth integrate.",
                       hint="Las versiones se publican con `mth release`.")
    if info.flow == "hotfix" and not info.is_child:
        raise MthError("Una rama hotfix se cierra con `mth hotfix finish`.")
    if errors := commits.validate_header(title):
        raise MthError("Título inválido:\n" + "\n".join(f"  - {e}" for e in errors))
    target = branches.target_of(info, cfg)
    g.require_clean()
    g.fetch()
    if not g.remote_has(target):
        raise MthError(f"La rama destino {target} no existe en {g.remote}.")
    if g.remote_has(branch) and g.is_ancestor(g.remote_ref(branch), g.remote_ref(target)) \
            and g.sha("HEAD") == g.sha(g.remote_ref(branch)) and g.sha("HEAD") != g.sha(g.remote_ref(target)):
        say(f"· {branch} ya está integrada en {target}: se completa la limpieza")
        _finish_integration(ctx, branch, target)
        return
    _require_synced(ctx, target)
    if not info.is_child:
        _require_no_children(ctx, branch)
    _gate_plan(ctx, info)
    found = _gate_commits(ctx, f"{g.remote_ref(target)}..HEAD")
    frag = _fragment(ctx, info)
    _gate_trace(ctx)
    _gate_secrets(ctx, f"{g.remote_ref(target)}..HEAD")
    reviews = _review(ctx, info, branch)
    tests = _gate_tests(ctx)

    g.push(branch)
    refs = list(dict.fromkeys((frag.refs if frag else []) + [r for _, m in found for r in commits.refs_of(m)]))
    if cfg.forge != forge.GITHUB:  # SPEC-0016: the forge part is manual; never merge without checking the CI
        _integrate_manual(ctx, branch, target, title, _pr_body(summary, refs, frag, tests, reviews),
                          _merge_message(title, 0, branch, target, found, frag.refs if frag else [])[1])
        return
    hub = ctx.gh()
    number = hub.ensure_pr(branch, target, title, _pr_body(summary, refs, frag, tests, reviews))
    hub.wait_checks(number, cfg["ci"]["required"])
    subject, body = _merge_message(title, number, branch, target, found, frag.refs if frag else [])
    hub.merge(number, subject, body)
    ctx.tracer.event("integrate", branch=branch, target=target, pr=number)
    _finish_integration(ctx, branch, target)
    say(f"✓ {branch} integrada en {target} (PR #{number}); rama borrada, historia conservada")


def _write_request(ctx: Ctx, name: str, text: str) -> Path:
    """Write ``text`` where the person finds it to paste into the forge (``.work/merge-request/``)."""
    path = ctx.root / WORK_DIR / "merge-request" / f"{name.replace('/', '-')}.md"
    atomic_write(path, text)
    return path.relative_to(ctx.root)


def _integrate_manual(ctx: Ctx, branch: str, target: str, title: str, body: str, merge_body: str) -> None:
    """Local part of an integration when the forge is not GitHub: prepare the merge request, never merge."""
    cfg = ctx.cfg
    path = _write_request(ctx, branch, f"# {title}\n\n{body}\n## Mensaje del merge commit\n\n```\n{title}\n\n{merge_body}\n```\n")
    ctx.tracer.event("integrate.manual", branch=branch, target=target, forge=cfg.forge)
    say(f"✓ Gates locales superados y {branch} subida; no se fusiona (forge = {cfg.forge}, mth no puede comprobar la CI).")
    say("Pasos manuales:")
    say(f"  1. Abre un MR {branch} → {target} con el título y la descripción de {path}.")
    say("  2. Espera a que la CI esté en verde.")
    say("  3. Fusiona con merge commit (sin squash ni rebase), usando el mensaje del final de ese fichero.")
    say(f"  4. Vuelve a ejecutar `mth integrate` con los mismos argumentos: detecta el merge y limpia {branch}.")


def _finish_integration(ctx: Ctx, branch: str, target: str) -> None:
    g = ctx.git
    g.fetch()
    g.checkout_synced(target)
    g.delete_branch(branch)


# -- release & hotfix -----------------------------------------------------------
def _version_files(ctx: Ctx) -> list[versions.VersionFile]:
    return versions.from_config(ctx.cfg["release"]["version_files"])


def _check_version_files(ctx: Ctx) -> None:
    for item in _version_files(ctx):
        versions.read(ctx.root, item)


def _apply_release(ctx: Ctx, version: str, fragments: list[changelog.Fragment]) -> None:
    """Fold fragments into the changelog and commit it on the current branch."""
    log_path = ctx.path("changelog")
    if not log_path.is_file():
        raise MthError(f"No existe {log_path.name}.", hint="mth init lo crea.")
    bumped = versions.write(ctx.root, _version_files(ctx), version)  # SPEC-0003: checked before any write
    section = changelog.render(version, fragments, vocab=ctx.cfg.vocab)
    log_path.write_text(changelog.insert(log_path.read_text(encoding="utf-8"), section), encoding="utf-8")
    for frag in fragments:
        ctx.git.out("rm", "-q", str(frag.path.relative_to(ctx.root)))
    ctx.git.out("add", str(log_path.relative_to(ctx.root)), *bumped)
    refs = list(dict.fromkeys(r for f in fragments for r in f.refs))
    body = f"Fold {len(fragments)} changelog fragment(s) into {log_path.name} for v{version}."
    if bumped:
        body += f"\n\nSet version {version} in {', '.join(bumped)}."
    message = commits.build("chore", "release", f"v{version}", body, refs)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fh:
        fh.write(message)
    try:
        ctx.git.out("commit", "-F", fh.name)
    finally:
        Path(fh.name).unlink(missing_ok=True)


def _publish(ctx: Ctx, head: str, version: str, found: list[tuple[str, str]]) -> None:
    """head → main (merge commit), tag, GitHub release, head → development, delete head."""
    g, cfg = ctx.git, ctx.cfg
    hub = ctx.gh()
    tag = f"{cfg.tag_prefix}{version}"
    title = f"chore(release): {tag}"
    notes = changelog.section_of(ctx.path("changelog").read_text(encoding="utf-8"), version)

    g.fetch()
    if not g.is_ancestor(g.remote_ref(head), g.remote_ref(cfg.main)):
        number = hub.ensure_pr(head, cfg.main, title, f"## Versión {tag}\n\n{notes}\n")
        hub.wait_checks(number, cfg["ci"]["required"])
        hub.merge(number, *_merge_message(title, number, head, cfg.main, found, []))
        g.fetch()
    if not g.tag_exists(tag):
        sign = ["-s"] if cfg["release"]["sign_tags"] else ["-a"]
        g.out("tag", *sign, tag, "-m", f"{tag}\n\n{notes}", g.remote_ref(cfg.main))
        g.out("push", g.remote, tag)
        say(f"· Etiqueta {tag} creada en {cfg.main}")
    if cfg["release"]["github_release"]:
        hub.release(tag, notes)

    # main ⊆ development: development always contains every tagged release.
    if not g.is_ancestor(g.remote_ref(cfg.main), g.remote_ref(cfg.development)):
        back_title = f"chore(release): merge {tag} into {cfg.development}"
        number = hub.ensure_pr(cfg.main, cfg.development, back_title,
                               f"Integra {tag} de {cfg.main} en {cfg.development}.\n")
        hub.wait_checks(number, cfg["ci"]["required"])
        hub.merge(number, f"{back_title} (#{number})",
                  f"Merge {cfg.main} into {cfg.development} after {tag}.\n\nRefs: {commits.NO_REFS}")
    g.fetch()
    g.checkout_synced(cfg.development)
    g.delete_branch(head)
    ctx.tracer.event("release", version=version, head=head)
    say(f"✓ Versión {tag} publicada en {cfg.main} e integrada en {cfg.development}")


def _tag_on_main(g: Git, tag: str, main: str) -> bool:
    """The tag is on the remote and points into ``main`` (a local-only or misplaced tag is not a published one)."""
    return (bool(g.out("ls-remote", "--tags", g.remote, f"refs/tags/{tag}")) and g.tag_exists(tag)
            and g.is_ancestor(f"refs/tags/{tag}^{{commit}}", g.remote_ref(main)))


def _unfinished_manual_release(ctx: Ctx) -> str | None:
    """Version of a release merged into ``main`` by hand whose branch the forge already deleted, if it is unfinished.

    It is unfinished while its tag is not published or ``main`` has not come back into ``development``.
    A version older than the latest tag is history, not a pending release: it never holds back a new one.
    """
    g, cfg = ctx.git, ctx.cfg
    if not g.remote_has(cfg.main):
        return None
    log = g.try_run("show", f"{g.remote_ref(cfg.main)}:{cfg['paths']['changelog']}")
    m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", log.stdout, re.MULTILINE) if log.returncode == 0 else None
    if not m:
        return None
    version = m.group(1)
    if tuple(map(int, version.split("."))) < g.latest_version(cfg.tag_prefix):
        return None
    done = _tag_on_main(g, f"{cfg.tag_prefix}{version}", cfg.main) and g.is_ancestor(g.remote_ref(cfg.main),
                                                                                    g.remote_ref(cfg.development))
    return None if done else version


def _release_manual(ctx: Ctx, head: str, version: str) -> None:
    """Local part of a release when the forge is not GitHub: list the manual steps and which ones git confirms.

    The release branch may be gone (the forge deletes it on merge): then the release is already in ``main``.
    """
    g, cfg = ctx.git, ctx.cfg
    tag, remote, main = f"{cfg.tag_prefix}{version}", g.remote, cfg.main
    g.fetch()
    on_remote = g.remote_has(head)
    log = g.out("show", f"{g.remote_ref(head if on_remote else main)}:{cfg['paths']['changelog']}")
    notes = changelog.section_of(log, version)
    path = _write_request(ctx, f"release-v{version}", f"# chore(release): {tag}\n\n## Versión {tag}\n\n{notes}\n")
    merged = not on_remote or g.is_ancestor(g.remote_ref(head), g.remote_ref(main))
    tagged = _tag_on_main(g, tag, main)
    back = merged and g.is_ancestor(g.remote_ref(main), g.remote_ref(cfg.development))
    ctx.tracer.event("release.manual", version=version, head=head, forge=cfg.forge, merged=merged, tagged=tagged, back=back)
    if merged and tagged and back:
        g.checkout_synced(cfg.development)
        g.delete_branch(head)
        ctx.tracer.event("release.manual.cleaned", version=version, head=head)
        say(f"✓ Versión {tag} publicada a mano; {head} borrada y {cfg.development} sincronizada.")
        return
    mark = lambda done: "✓" if done else "·"  # noqa: E731
    q = shlex.quote
    command = f"git fetch {q(remote)} && git tag -a {q(tag)} -m {q(tag)} {q(remote + '/' + main)} && git push {q(remote)} {q(tag)}"
    say(f"✓ {head} preparada con el CHANGELOG de {tag}; no se fusiona (forge = {cfg.forge}, mth no puede comprobar la CI).")
    say("Pasos manuales:")
    say(f"  {mark(merged)} 1. Abre un MR {head} → {main} (título y notas en {path}), espera a la CI y fusiona con merge commit.")
    say(f"  {mark(tagged)} 2. Etiqueta {main}: `{command}`.")
    say(f"  · 3. Publica la release {tag} en la forja con las notas de {path} (mth no puede comprobarlo).")
    say(f"  {mark(back)} 4. Abre un MR {main} → {cfg.development} y fusiona con merge commit.")
    say("Si tu forja borra la rama de origen al fusionar, no importa: `mth release` retoma desde "
        f"{main}. Cuando acabes, vuelve a ejecutarlo: marca lo que git confirma y limpia.")


def _open_work(ctx: Ctx) -> list[str]:
    """Remote work branches that will bring a changelog fragment (their content may belong in the next version)."""
    cfg, found = ctx.cfg, []
    try:
        remote = ctx.git.remote_branches()
    except MthError as exc:  # SPEC-0017: decide without them rather than refuse; never recommend waiting for unknown work
        warn(f"No se pudieron leer las ramas del remoto ({exc.message}); se decide sin ellas.")
        return []
    for name in remote:
        if name in (cfg.main, cfg.development) or branches.is_release(name):
            continue
        try:
            info = branches.parse(name, cfg)
        except MthError:
            continue
        if info is not None and not info.is_child and info.kind in cfg["changes"]["required_for"]:
            found.append(name)
    return sorted(found)


def _decide_release(ctx: Ctx, allow_major: bool) -> releaseplan.Plan:
    """Validate the fragments of ``development`` and decide whether and how to publish (SPEC-0017)."""
    cfg = ctx.cfg
    fragments = changelog.load_all(ctx.path("changes"))
    registry = ctx.registry()
    errors = [e for f in fragments for e in changelog.validate(f, registry, False, cfg.vocab)]
    if errors:
        raise MthError("Fragmentos inválidos:\n" + "\n".join(f"  - {e}" for e in errors))
    plan = releaseplan.decide(fragments, ctx.git.latest_version(cfg.tag_prefix), _open_work(ctx), allow_major, cfg.vocab)
    ctx.tracer.event("release.plan", decision=plan.decision, level=plan.level, version=plan.version,
                     reasons=plan.reasons)
    return plan


def release_plan(ctx: Ctx, allow_major: bool = False) -> None:
    """Say whether development should be published and at which level, writing nothing (SPEC-0017)."""
    g, cfg = ctx.git, ctx.cfg
    if g.current_branch() != cfg.development:
        raise MthError(f"`mth release --plan` se ejecuta desde {cfg.development}.",
                       hint=f"Cambia a {cfg.development} (por ejemplo, tras `mth integrate`).")
    g.require_clean()
    g.fetch()
    g.checkout_synced(cfg.development)
    for line in _decide_release(ctx, allow_major).lines():
        say(line)


def release(ctx: Ctx, allow_major: bool = False) -> None:
    """Publish development as a new version (resumable after any failure)."""
    g, cfg = ctx.git, ctx.cfg
    g.require_clean()
    g.fetch()
    pending = [b for b in g.remote_branches() if branches.is_release(b)]
    if len(pending) > 1:
        raise MthError(f"Hay varias ramas de release abiertas: {', '.join(pending)}.")
    if not pending and cfg.forge != forge.GITHUB and (unfinished := _unfinished_manual_release(ctx)):
        say(f"· Reanudando la publicación manual de v{unfinished} (la rama de release ya no existe)")
        _release_manual(ctx, f"release/v{unfinished}", unfinished)
        return
    if pending:
        head = pending[0]
        version = head.split("/v", 1)[1]
        say(f"· Reanudando {head}")
        g.checkout_synced(head)
    else:
        g.checkout_synced(cfg.development)
        plan = _decide_release(ctx, allow_major)
        if plan.decision == releaseplan.SKIP:
            raise MthError("No hay fragmentos en changes/: nada que publicar.")
        if plan.decision == releaseplan.BLOCKED:
            raise MthError("Publicación bloqueada:\n" + "\n".join(f"  - {r}" for r in plan.reasons))
        fragments = changelog.load_all(ctx.path("changes"))
        _gate_trace(ctx)
        _gate_tests(ctx)
        _check_version_files(ctx)
        version = plan.version
        head = f"release/v{version}"
        g.out("checkout", "-b", head)
        _apply_release(ctx, version, fragments)
        g.push(head)
    if cfg.forge != forge.GITHUB:  # SPEC-0016: the forge part is manual
        _release_manual(ctx, head, version)
        return
    found = ctx.own_commits(f"{g.remote_ref(cfg.main)}..{g.remote_ref(head)}")
    _publish(ctx, head, version, found)


def hotfix_finish(ctx: Ctx) -> None:
    """Publish the current hotfix branch as a patch version (resumable)."""
    g, cfg = ctx.git, ctx.cfg
    branch = g.current_branch()
    info = branches.parse(branch, cfg)
    if info is None or info.flow != "hotfix" or info.is_child:
        raise MthError("`mth hotfix finish` se ejecuta desde una rama hotfix de primer nivel.")
    if cfg.forge != forge.GITHUB:
        raise MthError(f"`mth hotfix finish` aún no está soportado con forge = {cfg.forge}.",
                       hint="Cierra el hotfix a mano (MR a main, etiqueta y MR de vuelta a development) o usa forge = github.")
    g.require_clean()
    g.fetch()
    _gate_plan(ctx, info)
    frag_path = ctx.path("changes") / branches.fragment_name(info)
    if frag_path.exists():
        _require_synced(ctx, cfg.main)
        _require_no_children(ctx, branch)
        _gate_commits(ctx, f"{g.remote_ref(cfg.main)}..HEAD")
        frag = _fragment(ctx, info)
        if frag.bump != "patch":
            raise MthError("Un hotfix solo publica versiones patch (bump: patch).")
        _check_version_files(ctx)
        _gate_trace(ctx)
        _review(ctx, info, branch)
        _gate_tests(ctx)
        version = changelog.next_version(g.latest_version(cfg.tag_prefix), "patch")
        _apply_release(ctx, version, [frag])
        g.push(branch)
    else:  # resuming: the fragment was already folded into the changelog by a previous run
        m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", ctx.path("changelog").read_text(encoding="utf-8"), re.MULTILINE)
        if not m:
            raise MthError(f"Falta el fragmento {frag_path.name}.", hint="Créalo con `mth changes new`.")
        version = m.group(1)
        say(f"· Reanudando la publicación de v{version}")
    found = ctx.own_commits(f"{g.remote_ref(cfg.main)}..HEAD")
    _publish(ctx, branch, version, found)


# -- docs ---------------------------------------------------------------------
def _slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def new_doc(ctx: Ctx, kind: str, title: str, category: str | None) -> Path:
    """Create a spec or ADR from its template with the next free ID."""
    cfg = ctx.cfg
    id_kind = cfg["trace"]["spec_kind" if kind == "spec" else "adr_kind"]
    ident = ctx.registry().next_id(id_kind)
    slug = _slugify(title)
    if not slug:
        raise MthError("El título no produce un nombre de fichero válido.")
    if kind == "adr":
        if not category:
            raise MthError("Un ADR necesita --category (subdirectorio de specs/adr).")
        folder = ctx.path("adr") / _slugify(category)
    else:
        folder = ctx.path("specs")
    path = folder / f"{ident}-{slug}.md"
    content = (cfg.vocab.templates / f"{kind}.md").read_text(encoding="utf-8")
    content = (content.replace("{{ID}}", ident).replace("{{TITLE}}", title.strip())
               .replace("{{DATE}}", date.today().isoformat())
               .replace("{{CATEGORY}}", category or ""))
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if kind == "spec":
        _link_spec_to_fragment(ctx, ident)
    ctx.tracer.event("doc.new", kind=kind, id=ident, path=str(path.relative_to(ctx.root)))
    say(f"✓ {ident} creado en {path.relative_to(ctx.root)}")
    return path


def _link_spec_to_fragment(ctx: Ctx, ident: str) -> None:
    """Add a new spec to the current branch fragment when its refs are empty."""
    try:
        info = branches.parse(ctx.git.current_branch(), ctx.cfg)
    except MthError:
        return
    if info is None or info.is_child:
        return
    frag = ctx.path("changes") / branches.fragment_name(info)
    if not frag.is_file():
        return
    text = frag.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^refs:[ \t]*$", f"refs: {ident}", text, count=1)
    if new != text:
        frag.write_text(new, encoding="utf-8")
        say(f"· {ident} añadido a las refs de {frag.name}")
