"""Git Flow operations: start, commit, sync, integrate, release and hotfix.

Every operation validates first and mutates last, and every remote step is
idempotent, so a failed run can simply be repeated (design for failure).
"""
from __future__ import annotations

import tempfile
import unicodedata
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import branches, changelog, commits, review, versions
from .config import Config
from .errors import MthError
from .gh import GitHub
from .git import Git
from .ids import IdRegistry
from .log import Tracer, say, warn
from .proc import run_shell
from .trace import check as trace_check

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
def _gate_trace(ctx: Ctx) -> None:
    findings = trace_check(ctx.cfg, ctx.git.files())
    if findings:
        listing = "\n".join(f"  - {f}" for f in findings[:50])
        more = f"\n  … y {len(findings) - 50} más" if len(findings) > 50 else ""
        raise MthError(f"Trazabilidad rota ({len(findings)} hallazgos):\n{listing}{more}",
                       hint="Corrige las referencias (skill mth-trace) y vuelve a intentarlo.")
    say("· Trazabilidad OK")


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


def _pr_body(summary: str, refs: list[str], frag: changelog.Fragment | None,
             tests: str, reviews: dict[str, dict]) -> str:
    parts = ["## Resumen", summary.strip(), "", "## Referencias",
             ", ".join(refs) if refs else "—", ""]
    if frag:
        parts += ["## Changelog", frag.path.read_text(encoding="utf-8").split("---", 2)[-1].strip(), ""]
    parts += ["## Verificación", f"- Tests: {tests}", "- Trazabilidad: OK"]
    if reviews:
        parts += ["", "## Revisión", "| Revisor | Bloqueantes | Resumen |", "|---|---|---|"]
        parts += [f"| {a} | {r['blocking']} | {r['summary'].replace(chr(10), ' ')} |"
                  for a, r in reviews.items()]
    parts += ["", "---", "_Generado por claude-methodology._"]
    return "\n".join(parts) + "\n"


# -- start --------------------------------------------------------------------
def start(ctx: Ctx, kind: str, slug: str, child: bool, spec: str | None) -> str:
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
    g.checkout_synced(base)
    g.out("checkout", "-b", name)
    if kind in cfg["changes"]["required_for"]:
        frag_path = ctx.path("changes") / branches.fragment_name(info)
        frag_path.parent.mkdir(parents=True, exist_ok=True)
        frag_path.write_text(changelog.template(kind, refs, cfg.vocab), encoding="utf-8")
        say(f"· Fragmento creado: {frag_path.relative_to(ctx.root)} (complétalo antes de integrar)")
    g.push(name)
    ctx.tracer.event("branch.start", branch=name, base=base, spec=spec)
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
    found = _gate_commits(ctx, f"{g.remote_ref(target)}..HEAD")
    frag = _fragment(ctx, info)
    _gate_trace(ctx)
    reviews = _review(ctx, info, branch)
    tests = _gate_tests(ctx)

    g.push(branch)
    hub = ctx.gh()
    refs = list(dict.fromkeys((frag.refs if frag else []) + [r for _, m in found for r in commits.refs_of(m)]))
    number = hub.ensure_pr(branch, target, title, _pr_body(summary, refs, frag, tests, reviews))
    hub.wait_checks(number, cfg["ci"]["required"])
    subject, body = _merge_message(title, number, branch, target, found, frag.refs if frag else [])
    hub.merge(number, subject, body)
    ctx.tracer.event("integrate", branch=branch, target=target, pr=number)
    _finish_integration(ctx, branch, target)
    say(f"✓ {branch} integrada en {target} (PR #{number}); rama borrada, historia conservada")


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


def release(ctx: Ctx) -> None:
    """Publish development as a new version (resumable after any failure)."""
    g, cfg = ctx.git, ctx.cfg
    g.require_clean()
    g.fetch()
    pending = [b for b in g.remote_branches() if branches.is_release(b)]
    if len(pending) > 1:
        raise MthError(f"Hay varias ramas de release abiertas: {', '.join(pending)}.")
    if pending:
        head = pending[0]
        version = head.split("/v", 1)[1]
        say(f"· Reanudando {head}")
        g.checkout_synced(head)
    else:
        g.checkout_synced(cfg.development)
        fragments = changelog.load_all(ctx.path("changes"))
        if not fragments:
            raise MthError("No hay fragmentos en changes/: nada que publicar.")
        registry = ctx.registry()
        errors = [e for f in fragments for e in changelog.validate(f, registry, False, cfg.vocab)]
        if errors:
            raise MthError("Fragmentos inválidos:\n" + "\n".join(f"  - {e}" for e in errors))
        _gate_trace(ctx)
        _gate_tests(ctx)
        _check_version_files(ctx)
        version = changelog.next_version(g.latest_version(cfg.tag_prefix), changelog.highest_bump(fragments))
        head = f"release/v{version}"
        g.out("checkout", "-b", head)
        _apply_release(ctx, version, fragments)
        g.push(head)
    found = ctx.own_commits(f"{g.remote_ref(cfg.main)}..{g.remote_ref(head)}")
    _publish(ctx, head, version, found)


def hotfix_finish(ctx: Ctx) -> None:
    """Publish the current hotfix branch as a patch version (resumable)."""
    g, cfg = ctx.git, ctx.cfg
    branch = g.current_branch()
    info = branches.parse(branch, cfg)
    if info is None or info.flow != "hotfix" or info.is_child:
        raise MthError("`mth hotfix finish` se ejecuta desde una rama hotfix de primer nivel.")
    g.require_clean()
    g.fetch()
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
