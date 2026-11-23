"""Command-line interface. This is the error boundary of every mth operation."""
from __future__ import annotations

import argparse
import re
import sys
import traceback
from pathlib import Path

from . import (__version__, agent_guard, agents, branches, catalog, changelog, commits, db_query, flow, guard, plan,
               review, session, setup, survey)
from .config import load
from .errors import MthError
from .flow import Ctx, commit, hotfix_finish, integrate, new_doc, release, required_reviewers, start, sync
from .git import Git
from .ids import IdRegistry
from .log import Tracer, say, warn

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


def _cmd_trace(args: argparse.Namespace) -> int:
    ctx = _ctx("trace")
    findings, legacy = flow.run_trace(ctx)
    for f in findings:
        print(f"✗ {f}")
    say("✓ Trazabilidad OK" if not findings else f"{len(findings)} hallazgos")
    if legacy:
        say(flow.legacy_summary(ctx, legacy))
        for f in legacy if args.legacy else []:
            print(f"⚠ {f}")
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
        path.write_text(changelog.template(info.kind, _split_refs(args.refs), ctx.cfg.vocab), encoding="utf-8")
        say(f"✓ {path.relative_to(ctx.root)}")
        return 0
    fragments = changelog.load_all(folder)
    registry = ctx.registry()
    errors = [e for f in fragments for e in changelog.validate(f, registry, False, ctx.cfg.vocab)]
    for e in errors:
        print(f"✗ {e}")
    if args.action == "preview" and fragments and not errors:
        version = changelog.next_version(ctx.git.latest_version(ctx.cfg.tag_prefix), changelog.highest_bump(fragments))
        print(changelog.render(version, fragments, vocab=ctx.cfg.vocab))
    say(f"{len(fragments)} fragmentos, {len(errors)} errores")
    return EXIT_ERROR if errors else 0


def _cmd_review(args: argparse.Namespace) -> int:
    ctx = _ctx("review")
    branch, sha = ctx.git.current_branch(), ctx.git.sha("HEAD")
    agents = ctx.cfg["review"]["agents"]
    if args.action == "record":
        if args.agent not in agents:
            raise MthError(f"'{args.agent}' no está en review.agents ({', '.join(agents) or 'vacío'}).")
        try:
            if not args.report:
                raise review.ReviewError("rejected", "Falta --report <fichero>.",
                                         hint="Guarda el informe literal del revisor en .work/tmp/ y pásalo.")
            entry = review.record_report(ctx.git.git_dir(), ctx.root, ctx.root / ".work" / "reviews", branch, sha,
                                         args.agent, Path(args.report), args.summary)
        except MthError as exc:
            ctx.tracer.event("review.not_recorded", branch=branch, sha=sha, agent=args.agent,
                             stage=getattr(exc, "stage", "unknown"), error=exc.message,
                             orphan=str(getattr(exc, "archived", None) or "") or None)
            raise
        ctx.tracer.event("review.failed" if entry["status"] == "failed" else "review.record", branch=branch, sha=sha, agent=args.agent, status=entry["status"],
                         blocking=entry.get("blocking"), attempts=entry["attempts"],
                         reason=entry.get("reason"), previous_status=entry.get("previous_status"))
        if entry["status"] == "failed":
            stop = entry["failures"] >= 2
            raise MthError(
                f"Revisión de {args.agent} fallida (intento {entry['attempts']}, fallo {entry['failures']}): {entry['reason']}. "
                "No aprueba nada.",
                hint=("Segundo fallo: detente y avisa (PRINCIPLES §11); revisa el prompt del revisor."
                      if stop else
                      "Pide UNA corrección al mismo agente con SendMessage (mismo contexto), indicándole "
                      "este motivo, y registra de nuevo. No lances otro agente desde cero."))
        say(f"✓ Revisión de {args.agent} registrada para {sha[:8]} ({entry['blocking']} bloqueantes, "
            f"intento {entry['attempts']})")
        return 0
    info = branches.parse(branch, ctx.cfg)
    needed = required_reviewers(ctx, info) if info else []
    found = review.results(ctx.git.git_dir(), branch, sha)
    if not needed:
        say("No se requiere revisión para esta rama (tipo, rama hija o ningún revisor aplica).")
    for agent in needed:
        r = found.get(agent)
        approved, state = review.describe(r)
        print(f"{'✓' if approved else '✗'} {agent}: {state}")
    skipped = [a for a in agents if a not in needed]
    if needed and skipped:
        say(f"No aplican a estos cambios: {', '.join(skipped)}")
    return 0


def _spec_text(ctx: Ctx, spec_id: str) -> tuple[str, str]:
    """Relative path and text of the spec that defines ``spec_id``."""
    registry = ctx.registry()
    spec_kind = ctx.cfg["trace"]["spec_kind"]
    places = registry.definitions.get(spec_id)
    if registry.kind_of(spec_id) != spec_kind or not places:
        raise MthError(f"{spec_id} no es una spec definida.", hint="Comprueba el ID con mth trace.")
    rel = places[0][0]
    return rel, (ctx.root / rel).read_text(encoding="utf-8")


_MODEL_ARG = re.compile(r"^(T-\d{2})=([a-z]+)$")


def _plan_tasks(ctx: Ctx, spec_id: str) -> tuple[str, list[plan.Task]]:
    """Valid tasks of the spec's plan; prints every problem and fails when there are any."""
    rel, text = _spec_text(ctx, spec_id)
    vocab = ctx.cfg.vocab
    if not plan.has_plan(text, vocab):
        raise MthError(f"{spec_id} no tiene sección '## {vocab.plan_section}'.",
                       hint="Añade el plan a la spec (skill mth-spec) antes de delegar.")
    tasks, problems = plan.check(text, ctx.cfg["models"]["ladder"], vocab)
    for p in problems:
        print(f"✗ {rel}:{p.line}: {p.message}")
    if problems:
        raise MthError(f"{len(problems)} errores en el plan de {spec_id}.")
    return rel, tasks


def _model_overrides(values: list[str] | None, wave_tasks: set[str], ladder: list[str]) -> dict[str, str]:
    """Parse ``--model T-NN=<alias>``; any invalid value aborts before verifying (SPEC-0002)."""
    out: dict[str, str] = {}
    for value in values or []:
        m = _MODEL_ARG.match(value)
        if not m:
            raise MthError(f"--model mal formado: '{value}'.", hint="Formato: --model T-NN=<alias>.")
        task, model = m.groups()
        if model not in ladder:
            raise MthError(f"--model {value}: '{model}' no está en models.ladder ({', '.join(ladder)}).")
        if task not in wave_tasks:
            raise MthError(f"--model {value}: {task} no pertenece a la oleada.")
        out[task] = model
    return out


def _cmd_plan_stats(ctx: Ctx, spec: str | None) -> int:
    path = ctx.git.git_dir() / "mth" / "trace.jsonl"
    if not path.is_file():
        say("No hay datos: la traza aún no registra tareas verificadas.")
        return 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        rows, unreadable = plan.stats(fh.readlines(), spec)
    if unreadable:
        warn(f"{unreadable} líneas ilegibles de la traza ignoradas")
    if not rows:
        say("No hay datos: la traza no registra tareas verificadas" + (f" de {spec}." if spec else "."))
        return 0
    order = {m: i for i, m in enumerate(ctx.cfg["models"]["ladder"])}
    rows.sort(key=lambda r: (order.get(r.model, len(order)), r.model))
    print(f"{'Modelo':<8} {'Intentos':>8} {'ok':>4} {'Fallidos':>8} {'% ok':>6}")
    for r in rows:
        print(f"{r.model:<8} {r.attempts:>8} {r.ok:>4} {r.failed:>8} {r.ok_rate:>5.0f}%")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    ctx = _ctx("plan")
    models = ctx.cfg["models"]
    if args.action == "stats":
        if args.spec:
            raise MthError("plan stats no admite una spec posicional.", hint="Usa --spec SPEC-NNNN.")
        return _cmd_plan_stats(ctx, args.only_spec)
    if not args.spec:
        raise MthError(f"plan {args.action} necesita el ID de la spec.")
    _, tasks = _plan_tasks(ctx, args.spec)
    if args.action == "check":
        by_wave = plan.waves(tasks)
        say(f"✓ Plan de {args.spec} válido: {len(tasks)} tareas en {len(by_wave)} oleadas")
        for wave, items in by_wave.items():
            print(f"  Oleada {wave}: " + ", ".join(f"{t.id} ({t.effective_model(models['task'])})" for t in items))
        return 0
    if args.action == "model":
        task = next((t for t in tasks if t.id == args.task), None)
        if task is None:
            raise MthError(f"{args.task or '(sin tarea)'} no es una tarea del plan de {args.spec}.")
        model = task.effective_model(models["task"])
        print(plan.next_model(models["ladder"], model) if args.retry else model)
        return 0
    if args.wave is None or not args.manifest:
        raise MthError("plan verify necesita --wave y al menos un --manifest.")
    in_wave = {t.id: t for t in tasks if t.wave == args.wave}
    overrides = _model_overrides(args.model, set(in_wave), models["ladder"])
    manifests, errors = [], []
    for source in args.manifest:
        m, errs = plan.load_manifest(Path(source))
        errors += errs
        if m is not None:
            manifests.append(m)
    result = plan.verify_wave(tasks, args.wave, manifests, ctx.git.worktree_changes())
    errors += result.errors
    for task_id, (outcome, digest) in sorted(result.outcomes.items()):
        model = overrides.get(task_id) or in_wave[task_id].effective_model(models["task"])
        ctx.tracer.event("plan.task", spec=args.spec, task=task_id, wave=args.wave, model=model,
                         result=outcome, manifest=digest)
    for w in result.warnings:
        warn(w)
    for e in errors:
        print(f"✗ {e}")
    ctx.tracer.event("plan.verify", spec=args.spec, wave=args.wave, errors=len(errors), warnings=len(result.warnings))
    if errors:
        say(f"Oleada {args.wave} de {args.spec} rechazada: {len(errors)} errores")
        return EXIT_ERROR
    suffix = f" ({len(result.warnings)} desvíos por resolver)" if result.warnings else ""
    say(f"✓ Oleada {args.wave} de {args.spec} verificada{suffix}")
    return 0


def _cmd_models(_: argparse.Namespace) -> int:
    models = _ctx("models").cfg["models"]
    print(f"Escalera de reintento: {' → '.join(models['ladder'])}")
    for role, label in (("task", "Tareas del plan sin modelo"), ("review", "Revisores"),
                        ("documenter", "Documentador")):
        print(f"{label}: {models[role]}")
    return 0


def _cmd_survey(args: argparse.Namespace) -> int:
    git = Git.discover(Path.cwd())
    result = survey.reconfigure(git, load(git.root), args.only) if args.reconfigure else survey.run(git)
    if args.json:
        print(result.to_json())
        return 0
    print(f"Perfil: {result.profile}")
    for key, value in result.signals.items():
        if value:
            print(f"· {key}: {value}")
    print("Preguntas: " + ", ".join(f"{q['id']} ({q.get('current') or q['evidence']})" for q in result.questions))
    for w in result.warnings:
        warn(w)
    return 0


def _cmd_db_query(args: argparse.Namespace) -> int:
    if args.schema == bool(args.sql):
        raise MthError("Indica --schema o una consulta SQL, no ambas.")
    git = Git.discover(Path.cwd())
    cfg = load(git.root)
    defaults = catalog.load_meta(catalog.CATALOG_DIR, db_query.AGENT)["vars"]
    print(db_query.run(cfg["agents"], defaults, git.root, args.db, None if args.schema else args.sql))
    return 0


def _cmd_agents(args: argparse.Namespace) -> int:
    git = Git.discover(Path.cwd())
    manager = agents.Manager(load(git.root))
    if args.action == "list":
        manager.list()
        return 0
    if args.action == "add":
        return EXIT_ERROR if manager.add(args.names, args.profile, args.replace) else 0
    if args.action == "sync":
        return EXIT_ERROR if manager.sync(args.names, args.force) else 0
    if args.action == "diff":
        print(manager.diff(args.name), end="")
        return 0
    manager.remove(args.name)
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
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--config", help="configuración preparada (fuera del repo) en lugar de la plantilla")
    mode.add_argument("--answers", help="respuestas de la entrevista de adopción (JSON, skill mth-init)")
    mode.add_argument("--decline", action="store_true", help="desactiva el plugin en este repo (no versionado)")
    s = sub.add_parser("survey", help="inventario del repo antes de adoptar (solo lectura)")
    s.add_argument("--json", action="store_true", help="salida en JSON para la skill mth-init")
    s.add_argument("--reconfigure", action="store_true", help="inventario de un repo adoptado (skill mth-reconfigure)")
    s.add_argument("--only", help="preguntas o bloques separados por comas (con --reconfigure)")
    s = sub.add_parser("reconfigure", help="aplica las respuestas de una reestructuración en una rama")
    s.add_argument("--answers", required=True, help="respuestas de la reestructuración (JSON, skill mth-reconfigure)")
    s.add_argument("--only", help="las mismas preguntas o bloques que en mth survey --reconfigure")
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
    s = sub.add_parser("trace", help="comprueba referencias, enlaces y criterios de aceptación")
    s.add_argument("--legacy", action="store_true", help="lista también los hallazgos en contenido legado")

    s = sub.add_parser("changes", help="fragmentos de changelog")
    s.add_argument("action", choices=["new", "check", "preview"])
    s.add_argument("--refs")

    s = sub.add_parser("review", help="registra o consulta revisiones del HEAD")
    s.add_argument("action", choices=["record", "status"])
    s.add_argument("agent", nargs="?")
    s.add_argument("--report", help="informe literal del revisor (sección HALLAZGOS y última línea 'BLOQUEANTES: <n>'); mth cuenta los bloqueantes")
    s.add_argument("--summary", default="")

    s = sub.add_parser("plan", help="plan de trabajo: validar, verificar una oleada, modelo de una tarea, métricas")
    s.add_argument("action", choices=["check", "verify", "model", "stats"])
    s.add_argument("spec", nargs="?", help="ID de la spec (SPEC-NNNN)")
    s.add_argument("task", nargs="?", help="ID de la tarea (plan model)")
    s.add_argument("--wave", type=int, help="oleada a verificar")
    s.add_argument("--manifest", action="append", help="manifiesto JSON de una tarea (repetible)")
    s.add_argument("--model", action="append", help="modelo usado en una tarea: T-NN=<alias> (repetible)")
    s.add_argument("--retry", action="store_true", help="plan model: modelo del reintento")
    s.add_argument("--spec", dest="only_spec", help="plan stats: solo esta spec")
    sub.add_parser("models", help="escalera de modelos y nivel de cada rol")

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
    sub.add_parser("agent-guard", help="guard de los agentes del catálogo (stdin JSON; falla cerrado)")
    s = sub.add_parser("agents", help="agentes del catálogo: list, add, sync, diff, remove")
    actions = s.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="agentes del catálogo y su estado en el repo")
    a = actions.add_parser("add", help="renderiza e instala agentes")
    a.add_argument("names", nargs="*")
    a.add_argument("--profile", help="instala los agentes de un perfil (base, opcional, autonomo)")
    a.add_argument("--replace", action="store_true", help="sustituye un agente del repo sin cabecera del catálogo")
    a = actions.add_parser("sync", help="vuelve a renderizar los agentes instalados conservando su sección local")
    a.add_argument("names", nargs="*")
    a.add_argument("--force", action="store_true", help="sobrescribe ediciones manuales de la parte generada")
    a = actions.add_parser("diff", help="diferencias entre lo instalado y lo que se renderizaría hoy")
    a.add_argument("name")
    a = actions.add_parser("remove", help="desinstala un agente del catálogo")
    a.add_argument("name")
    s = sub.add_parser("db-query", help="consulta SQLite de solo lectura sobre [agents.lector-estado].databases")
    s.add_argument("--db", required=True, help="alias declarado de la base")
    s.add_argument("--schema", action="store_true", help="lista tablas y vistas con su SQL")
    s.add_argument("sql", nargs="?", help="una única sentencia de lectura")
    sub.add_parser("session", help="hook SessionStart")
    return p


def _dispatch(args: argparse.Namespace) -> int:
    c = args.command
    if c == "guard":
        return guard.main(sys.stdin.read())
    if c == "agent-guard":  # SPEC-0012: its own entry point, fails closed
        return agent_guard.main(sys.stdin.read())
    if c == "session":
        return session.main()
    if c == "init":
        if args.decline:
            setup.decline(Path.cwd())
        else:
            setup.init(Path.cwd(), args.marketplace_repo, args.github, args.config, args.answers)
        return 0
    if c == "survey":
        if args.only and not args.reconfigure:
            raise MthError("--only solo se usa con --reconfigure.")
        return _cmd_survey(args)
    if c == "reconfigure":
        setup.reconfigure(Path.cwd(), args.answers, args.only)
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
        if args.action == "record" and not (args.agent and args.summary and args.report):
            raise MthError("review record necesita <agente>, --report y --summary.")
        return _cmd_review(args)
    if c == "plan":
        return _cmd_plan(args)
    if c == "models":
        return _cmd_models(args)
    if c == "status":
        return _cmd_status(args)
    if c == "db-query":
        return _cmd_db_query(args)
    if c == "agents":
        return _cmd_agents(args)
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
