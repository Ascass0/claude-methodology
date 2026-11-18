"""Interview answers → configuration and adoption ADR (SPEC-0004, ADR-0003).

Opus conducts the interview and writes the answers as JSON; this module turns
them into configuration deterministically and validates them against the
survey, so a wrong answer fails before anything is written.
"""
from __future__ import annotations

import copy
import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import lang
from .config import AUTONOMY_LEVELS, _merge
from .errors import MthError
from .survey import Survey

MAX_ANSWERS_BYTES = 256 * 1024
OTHER = "otro"
# Option → parameters: name → (type, required). Every question also accepts OTHER.
OPTIONS: dict[str, dict[str, dict[str, tuple[type, bool]]]] = {
    "alcance": {"gradual": {}, "completa": {}},
    "ramas": {"usar": {"branch": (str, True)}, "crear": {}},
    "commits": {"sustituir": {}, "encadenar": {}},
    "versiones": {"continuar": {"version_files": (list, False)},
                  "prefijo": {"tag_prefix": (str, True), "version_files": (list, False)}},
    "specs": {"mapear": {"path": (str, True), "kind": (str, True), "pattern": (str, True)},
              "convertir": {}, "archivar": {}},
    "decisiones": {"mapear": {"path": (str, True), "kind": (str, True), "pattern": (str, True)},
                   "convertir": {}, "archivar": {}},
    "tests": {"comando": {"command": (str, True)}, "ninguno": {}},
    "revisores": {"agentes": {"agents": (list, True)}},
    "colision": {"renombrar": {"renames": (dict, True)}, "mantener": {}},
    "instrucciones": {"metodologia": {}, "repo": {"exceptions": (list, True)}},
    "autonomia": {level: {} for level in AUTONOMY_LEVELS},
    "idioma": {code: {} for code in lang.LANGUAGES},
    "ci": {"sin-ci": {}, "crear": {}},
    "modelos": {"equilibrado": {}, "calidad": {}, "ahorro": {}},
}
MODEL_PRESETS = {
    "equilibrado": {"ladder": ["haiku", "sonnet", "opus"], "task": "sonnet", "review": "sonnet", "documenter": "sonnet"},
    "calidad": {"ladder": ["sonnet", "opus"], "task": "sonnet", "review": "opus", "documenter": "sonnet"},
    "ahorro": {"ladder": ["haiku", "sonnet"], "task": "haiku", "review": "sonnet", "documenter": "haiku"},
}
_KIND = re.compile(r"^[A-Z]+$")


@dataclass
class Decision:
    question: str
    option: str
    effect: str
    note: str = ""


@dataclass
class Plan:
    data: dict[str, Any]
    decisions: list[Decision] = field(default_factory=list)


def load_answers(path: Path) -> dict[str, dict[str, Any]]:
    """Read ``{"answers": {...}}``.

    Raises:
        MthError: Missing, oversized or malformed file.
    """
    try:
        if path.stat().st_size > MAX_ANSWERS_BYTES:
            raise MthError(f"{path} supera {MAX_ANSWERS_BYTES // 1024} KiB.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MthError(f"No se puede leer el fichero de respuestas {path}: {exc.strerror}.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MthError(f"{path} no es JSON válido: {exc}.") from exc
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict) or not all(isinstance(a, dict) for a in answers.values()):
        raise MthError(f'{path} debe tener la forma {{"answers": {{"<pregunta>": {{"option": "…"}}}}}}.')
    return answers


def validate(survey: Survey, answers: dict[str, dict[str, Any]]) -> None:
    """Every asked question has a valid answer and nothing else is answered.

    Raises:
        MthError: Listing every problem found.
    """
    asked = survey.asked()
    problems = [f"{q}: la pregunta no está en el inventario" for q in answers if q not in asked]
    problems += [f"{q}: falta la respuesta" for q in asked if q not in answers]
    for qid in [q for q in asked if q in answers]:
        answer = answers[qid]
        option = answer.get("option")
        if option == OTHER:
            extra = set(answer) - {"option", "config", "note"}
            if not isinstance(answer.get("config", {}), dict) or not isinstance(answer.get("note", ""), str):
                problems.append(f"{qid}: '{OTHER}' admite 'config' (tabla) y 'note' (texto)")
            elif extra:
                problems.append(f"{qid}: parámetros desconocidos: {', '.join(sorted(extra))}")
            continue
        params = OPTIONS[qid].get(option)
        if params is None:
            problems.append(f"{qid}: opción desconocida '{option}' (admitidas: {', '.join([*OPTIONS[qid], OTHER])})")
            continue
        given = set(answer) - {"option"}
        if given - set(params):
            problems.append(f"{qid}: parámetros desconocidos: {', '.join(sorted(given - set(params)))}")
        for name, (kind, required) in params.items():
            if name not in answer:
                if required:
                    problems.append(f"{qid}: '{option}' necesita '{name}'")
            elif not isinstance(answer[name], kind):
                problems.append(f"{qid}: '{name}' debe ser de tipo {kind.__name__}")
        if qid in ("specs", "decisiones") and option == "mapear" and not _KIND.match(str(answer.get("kind", ""))):
            problems.append(f"{qid}: 'kind' debe ser un prefijo en mayúsculas (por ejemplo, RFC)")
    if problems:
        raise MthError("Respuestas inválidas:\n" + "\n".join(f"  - {p}" for p in problems),
                       hint="Corrige el JSON de respuestas; las opciones están en la skill mth-init.")


def build(template: str, survey: Survey, answers: dict[str, dict[str, Any]], main: str, base: str) -> Plan:
    """Configuration (raw tables, before validation) and the decisions to record.

    Args:
        template: Text of the configuration template.
        survey: Inventory of the repository.
        answers: Validated answers.
        main: Name of the main branch on the remote.
        base: Commit where adoption starts (``trace.legacy_base`` for a gradual adoption).

    Raises:
        MthError: An answer cannot be applied (for example, unprefixed tags).
    """
    found = survey.signals
    data = tomllib.loads(template)
    data["branches"]["main"] = main
    data["ci"]["required"] = found["ci"]
    if len(found["tests"]) == 1 and "tests" not in answers:
        data["commands"]["test"] = found["tests"][0]
    plan = Plan(data)
    if survey.profile == "fork":
        data["paths"]["claude_md"] = ".claude/CLAUDE.md"
        data["commits"]["external_refs"] = [f"refs/remotes/upstream/{main}"]
        plan.decisions.append(Decision("perfil", "fork", "paths.claude_md = .claude/CLAUDE.md; "
                                       f"commits.external_refs = refs/remotes/upstream/{main}"))
    for qid in survey.asked():
        answer = answers[qid]
        option = answer["option"]
        if option == OTHER:
            plan.data = _merge(plan.data, copy.deepcopy(answer.get("config", {})))
            effect = ", ".join(sorted(_flatten(answer.get("config", {})))) or "sin cambios de configuración"
            plan.decisions.append(Decision(qid, OTHER, effect, answer.get("note", "")))
            continue
        effect = _apply(plan.data, qid, option, answer, found, base)
        note = "; ".join(answer.get("exceptions", [])) if qid == "instrucciones" else ""
        plan.decisions.append(Decision(qid, option, effect, note))
    return plan


def _apply(data: dict[str, Any], qid: str, option: str, answer: dict[str, Any],
           found: dict[str, Any], base: str) -> str:
    if qid == "alcance":
        if option == "gradual":
            data["trace"]["legacy_base"] = base
            return f"trace.legacy_base = {base[:7]}"
        return "todo el contenido cumple las reglas desde la adopción"
    if qid == "ramas":
        data["branches"]["development"] = answer.get("branch", "development")
        return f"branches.development = {data['branches']['development']}"
    if qid == "commits":
        data.setdefault("hooks", {})["commit_msg"] = "replace" if option == "sustituir" else "chain"
        return f"hooks.commit_msg = {data['hooks']['commit_msg']}"
    if qid == "versiones":
        if option == "continuar":
            tags = found["tags"]
            if tags and not tags["prefix"]:
                raise MthError("versiones: las etiquetas sin prefijo (1.2.3) no se pueden continuar.",
                               hint="Responde 'prefijo' con un tag_prefix propio.")
            data["release"]["tag_prefix"] = tags["prefix"] if tags else data["release"]["tag_prefix"]
        else:
            data["release"]["tag_prefix"] = answer["tag_prefix"]
        data["release"]["version_files"] = answer.get("version_files", [])
        files = ", ".join(v.get("path", "?") for v in data["release"]["version_files"] if isinstance(v, dict))
        return f"release.tag_prefix = {data['release']['tag_prefix']}" + (f"; version_files: {files}" if files else "")
    if qid in ("specs", "decisiones"):
        if option != "mapear":
            return "Opus " + ("convierte los documentos al formato de la metodología" if option == "convertir"
                              else "archiva los documentos previos") + " en la rama de adopción"
        path_key, kind_key, default_kind = ("specs", "spec_kind", "SPEC") if qid == "specs" else ("adr", "adr_kind", "ADR")
        kind, folder = answer["kind"], answer["path"].rstrip("/")
        data["paths"][path_key] = folder
        if kind != default_kind:
            data["ids"].pop(default_kind, None)
        data["ids"][kind] = {"pattern": answer["pattern"], "defined_in": [f"{folder}/**/*.md"]}
        data["trace"][kind_key] = kind
        return f"paths.{path_key} = {folder}; ids.{kind} = {answer['pattern']}; trace.{kind_key} = {kind}"
    if qid == "tests":
        data["commands"]["test"] = answer.get("command", "")
        return f"commands.test = {data['commands']['test'] or '(vacío)'}"
    if qid == "revisores":
        agents = data["review"]["agents"]
        agents += [a for a in answer["agents"] if isinstance(a, str) and a not in agents]
        return f"review.agents = {', '.join(agents)}"
    if qid == "colision":
        if option == "mantener":
            return "los agentes del repo sustituyen a los del plugin con el mismo nombre"
        renames = {str(k): str(v) for k, v in answer["renames"].items()}
        agents = data["review"]["agents"]
        agents += [new for new in renames.values() if new not in agents]  # the renamed agents keep reviewing
        return "Opus renombra en la rama de adopción: " + ", ".join(f"{k} → {v}" for k, v in renames.items())
    if qid == "instrucciones":
        return ("Opus retira de las instrucciones del repo lo que contradice la metodología" if option == "metodologia"
                else "prevalecen las instrucciones del repo en lo que no es innegociable")
    if qid == "autonomia":
        data.setdefault("autonomy", {})["level"] = option
        return f"autonomy.level = {option}"
    if qid == "idioma":
        data.setdefault("language", {})["docs"] = option
        return f"language.docs = {option}"
    if qid == "ci":
        data["ci"]["required"] = option == "crear"
        return "ci.required = true; Opus crea el workflow en la rama de adopción" if option == "crear" else "ci.required = false"
    if qid == "modelos":
        data["models"] = dict(MODEL_PRESETS[option])
        return f"models.ladder = {', '.join(data['models']['ladder'])}; review = {data['models']['review']}"
    raise AssertionError(f"pregunta sin efecto: {qid}")


def _flatten(table: dict[str, Any], prefix: str = "") -> list[str]:
    out = []
    for key, value in table.items():
        if isinstance(value, dict):
            out += _flatten(value, f"{prefix}{key}.")
        else:
            out.append(f"{prefix}{key}")
    return out


# -- TOML ---------------------------------------------------------------------
def dump_toml(data: dict[str, Any]) -> str:
    """Serialise the configuration (strings, booleans, integers, lists and tables)."""
    lines: list[str] = []
    _dump_table(data, [], lines)
    return "\n".join(lines).strip() + "\n"


def _dump_table(table: dict[str, Any], path: list[str], lines: list[str]) -> None:
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict) and not _is_table_array(v)}
    if path and (scalars or not any(isinstance(v, dict) or _is_table_array(v) for v in table.values())):
        lines += ["", f"[{'.'.join(_key(p) for p in path)}]"]
    lines += [f"{_key(k)} = {_value(v)}" for k, v in scalars.items()]
    for key, value in table.items():
        if isinstance(value, dict):
            _dump_table(value, [*path, key], lines)
        elif _is_table_array(value):
            for item in value:
                lines += ["", f"[[{'.'.join(_key(p) for p in [*path, key])}]]"]
                lines += [f"{_key(k)} = {_value(v)}" for k, v in item.items()]


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def _key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if "'" not in value and "\n" not in value:
            return f"'{value}'"  # literal string: regexes need no escaping
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    raise MthError(f"Valor de configuración no admitido: {value!r}.")


# -- adoption ADR -------------------------------------------------------------
_ADR_TEXT = {
    "es": {"title": "Adopción de claude-methodology", "status": "Estado", "accepted": "aceptado", "date": "Fecha",
           "category": "Categoría", "context": "Contexto", "decision": "Decisión",
           "alternatives": "Alternativas consideradas", "consequences": "Consecuencias",
           "intro": "Este repositorio adopta claude-methodology. `mth survey` lo clasificó con el perfil **{profile}**.",
           "signals": "Señales detectadas: {signals}.",
           "body": "Se adopta la metodología con estas decisiones, tomadas en la entrevista de adopción:",
           "table": "| Pregunta | Opción | Efecto | Nota |",
           "others": "Las demás opciones de cada pregunta, descritas en la skill `mth-init` de claude-methodology.",
           "legacy": "- El contenido anterior a `{base}` queda como legado: sus hallazgos de trazabilidad son avisos hasta que se modifica.",
           "strict": "- Todo el contenido del repo cumple las reglas de la metodología desde la adopción.",
           "change": "- Cambiar una decisión exige un ADR que sustituya a este."},
    "en": {"title": "Adoption of claude-methodology", "status": "Status", "accepted": "accepted", "date": "Date",
           "category": "Category", "context": "Context", "decision": "Decision",
           "alternatives": "Alternatives considered", "consequences": "Consequences",
           "intro": "This repository adopts claude-methodology. `mth survey` classified it with the **{profile}** profile.",
           "signals": "Detected signals: {signals}.",
           "body": "The methodology is adopted with these decisions, taken in the adoption interview:",
           "table": "| Question | Option | Effect | Note |",
           "others": "The other options of each question, described in the `mth-init` skill of claude-methodology.",
           "legacy": "- Content older than `{base}` is legacy: its traceability findings are warnings until it is modified.",
           "strict": "- All the repository content follows the methodology rules from adoption on.",
           "change": "- Changing a decision requires an ADR that supersedes this one."},
}


def adr_text(ident: str, survey: Survey, plan: Plan, vocab: lang.Vocabulary, today: date | None = None) -> str:
    """Adoption ADR of the target repository, in its documentation language."""
    t = _ADR_TEXT[vocab.code]
    present = [k for k, v in survey.signals.items() if v and k not in ("files", "language", "branches")]
    legacy = plan.data["trace"].get("legacy_base", "")
    rows = [f"| `{d.question}` | `{d.option}` | {_cell(d.effect)} | {_cell(d.note)} |" for d in plan.decisions]
    return "\n".join([
        f"# {ident} · {t['title']}", "",
        f"- {t['status']}: {t['accepted']}", f"- {t['date']}: {(today or date.today()).isoformat()}",
        f"- {t['category']}: methodology", "",
        f"## {t['context']}", "", t["intro"].format(profile=survey.profile), "",
        t["signals"].format(signals=", ".join(f"`{s}`" for s in present) or "—"), "",
        f"## {t['decision']}", "", t["body"], "", t["table"], "|---|---|---|---|", *rows, "",
        f"## {t['alternatives']}", "", t["others"], "",
        f"## {t['consequences']}", "",
        t["legacy"].format(base=legacy[:7]) if legacy else t["strict"], t["change"], "",
    ])


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ") or "—"
