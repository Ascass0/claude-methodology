"""Command-line interface. This is the error boundary of every mth operation."""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from . import __version__, branches, changelog, commits, guard, review, session, setup
from .config import load
from .errors import MthError
from .flow import Ctx, commit, hotfix_finish, integrate, new_doc, release, required_reviewers, start, sync
from .git import Git
from .ids import IdRegistry
from .log import Tracer, say
from .trace import check as trace_check

EXIT_ERROR = 1
EXIT_BUG = 70


def _ctx(command: str) -> Ctx:
    git = Git.discover(Path.cwd())
    cfg = load(git.root)
    git.remote = cfg.remote
    return Ctx(cfg=cfg, git=git, tracer=Tracer(git.git_dir(), command))


def _split_refs(value: str | None) -> list[str]:
    return [r.strip() for r in (value or "").split(",") if r.strip() and r.strip().lower() != commits.NO_REFS]


def _text(value: str | None, file: str | None, name: str) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8")
    if value:
        return value
    raise MthError(f"Falta --{name} o --{name}-file.")


def _cmd_check_msg(args: argparse.Namespace) -> int:
    git = Git.discover(Path.cwd())
    cfg = load(git.root)
    message = Path(args.file).read_text(encoding="utf-8")
    errors = commits.validate(message, cfg, IdRegistry(cfg, git.files()))
    if errors:
        print("✗ Mensaje de commit inválido:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return EXIT_ERROR
    return 0


def _cmd_trace(_: argparse.Namespace) -> int:
    ctx = _ctx("trace")
    findings = trace_check(ctx.cfg, ctx.git.files())
    for f in findings:
        print(f"✗ {f}")
    say("✓ Trazabilidad OK" if not findings else f"{len(findings)} hallazgos")
    return EXIT_ERROR if findings else 0


def _cmd_changes(args: argparse.Namespace) -> int:
    ctx = _ctx("changes")
    folder = ctx.path("changes")
    if args.action == "new":
        info = branches.parse(ctx.git.current_branch(), ctx.cfg)
        if info is None or info.is_child:
            raise MthError("El fragmento pertenece a una rama de trabajo de primer nivel.")
        path = folder / branches.fragment_name(info)
        if path.exists():
            raise MthError(f"{path.name} ya existe.")
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(changelog.template(info.kind, _split_refs(args.refs)), encoding="utf-8")
        say(f"✓ {path.relative_to(ctx.root)}")
        return 0
    fragments = changelog.load_all(folder)
    registry = ctx.registry()
    errors = [e for f in fragments for e in changelog.validate(f, registry, False)]
    for e in errors:
        print(f"✗ {e}")
    if args.action == "preview" and fragments and not errors:
        version = changelog.next_version(ctx.git.latest_version(ctx.cfg.tag_prefix), changelog.highest_bump(fragments))
        print(changelog.render(version, fragments))
    say(f"{len(fragments)} fragmentos, {len(errors)} errores")
    return EXIT_ERROR if errors else 0


def _cmd_review(args: argparse.Namespace) -> int:
    ctx = _ctx("review")
    branch, sha = ctx.git.current_branch(), ctx.git.sha("HEAD")
    agents = ctx.cfg["review"]["agents"]
    if args.action == "record":
        if args.agent not in agents:
            raise MthError(f"'{args.agent}' no está en review.agents ({', '.join(agents) or 'vacío'}).")
        if args.blocking < 0:
            raise MthError("--blocking no puede ser negativo.")
        review.record(ctx.git.git_dir(), branch, sha, args.agent, args.blocking, args.summary)
        ctx.tracer.event("review.record", branch=branch, sha=sha, agent=args.agent, blocking=args.blocking)
        say(f"✓ Revisión de {args.agent} registrada para {sha[:8]} ({args.blocking} bloqueantes)")
        return 0
    info = branches.parse(branch, ctx.cfg)
    needed = required_reviewers(ctx, info) if info else []
    found = review.results(ctx.git.git_dir(), branch, sha)
    if not needed:
        say("No se requiere revisión para esta rama (tipo, rama hija o ningún revisor aplica).")
    for agent in needed:
        r = found.get(agent)
        print(f"{'✓' if r and not r['blocking'] else '✗'} {agent}: "
              f"{'pendiente' if not r else str(r['blocking']) + ' bloqueantes'}")
    skipped = [a for a in agents if a not in needed]
    if needed and skipped:
        say(f"No aplican a estos cambios: {', '.join(skipped)}")
    return 0


def _cmd_status(_: argparse.Namespace) -> int:
    for line in session._state(Path.cwd()):
        print(line)
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mth", description="claude-methodology")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="adopta la metodología en el repo actual")
    s.add_argument("--marketplace-repo", help="owner/repo del marketplace claude-methodology")
    s.add_argument("--github", action="store_true", help="aplica ajustes de merge y ruleset en GitHub")
    s.add_argument("--config", help="configuración preparada (fuera del repo) en lugar de la plantilla")
    sub.add_parser("doctor", help="comprueba la adopción")
    s = sub.add_parser("github", help="aplica ajustes de merge y ruleset en GitHub")

    s = sub.add_parser("doc", help="crea una spec o un ADR")
    s.add_argument("kind", choices=["spec", "adr"])
    s.add_argument("--title", required=True)
    s.add_argument("--category")

    s = sub.add_parser("branch", help="inicia una rama de trabajo")
    s.add_argument("kind")
    s.add_argument("slug")
    s.add_argument("--child", action="store_true", help="rama hija de la rama actual")
    s.add_argument("--spec", help="ID de la spec que motiva la rama")

    s = sub.add_parser("commit", help="commit con mensaje validado")
    s.add_argument("--type", required=True, choices=commits.TYPES)
    s.add_argument("--scope")
    s.add_argument("--summary", required=True)
    s.add_argument("--body")
    s.add_argument("--body-file")
    s.add_argument("--refs", help="IDs separados por comas (o n/a)")
    s.add_argument("--breaking", help="descripción del cambio incompatible")

    s = sub.add_parser("check-msg", help="valida un mensaje (hook commit-msg)")
    s.add_argument("file")
    sub.add_parser("trace", help="comprueba referencias, enlaces y criterios de aceptación")

    s = sub.add_parser("changes", help="fragmentos de changelog")
    s.add_argument("action", choices=["new", "check", "preview"])
    s.add_argument("--refs")

    s = sub.add_parser("review", help="registra o consulta revisiones del HEAD")
    s.add_argument("action", choices=["record", "status"])
    s.add_argument("agent", nargs="?")
    s.add_argument("--blocking", type=int, default=0)
    s.add_argument("--summary", default="")

    sub.add_parser("sync", help="integra la rama destino en la actual (merge)")
    s = sub.add_parser("integrate", help="integra la rama actual en su destino por PR")
    s.add_argument("--title", required=True, help="cabecera Conventional Commits en inglés")
    s.add_argument("--summary")
    s.add_argument("--summary-file")
    sub.add_parser("release", help="publica development como nueva versión")
    s = sub.add_parser("hotfix", help="cierra una rama hotfix")
    s.add_argument("action", choices=["finish"])
    sub.add_parser("status", help="posición de la rama actual en el flujo")
    sub.add_parser("guard", help="hook PreToolUse (stdin JSON)")
    sub.add_parser("session", help="hook SessionStart")
    return p


def _dispatch(args: argparse.Namespace) -> int:
    c = args.command
    if c == "guard":
        return guard.main(sys.stdin.read())
    if c == "session":
        return session.main()
    if c == "init":
        setup.init(Path.cwd(), args.marketplace_repo, args.github, args.config)
        return 0
    if c == "doctor":
        return EXIT_ERROR if setup.doctor(Path.cwd()) else 0
    if c == "github":
        ctx = _ctx(c)
        setup.configure_github(ctx.root, ctx.cfg.main, ctx.cfg.development)
        return 0
    if c == "check-msg":
        return _cmd_check_msg(args)
    if c == "trace":
        return _cmd_trace(args)
    if c == "changes":
        return _cmd_changes(args)
    if c == "review":
        if args.action == "record" and not (args.agent and args.summary):
            raise MthError("review record necesita <agente> y --summary.")
        return _cmd_review(args)
    if c == "status":
        return _cmd_status(args)
    ctx = _ctx(c)
    if c == "doc":
        new_doc(ctx, args.kind, args.title, args.category)
    elif c == "branch":
        start(ctx, args.kind, args.slug, args.child, args.spec)
    elif c == "commit":
        commit(ctx, args.type, args.scope, args.summary, _text(args.body, args.body_file, "body"),
               _split_refs(args.refs), args.breaking)
    elif c == "sync":
        sync(ctx)
    elif c == "integrate":
        integrate(ctx, args.title, _text(args.summary, args.summary_file, "summary"))
    elif c == "release":
        release(ctx)
    elif c == "hotfix":
        hotfix_finish(ctx)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except MthError as exc:
        print(f"✗ {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"  → {exc.hint}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
    except Exception:  # noqa: BLE001 — CLI boundary: unexpected errors are bugs.
        print("✗ Error interno de claude-methodology (bug):", file=sys.stderr)
        traceback.print_exc()
        return EXIT_BUG
