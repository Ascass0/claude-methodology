"""Work plans and task manifests for verifiable delegation (SPEC-0001, ADR-0001).

A spec may contain a ``## Plan de trabajo`` section: a fixed-column markdown
table that assigns files and acceptance criteria to tasks grouped in waves.
Each delegated agent returns a JSON manifest; :func:`verify_wave` compares the
manifests of one wave with the plan and with the real working-tree changes.

Every check reports all problems at once. When in doubt the answer is "no":
an overlap that cannot be ruled out is an overlap, a missing manifest is a task
that did not run.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import globs
from .config import DEFAULTS

SECTION = "Plan de trabajo"
COLUMNS = ["Tarea", "Oleada", "Ficheros", "Criterios"]
MODEL_COLUMN = "Modelo"
DEFAULT_LADDER: tuple[str, ...] = tuple(DEFAULTS["models"]["ladder"])
OUTCOMES = ("ok", "not_run", "not_completed", "rejected")
MAX_TASKS = 50
MAX_MANIFEST_BYTES = 256 * 1024
STATUSES = ("done", "blocked", "failed")
TEST_RESULTS = ("pass", "fail")

_FENCE = re.compile(r"^\s*(```|~~~)")
_SECTION_START = re.compile(rf"^##\s+{re.escape(SECTION)}\s*$")
_SECTION_END = re.compile(r"^#{1,2}\s")
_SEPARATOR = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_TASK_ID = re.compile(r"^T-\d{2}$")
_AC_ID = re.compile(r"^AC-\d{2,3}$")
_AC_DECLARED = re.compile(r"\*\*(AC-\d{2,3})\*\*")
_CODE_SPAN = re.compile(r"`([^`]*)`")
_WILDCARD = re.compile(r"[*?]")
_WAVE = re.compile(r"^[0-9]+$")

_STR_LISTS = ("files", "criteria", "decisions", "deviations", "questions")
_FIELDS = {"task", "status", "tests", *_STR_LISTS}


@dataclass(frozen=True)
class Task:
    """One row of a work plan."""

    id: str
    wave: int
    files: tuple[str, ...]
    criteria: tuple[str, ...]
    line: int
    model: str = ""  # declared in the plan; "" = take models.task (SPEC-0002)

    def effective_model(self, default: str) -> str:
        return self.model or default

    def allows(self, path: str) -> bool:
        """True when ``path`` is one of the task's files or matches one of its globs."""
        return any(path == p or globs.match(path, p) for p in self.files)


@dataclass(frozen=True)
class Problem:
    """A plan error located at a line of the spec (0 = the spec as a whole)."""

    line: int
    message: str


@dataclass(frozen=True)
class Manifest:
    """A validated task manifest."""

    source: str
    task: str
    status: str
    files: tuple[str, ...]
    criteria: tuple[str, ...]
    tests: tuple[tuple[str, str], ...]
    deviations: tuple[str, ...]
    questions: tuple[str, ...]
    digest: str  # SHA-256 of the manifest file: identifies one attempt in the metrics


# -- plan -------------------------------------------------------------------

def _section(text: str) -> tuple[int, list[tuple[int, str]]] | None:
    """Heading line and body lines of the plan section, or None when absent.

    Headings inside code fences do not open or close the section.
    """
    heading: int | None = None
    lines: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        is_fence = bool(_FENCE.match(line))
        if is_fence:
            in_fence = not in_fence
        is_prose = not (in_fence or is_fence)
        if heading is None:
            if is_prose and _SECTION_START.match(line):
                heading = lineno
            continue
        if is_prose and _SECTION_END.match(line):
            break
        lines.append((lineno, line))
    return None if heading is None else (heading, lines)


def has_plan(text: str) -> bool:
    return _section(text) is not None


def _cells(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [c.strip() for c in body.split("|")]


def valid_path(path: str) -> bool:
    """Normalised relative POSIX path (or glob) that stays inside the repository.

    ``./a``, ``a//b`` or ``a/`` are rejected rather than normalised: two
    spellings of one file would defeat the overlap check.
    """
    parts = path.split("/")
    return bool(path) and "\\" not in path and all(p not in ("", ".", "..") for p in parts)


def _parse_files(cell: str, line: int, problems: list[Problem]) -> tuple[str, ...]:
    items = [s.strip() for s in _CODE_SPAN.findall(cell)]
    rest = _CODE_SPAN.sub("", cell)
    if rest.replace(",", "").strip():
        problems.append(Problem(line, "la columna Ficheros solo admite rutas entre comillas invertidas separadas por comas"))
    if not items:
        problems.append(Problem(line, "la tarea no declara ficheros"))
    for item in items:
        if not valid_path(item):
            problems.append(Problem(line, f"ruta no permitida (vacía, absoluta, con '..' o sin normalizar): '{item}'"))
    return tuple(items)


def _parse_rows(rows: list[tuple[int, str]], width: int, problems: list[Problem]) -> list[Task]:
    tasks: list[Task] = []
    for lineno, line in rows:
        cells = _cells(line)
        if len(cells) != width:
            problems.append(Problem(lineno, f"la fila tiene {len(cells)} columnas y deben ser {width}"))
            continue
        task_id, wave_raw, files_raw, criteria_raw = cells[:4]
        model = cells[4] if width > 4 else ""
        if not _TASK_ID.match(task_id):
            problems.append(Problem(lineno, f"ID de tarea inválido: '{task_id}' (formato T-NN)"))
        wave = int(wave_raw) if _WAVE.match(wave_raw) else 0
        if wave < 1:
            problems.append(Problem(lineno, f"oleada inválida: '{wave_raw}' (entero ≥ 1)"))
        files = _parse_files(files_raw, lineno, problems)
        criteria = tuple(c.strip() for c in criteria_raw.split(",") if c.strip())
        if not criteria:
            problems.append(Problem(lineno, "la tarea no declara criterios"))
        for c in criteria:
            if not _AC_ID.match(c):
                problems.append(Problem(lineno, f"criterio inválido: '{c}' (formato AC-NN)"))
        tasks.append(Task(task_id, wave, files, criteria, lineno, model))
    return tasks


def parse(text: str) -> tuple[list[Task], list[Problem]]:
    """Parse the plan section of a spec.

    Returns:
        The tasks and the format problems. No section = no tasks, no problems.
    """
    section = _section(text)
    if section is None:
        return [], []
    heading, body = section
    problems: list[Problem] = []
    table = [(n, l) for n, l in body if l.strip()]
    start = next((i for i, (_, l) in enumerate(table) if l.lstrip().startswith("|")), None)
    if start is None:
        return [], [Problem(heading, "la sección Plan de trabajo no tiene tabla")]
    header_line, header = table[start]
    columns = _cells(header)
    if columns not in (COLUMNS, [*COLUMNS, MODEL_COLUMN]):
        problems.append(Problem(header_line, f"cabecera inválida: debe ser | {' | '.join(COLUMNS)} | "
                                             f"(opcionalmente con | {MODEL_COLUMN} | al final)"))
        return [], problems
    rows = []
    for lineno, line in table[start + 1:]:
        if not line.lstrip().startswith("|"):
            break
        rows.append((lineno, line))
    if not rows or not _SEPARATOR.match(rows[0][1]):
        problems.append(Problem(header_line, "falta la fila separadora de la tabla"))
        return [], problems
    tasks = _parse_rows(rows[1:], len(columns), problems)
    if not tasks:
        problems.append(Problem(header_line, "el plan no tiene tareas"))
    return tasks, problems


def _prefix(pattern: str) -> str:
    m = _WILDCARD.search(pattern)
    return pattern if m is None else pattern[:m.start()]


def overlaps(a: str, b: str) -> bool:
    """Whether two plan entries may designate the same file (conservative)."""
    a_glob, b_glob = bool(_WILDCARD.search(a)), bool(_WILDCARD.search(b))
    if not a_glob and not b_glob:
        return a == b
    if not a_glob:
        return globs.match(a, b)
    if not b_glob:
        return globs.match(b, a)
    pa, pb = _prefix(a), _prefix(b)
    return pa.startswith(pb) or pb.startswith(pa)


def declared_criteria(text: str) -> list[str]:
    """Acceptance criteria declared in the spec (``**AC-NN**``)."""
    return list(dict.fromkeys(_AC_DECLARED.findall(text)))


def check(text: str, ladder: Sequence[str] = DEFAULT_LADDER) -> tuple[list[Task], list[Problem]]:
    """Parse and validate the plan of a spec against its own criteria and the model ladder."""
    tasks, problems = parse(text)
    if not tasks:
        return tasks, problems
    for t in tasks:
        if t.model and t.model not in ladder:
            problems.append(Problem(t.line, f"{t.id}: modelo '{t.model}' fuera de models.ladder ({', '.join(ladder)})"))
    if len(tasks) > MAX_TASKS:
        problems.append(Problem(tasks[MAX_TASKS].line, f"el plan tiene {len(tasks)} tareas (máximo {MAX_TASKS})"))
    seen: dict[str, Task] = {}
    for t in tasks:
        if t.id in seen:
            problems.append(Problem(t.line, f"{t.id} repetida (primera en la línea {seen[t.id].line})"))
        else:
            seen[t.id] = t
    declared = declared_criteria(text)
    assigned = {c for t in tasks for c in t.criteria}
    for t in tasks:
        for c in t.criteria:
            if _AC_ID.match(c) and c not in declared:
                problems.append(Problem(t.line, f"{t.id} asigna {c}, que la spec no declara"))
    for c in declared:
        if c not in assigned:
            problems.append(Problem(0, f"{c} no está asignado a ninguna tarea del plan"))
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            if a.wave != b.wave or a.id == b.id:
                continue
            for fa in a.files:
                for fb in b.files:
                    if overlaps(fa, fb):
                        problems.append(Problem(b.line, f"{a.id} y {b.id} (oleada {a.wave}) pueden tocar el mismo "
                                                        f"fichero: '{fa}' / '{fb}'"))
    return tasks, problems


def next_model(ladder: Sequence[str], current: str) -> str:
    """Model for the retry: one step up the ladder, or the top step again."""
    index = list(ladder).index(current)
    return ladder[min(index + 1, len(ladder) - 1)]


def waves(tasks: list[Task]) -> dict[int, list[Task]]:
    out: dict[int, list[Task]] = {}
    for t in sorted(tasks, key=lambda t: (t.wave, t.id)):
        out.setdefault(t.wave, []).append(t)
    return out


# -- manifests --------------------------------------------------------------

def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def load_manifest(path: Path) -> tuple[Manifest | None, list[str]]:
    """Read and validate one manifest file.

    Returns:
        The manifest (None when invalid) and every validation error.
    """
    src = str(path)
    try:
        size = path.stat().st_size
    except OSError:
        return None, [f"{src}: no existe o no se puede leer"]
    if size > MAX_MANIFEST_BYTES:
        return None, [f"{src}: ocupa {size} bytes (máximo {MAX_MANIFEST_BYTES})"]
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"{src}: no es JSON válido ({exc})"]
    except OSError as exc:
        return None, [f"{src}: no se puede leer ({exc})"]
    if not isinstance(data, dict):
        return None, [f"{src}: debe ser un objeto JSON"]
    errors = [f"{src}: falta el campo '{k}'" for k in sorted(_FIELDS - data.keys())]
    errors += [f"{src}: campo no permitido '{k}'" for k in sorted(data.keys() - _FIELDS)]
    if errors:
        return None, errors
    if not isinstance(data["task"], str) or not _TASK_ID.match(data["task"]):
        errors.append(f"{src}: 'task' debe ser un ID T-NN")
    if data["status"] not in STATUSES:
        errors.append(f"{src}: 'status' debe ser uno de {', '.join(STATUSES)}")
    for key in _STR_LISTS:
        if not _is_str_list(data[key]):
            errors.append(f"{src}: '{key}' debe ser una lista de cadenas")
    if _is_str_list(data["files"]):
        errors += [f"{src}: ruta no permitida en 'files': '{f}'" for f in data["files"] if not valid_path(f)]
    tests = data["tests"]
    valid_tests = isinstance(tests, list) and all(
        isinstance(t, dict) and set(t) == {"name", "result"} and isinstance(t["name"], str)
        and t["name"] and t["result"] in TEST_RESULTS for t in tests)
    if not valid_tests:
        errors.append(f"{src}: 'tests' debe ser una lista de {{\"name\": …, \"result\": \"pass\" | \"fail\"}}")
    if errors:
        return None, errors
    return Manifest(source=src, task=data["task"], status=data["status"],
                    files=tuple(data["files"]),
                    criteria=tuple(data["criteria"]),
                    tests=tuple((t["name"], t["result"]) for t in tests),
                    deviations=tuple(data["deviations"]), questions=tuple(data["questions"]),
                    digest=hashlib.sha256(raw).hexdigest()), []


@dataclass(frozen=True)
class WaveResult:
    """Outcome of :func:`verify_wave`.

    ``outcomes`` maps every task of the wave to ``(outcome, manifest digest)``;
    the wave is accepted only when ``errors`` is empty.
    """

    errors: list[str]
    warnings: list[str]
    outcomes: dict[str, tuple[str, str]]


def _task_errors(task: Task, m: Manifest, changed: set[str]) -> list[str]:
    errors: list[str] = []
    if m.status == "done":
        if m.questions:
            errors.append(f"{task.id}: 'done' con preguntas abiertas: {'; '.join(m.questions)}")
        missing = [c for c in task.criteria if c not in m.criteria]
        extra = [c for c in m.criteria if c not in task.criteria]
        if missing:
            errors.append(f"{task.id}: no cubre {', '.join(missing)}")
        if extra:
            errors.append(f"{task.id}: declara criterios ajenos a la tarea: {', '.join(extra)}")
        if not m.tests:
            errors.append(f"{task.id}: no informa de ningún test")
        failing = [name for name, result in m.tests if result == "fail"]
        if failing:
            errors.append(f"{task.id}: tests en rojo: {', '.join(failing)}")
    for f in m.files:
        if not task.allows(f):
            errors.append(f"{task.id}: '{f}' está fuera de los ficheros de la tarea")
        if f not in changed:
            errors.append(f"{task.id}: declara '{f}', que no tiene cambios")
    return errors


def verify_wave(tasks: list[Task], wave: int, manifests: list[Manifest], changed: set[str]) -> WaveResult:
    """Compare the manifests of ``wave`` with the plan and the real changes.

    Args:
        tasks: Valid plan tasks.
        wave: Wave being closed.
        manifests: Valid manifests passed by the caller.
        changed: Files changed in the working tree with respect to HEAD.
    """
    in_wave = {t.id: t for t in tasks if t.wave == wave}
    if not in_wave:
        return WaveResult([f"El plan no tiene oleada {wave}."], [], {})
    errors: list[str] = []
    warnings: list[str] = []
    outcomes: dict[str, tuple[str, str]] = {}
    by_task: dict[str, Manifest] = {}
    for m in manifests:
        if m.task not in in_wave:
            errors.append(f"{m.source}: {m.task} no pertenece a la oleada {wave}")
        elif m.task in by_task:
            errors.append(f"{m.source}: manifiesto duplicado de {m.task} (ya en {by_task[m.task].source})")
        else:
            by_task[m.task] = m

    for task_id, task in sorted(in_wave.items()):
        m = by_task.get(task_id)
        if m is None:
            errors.append(f"{task_id} no ejecutada: no hay manifiesto válido")
            outcomes[task_id] = ("not_run", "")
            continue
        own = _task_errors(task, m, changed)
        if m.status != "done":
            own.insert(0, f"{task_id} no completada (status: {m.status})")
            outcomes[task_id] = ("not_completed", m.digest)
        else:
            outcomes[task_id] = ("rejected" if own else "ok", m.digest)
        errors += own
        warnings += [f"{task_id} desvío: {d}" for d in m.deviations]

    claimed = {f for m in by_task.values() for f in m.files}
    errors += [f"cambio que ningún manifiesto declara: '{f}'" for f in sorted(changed - claimed)]
    return WaveResult(errors, warnings, outcomes)


# -- metrics ----------------------------------------------------------------

@dataclass(frozen=True)
class ModelStats:
    """Attempts of one model aggregated from ``plan.task`` trace events."""

    model: str
    attempts: int
    ok: int

    @property
    def failed(self) -> int:
        return self.attempts - self.ok

    @property
    def ok_rate(self) -> float:
        return 100.0 * self.ok / self.attempts if self.attempts else 0.0


_EVENT_KEYS = ("spec", "task", "model", "result", "manifest")


def stats(lines: list[str], spec: str | None = None) -> tuple[list[ModelStats], int]:
    """Aggregate ``plan.task`` events per model (SPEC-0002).

    One attempt is ``(spec, task, model, manifest digest)``: verifying the same
    attempt again only updates its result. Lines that are not JSON objects are
    counted as unreadable; well-formed events of other kinds are ignored.

    Returns:
        Per-model stats (in order of first appearance) and the unreadable line count.
    """
    attempts: dict[tuple[str, ...], str] = {}
    unreadable = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            unreadable += 1
            continue
        if not isinstance(event, dict):
            unreadable += 1
            continue
        if event.get("event") != "plan.task":
            continue
        if not all(isinstance(event.get(k), str) for k in _EVENT_KEYS) or event["result"] not in OUTCOMES:
            unreadable += 1
            continue
        if spec and event["spec"] != spec:
            continue
        attempts[tuple(event[k] for k in ("spec", "task", "model", "manifest"))] = event["result"]
    per_model: dict[str, list[int]] = {}
    for (_, _, model, _), result in attempts.items():
        counts = per_model.setdefault(model, [0, 0])
        counts[0] += 1
        counts[1] += result == "ok"
    return [ModelStats(m, a, ok) for m, (a, ok) in per_model.items()], unreadable
