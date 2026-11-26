"""Agreed plans (ADR-0021, SPEC-0023): format, numbering, states, validation and the branch gate.

A plan is a local file in ``.work/plans/``. Parsing and validation work on text, so they test
without a repository; the file operations are the only part that touches the disk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import globs, plan as spec_plan
from .errors import MthError
from .files import atomic_write

STATES = ("borrador", "acordado", "en curso", "ejecutado", "abandonado")
ACTIVE = ("acordado", "en curso")
TRANSITIONS = {
    "borrador": ("acordado", "abandonado"),
    "acordado": ("en curso", "ejecutado", "abandonado"),
    "en curso": ("ejecutado", "abandonado"),
    "ejecutado": (),
    "abandonado": (),
}
SECTIONS = ("Idea", "Decisiones acordadas", "Fuera de alcance", "Tareas", "Agentes a instalar",
            "Verificación y cierre", "Riesgos", "Preguntas abiertas", "Registro de ejecución")
# A roadmap lists phases, each with its own plan, instead of tasks to run: no agents to install or checks.
ROADMAP_SECTIONS = ("Idea", "Decisiones acordadas", "Fases", "Fuera de alcance", "Riesgos",
                    "Preguntas abiertas", "Registro de ejecución")
TASK_COLUMNS = ("Tarea", "Oleada", "Agente sugerido", "Depende de", "Ficheros", "Hecho cuando")
MAX_TASKS = 50
MAX_NUMBER_TRIES = 20
MAX_BYTES = 256 * 1024  # a plan is a short working document: anything bigger is not read
MAX_TITLE = 120

_FILE = re.compile(r"^PLAN-(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
_ID = re.compile(r"^PLAN-\d{4}$")
_TASK = re.compile(r"^T-\d{2}$")
_CODE = re.compile(r"`([^`]+)`")
_NO_FILES = ("", "—", "-", "solo lectura")

TEMPLATE = """# {ident} · {title}

- Estado: borrador
- Fecha: {today}
- Acordado con: —
- Refs: —
- Rama: —

## Idea

## Decisiones acordadas

## Fuera de alcance

## Tareas

| Tarea | Oleada | Agente sugerido | Depende de | Ficheros | Hecho cuando |
|---|---|---|---|---|---|

## Agentes a instalar

Ninguno.

## Verificación y cierre

## Riesgos

## Preguntas abiertas

## Registro de ejecución

| Tarea | Agente real | Modelo | Resultado | Desviación y motivo |
|---|---|---|---|---|
"""


@dataclass(frozen=True)
class Plan:
    """The header of a plan file."""

    ident: str
    slug: str
    path: Path
    state: str
    title: str
    branches: tuple[str, ...]


@dataclass(frozen=True)
class Problem:
    """A plan error. ``line`` is the line of the plan, or 0 when it concerns the plan as a whole."""

    line: int
    message: str

    def __str__(self) -> str:
        return f"línea {self.line}: {self.message}" if self.line else self.message


def _header(text: str) -> str:
    """The lines before the first section: the only place a header field is read from."""
    return text.split("\n## ", 1)[0]


def _field(text: str, name: str) -> str | None:
    found = re.search(rf"^- {re.escape(name)}:[ \t]*(.*)$", _header(text), re.MULTILINE)
    return found.group(1).strip() if found else None


def parse(text: str, path: Path) -> Plan:
    """The header of a plan.

    Raises:
        MthError: The file name or the header does not follow the format; names the file.
    """
    named = _FILE.match(path.name)
    title = re.match(r"^# (PLAN-\d{4}) · (.+)$", text.splitlines()[0]) if text.strip() else None
    state = _field(text, "Estado")
    if not named or title is None or title.group(1) != f"PLAN-{named.group(1)}":
        raise MthError(f"El plan {path.name} no sigue el formato (nombre PLAN-NNNN-<slug>.md y título «# PLAN-NNNN · …»).",
                       hint="Corrígelo o créalo de nuevo con `mth plan new`.")
    if state not in STATES:
        raise MthError(f"El plan {path.name} tiene un estado inválido: {state!r}.",
                       hint=f"Estados: {', '.join(STATES)}.")
    return Plan(title.group(1), named.group(2), path, state, title.group(2).strip(),
                tuple(b for b in _CODE.findall(_field(text, "Rama") or "") if " " not in b))


def _sections(text: str) -> dict[str, tuple[int, list[tuple[int, str]]]]:
    found: dict[str, tuple[int, list[tuple[int, str]]]] = {}
    current: list[tuple[int, str]] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            name = line[3:].strip()
            current = []
            found[name] = (number, current)
        elif current is not None:
            current.append((number, line))
    return found


def _cells(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [c.strip() for c in body.split("|")]


def _table(rows: list[tuple[int, str]]) -> tuple[list[str], list[tuple[int, list[str]]]]:
    lines = [(n, s) for n, s in rows if s.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    return _cells(lines[0][1]), [(n, _cells(s)) for n, s in lines[2:]]


@dataclass(frozen=True)
class _Task:
    ident: str
    wave: int
    deps: tuple[str, ...]
    files: tuple[str, ...]
    line: int


def _tasks(rows: list[tuple[int, list[str]]], problems: list[Problem]) -> list[_Task]:
    tasks: list[_Task] = []
    for line, cells in rows:
        if len(cells) != len(TASK_COLUMNS):
            problems.append(Problem(line, f"la fila tiene {len(cells)} columnas y deben ser {len(TASK_COLUMNS)}"))
            continue
        ident, wave_raw, _, deps_raw, files_raw, _ = cells
        if not _TASK.match(ident):
            problems.append(Problem(line, f"ID de tarea inválido: '{ident}' (formato T-NN)"))
        if not wave_raw.isdigit():
            problems.append(Problem(line, f"oleada inválida: '{wave_raw}' (entero ≥ 0)"))
        deps = tuple(d.strip() for d in deps_raw.split(",") if d.strip() not in ("", "—", "-"))
        files = tuple(f.strip() for f in _CODE.findall(files_raw))
        if files_raw.strip().lower() not in _NO_FILES and not files:
            problems.append(Problem(line, "la columna Ficheros solo admite rutas entre comillas invertidas, «solo lectura» o «—»"))
        problems += [Problem(line, f"ruta no permitida: '{f}'") for f in files if not globs.valid_path(f)]
        tasks.append(_Task(ident, int(wave_raw) if wave_raw.isdigit() else 0, deps, files, line))
    return tasks


def _cycle_problems(by_id: dict[str, _Task]) -> list[Problem]:
    problems: list[Problem] = []
    seen: set[str] = set()

    def visit(ident: str, path: tuple[str, ...]) -> None:
        if ident in path:
            problems.append(Problem(by_id[ident].line, "ciclo de dependencias: " + " → ".join((*path[path.index(ident):], ident))))
        elif ident not in seen and ident in by_id:
            seen.add(ident)
            for dep in by_id[ident].deps:
                visit(dep, (*path, ident))

    for ident in by_id:
        visit(ident, ())
    return problems


def _graph_problems(tasks: list[_Task]) -> list[Problem]:
    problems: list[Problem] = []
    by_id: dict[str, _Task] = {}
    for task in tasks:
        if task.ident in by_id:
            problems.append(Problem(task.line, f"ID de tarea repetido: {task.ident}"))
        by_id[task.ident] = task
    for task in tasks:
        for dep in task.deps:
            if dep not in by_id:
                problems.append(Problem(task.line, f"{task.ident} depende de {dep}, que no existe"))
            elif by_id[dep].wave >= task.wave:
                problems.append(Problem(task.line, f"{task.ident} (oleada {task.wave}) depende de {dep} "
                                                    f"(oleada {by_id[dep].wave}): debe ir en una oleada posterior"))
    problems += _cycle_problems(by_id)
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            if a.wave == b.wave and any(spec_plan.overlaps(x, y) for x in a.files for y in b.files):
                problems.append(Problem(b.line, f"{a.ident} y {b.ident} comparten ficheros en la oleada {a.wave}"))
    return problems


def _section_problems(sections: dict, expected: tuple[str, ...]) -> list[Problem]:
    problems = [Problem(0, f"falta la sección «{name}»") for name in expected if name not in sections]
    if not problems and [name for name in sections if name in expected] != list(expected):
        problems.append(Problem(0, "las secciones no siguen el orden: " + ", ".join(expected)))
    return problems


def _question_problems(start: int, rows: list[tuple[int, str]]) -> list[Problem]:
    pending = [(n, s.strip()) for n, s in rows if s.strip()]
    if not pending:
        return [Problem(start, "«Preguntas abiertas» está vacía: escribe «Ninguna.» o las preguntas")]
    if pending[0][1].lower().startswith("ninguna"):
        return []
    return [Problem(n, f"pregunta abierta sin resolver: {s}") for n, s in pending]


def _task_table_problems(start: int, rows: list[tuple[int, str]]) -> list[Problem]:
    header, body = _table(rows)
    if tuple(header) != TASK_COLUMNS:
        return [Problem(start, "la tabla de tareas debe tener las columnas: " + " | ".join(TASK_COLUMNS))]
    problems: list[Problem] = []
    tasks = _tasks(body, problems)
    if not tasks:
        problems.append(Problem(start, "el plan no tiene tareas"))
    if len(tasks) > MAX_TASKS:
        problems.append(Problem(start, f"más de {MAX_TASKS} tareas"))
    return problems + _graph_problems(tasks)


def check(text: str) -> list[Problem]:
    """Every problem that keeps a plan from being agreed (empty when it is valid)."""
    sections = _sections(text)
    expected = ROADMAP_SECTIONS if "Fases" in sections and "Tareas" not in sections else SECTIONS
    problems = _section_problems(sections, expected)
    if "Preguntas abiertas" in sections:
        problems += _question_problems(sections["Preguntas abiertas"][0], sections["Preguntas abiertas"][1])
    if "Tareas" in sections:
        problems += _task_table_problems(sections["Tareas"][0], sections["Tareas"][1])
    return problems


# -- files --------------------------------------------------------------------
def raw(path: Path) -> str:
    """The text of a plan file, whatever its format.

    Raises:
        MthError: The file cannot be read, is not UTF-8 or is bigger than ``MAX_BYTES``.
    """
    try:
        if path.stat().st_size > MAX_BYTES:
            raise MthError(f"El plan {path.name} pesa más de {MAX_BYTES // 1024} KB: no se lee.",
                           hint="Un plan es un documento corto: reduce su contenido.")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MthError(f"No se puede leer el plan {path.name}: {exc}.", hint="Corrige el fichero o créalo de nuevo.") from exc


def read(path: Path) -> tuple[Plan, str]:
    """A plan and its text.

    Raises:
        MthError: The file cannot be read or does not follow the format.
    """
    text = raw(path)
    return parse(text, path), text


def find(directory: Path, ident: str) -> Path:
    """The file of ``PLAN-NNNN``.

    Raises:
        MthError: The ID is malformed or no plan has it.
    """
    if not _ID.match(ident):
        raise MthError(f"'{ident}' no es un ID de plan (formato PLAN-NNNN).")
    found = sorted(directory.glob(f"{ident}-*.md")) if directory.is_dir() else []
    if not found:
        raise MthError(f"No existe {ident} en {directory}.", hint="Créalo con `mth plan new <slug>` (skill mth-plan).")
    if len(found) > 1:
        raise MthError(f"{ident} está en más de un fichero: {', '.join(p.name for p in found)}.",
                       hint="Deja un solo fichero por número de plan.")
    return found[0]


def listing(directory: Path) -> tuple[list[Plan], list[Path]]:
    """Readable plans, in order, and the files that could not be read."""
    plans: list[Plan] = []
    broken: list[Path] = []
    for path in sorted(directory.glob("PLAN-*.md")) if directory.is_dir() else []:
        try:
            plans.append(read(path)[0])
        except MthError:
            broken.append(path)
    return plans, broken


def create(directory: Path, slug: str, title: str, today: date | None = None) -> Path:
    """A new plan in ``borrador`` with the highest number plus one; never overwrites a file.

    Raises:
        MthError: The slug is invalid or a free number could not be taken.
    """
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        raise MthError(f"Slug inválido: '{slug}'.", hint="Minúsculas, dígitos y guiones (ejemplo: planes-acordados).")
    if not title.strip() or len(title) > MAX_TITLE or any(ord(c) < 32 or ord(c) == 127 for c in title):
        raise MthError(f"Título inválido: una sola línea de hasta {MAX_TITLE} caracteres, sin saltos de línea ni caracteres de control.",
                       hint="Un título con saltos de línea podría inyectar campos de cabecera en el plan.")
    directory.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for p in directory.glob("PLAN-*.md") if (m := _FILE.match(p.name))]
    number = max(numbers, default=0) + 1
    for _ in range(MAX_NUMBER_TRIES):
        ident = f"PLAN-{number:04d}"
        path = directory / f"{ident}-{slug}.md"
        try:
            with path.open("x", encoding="utf-8") as handle:  # exclusive: another session may take the number
                handle.write(TEMPLATE.format(ident=ident, title=title, today=(today or date.today()).isoformat()))
            return path
        except FileExistsError:
            number += 1
    raise MthError("No se pudo reservar un número de plan libre.", hint="Repite el comando.")


def transition(path: Path, new: str, today: date | None = None) -> Plan:
    """Move a plan to ``new``; ``acordado`` also validates it and stamps the date.

    Raises:
        MthError: The transition is not allowed, or the plan is not valid to be agreed.
    """
    plan, text = read(path)
    if new not in TRANSITIONS[plan.state]:
        raise MthError(f"{plan.ident} está «{plan.state}» y no puede pasar a «{new}».",
                       hint=f"Desde «{plan.state}» solo: {', '.join(TRANSITIONS[plan.state]) or 'nada (estado final)'}.")
    if new == "acordado":
        if problems := check(text):
            raise MthError(f"{plan.ident} no se puede acordar ({len(problems)} problemas):\n"
                           + "\n".join(f"  - {p}" for p in problems[:30]),
                           hint="Corrige el plan con la persona y vuelve a ejecutar `mth plan agree`.")
        text = _set_field(text, "Acordado con", f"la persona que desarrolla ({(today or date.today()).isoformat()})")
    text = _set_field(text, "Estado", new)
    atomic_write(path, text)
    return parse(text, path)


def _set_field(text: str, name: str, value: str) -> str:
    line = f"- {name}: {value}"
    pattern = re.compile(rf"^- {re.escape(name)}:.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    state = re.search(r"^- Estado:.*$", text, re.MULTILINE)  # a missing field goes under the state line
    return text[:state.end()] + f"\n{line}" + text[state.end():] if state else text


def add_branch(path: Path, branch: str) -> Plan:
    """Record a branch in the plan and move ``acordado`` to ``en curso``."""
    plan, text = read(path)
    branches = (*plan.branches, branch) if branch not in plan.branches else plan.branches
    text = _set_field(text, "Rama", ", ".join(f"`{b}`" for b in branches))
    if plan.state == "acordado":
        text = _set_field(text, "Estado", "en curso")
    atomic_write(path, text)
    return parse(text, path)


# -- gate ---------------------------------------------------------------------
def for_start(directory: Path, ident: str | None, kind: str) -> Path:
    """The plan a new branch of a required ``kind`` may use.

    Raises:
        MthError: No ``--plan`` was given, the plan does not exist or is not agreed.
    """
    if not ident:
        raise MthError(f"Una rama {kind} necesita un plan acordado: falta --plan PLAN-NNNN.",
                       hint="Crea el plan con la skill mth-plan (`mth plan new <slug>`), acuérdalo con la persona y pásalo con --plan.")
    path = find(directory, ident)
    plan, _ = read(path)
    if plan.state not in ACTIVE:
        raise MthError(f"{plan.ident} está «{plan.state}»: solo valen los planes {' o '.join(ACTIVE)}.",
                       hint="Acuérdalo con la persona (`mth plan agree`) o usa otro plan.")
    return path


def running_for(found: list[Plan], top_branch: str) -> Plan | None:
    """The ``en curso`` plan that lists ``top_branch``, among already read plans."""
    return next((p for p in found if p.state == "en curso" and top_branch in p.branches), None)


def for_branch(directory: Path, top_branch: str) -> Plan:
    """The ``en curso`` plan that lists ``top_branch``.

    Raises:
        MthError: No readable plan lists the branch; names any plan file it could not read.
    """
    plans, broken = listing(directory)
    if (plan := running_for(plans, top_branch)) is not None:
        return plan
    unreadable = f" Planes ilegibles: {', '.join(p.name for p in broken)}." if broken else ""
    raise MthError(f"La rama {top_branch} no tiene un plan «en curso» que la liste.{unreadable}",
                   hint="Crea la rama con `mth branch <tipo> <slug> --plan PLAN-NNNN` o añade la rama a `- Rama:` de su plan acordado.")
