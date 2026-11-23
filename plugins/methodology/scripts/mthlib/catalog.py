"""Agent catalog: deterministic rendering of the templates in ``catalog/`` (SPEC-0012, ADR-0008).

Input: an agent template (``catalog/<agent>/``), the repository configuration and the
agent variables (``[agents.<agent>]`` over the defaults of its ``meta.toml``). Output: the
agent ``.md`` and its rendered guard. No language model is involved: the same input always
produces the same bytes.

Template syntax:
  {{config.<dotted.key>}}   value from methodology.toml
  {{vars.<name>}}           agent variable
  {{agent.name}} / {{agent.version}}
  {{> <fragment>}}          includes catalog/_shared/<fragment>.md
An unknown variable is an error (fail-fast), never a silent empty string.
"""
from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MthError

CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog"
LOCAL_BEGIN = "<!-- mth:local:begin -->"
LOCAL_END = "<!-- mth:local:end -->"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
KINDS = ("revisor", "trabajador", "principal")

_VAR = re.compile(r"\{\{\s*([a-z_]+(?:\.[A-Za-z0-9_\-]+)+)\s*\}\}")
_PARTIAL = re.compile(r"\{\{>\s*([a-z0-9\-]+)\s*\}\}")
_LOCAL = re.compile(re.escape(LOCAL_BEGIN) + r"(.*?)" + re.escape(LOCAL_END), re.S)
_HEADER = re.compile(r"^<!-- mth:template (\S+)@(\S+) sha256=([0-9a-f]{64}) -->\n", re.M)
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


class TemplateError(MthError):
    """The template or its data cannot be rendered: abort without writing anything."""


@dataclass(frozen=True)
class Rendered:
    """A rendered agent, ready to be written to the repository."""

    name: str
    version: str
    agent_md: str
    guard_toml: str
    digest: str
    review: dict[str, Any] | None  # {"order", "branches", "paths"} for reviewers


@dataclass(frozen=True)
class Installed:
    """Template origin of an installed agent, read from its header."""

    name: str
    version: str
    edited: bool  # the generated part no longer matches the header hash


def names(catalog: Path) -> list[str]:
    """Agent names of the catalog, sorted."""
    return sorted(p.name for p in catalog.iterdir() if p.is_dir() and not p.name.startswith("_"))


def profiles(catalog: Path) -> dict[str, dict[str, Any]]:
    """``profiles.toml``: profile name → {description, agents}."""
    return tomllib.loads((catalog / "profiles.toml").read_text(encoding="utf-8"))


def load_meta(catalog: Path, name: str) -> dict[str, Any]:
    """``meta.toml`` of an agent.

    Raises:
        MthError: The agent is not in the catalog.
    """
    if not NAME.match(name) or not (catalog / name / "meta.toml").is_file():
        raise MthError(f"El agente '{name}' no está en el catálogo.",
                       hint="Consulta los disponibles con `mth agents list`.")
    return tomllib.loads((catalog / name / "meta.toml").read_text(encoding="utf-8"))


def frontmatter(text: str) -> dict[str, str]:
    """Top-level ``key: value`` pairs of a markdown frontmatter (quotes stripped).

    Raises:
        TemplateError: The text has no frontmatter.
    """
    m = _FRONTMATTER.match(text)
    if not m:
        raise TemplateError("La plantilla no tiene frontmatter.")
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and re.fullmatch(r"[a-zA-Z_]+", key):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            out[key] = value
    return out


def tools_of(agent_md: str) -> set[str]:
    """Tools declared in an agent's frontmatter."""
    return {t.strip() for t in frontmatter(agent_md).get("tools", "").split(",") if t.strip()}


def _lookup(ctx: dict[str, Any], dotted: str) -> Any:
    cur: Any = ctx
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise TemplateError(f"Variable inexistente en la plantilla: {{{{{dotted}}}}}.")
        cur = cur[part]
    return cur


def _fmt_md(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"`{k}`" for k in value) or "(ninguna)"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "(ninguno)"
    if value == "":
        return "(sin configurar)"
    return str(value)


def _subst(text: str, ctx: dict[str, Any], fmt) -> str:
    return _VAR.sub(lambda m: fmt(_lookup(ctx, m.group(1))), text)


def _partials(text: str, shared: Path) -> str:
    def include(m: re.Match[str]) -> str:
        path = shared / f"{m.group(1)}.md"
        if not path.is_file():
            raise TemplateError(f"Fragmento inexistente: {path.name}.")
        return path.read_text(encoding="utf-8").rstrip("\n")
    return _PARTIAL.sub(include, text)


def merged_vars(meta: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Agent variables: ``[vars]`` defaults overridden by ``[agents.<agent>]``."""
    out = dict(meta.get("vars", {}))
    out.update(config.get("agents", {}).get(meta["name"], {}))
    return out


def missing_requirements(meta: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Unmet requirements as dotted keys. A non-empty list prevents installing the agent."""
    missing = []
    for key in meta.get("requires", {}).get("config", []):
        try:
            value = _lookup({"config": config}, f"config.{key}")
        except TemplateError:
            value = None
        if value in (None, "", [], {}):
            missing.append(key)
    variables = merged_vars(meta, config)
    for key in meta.get("requires", {}).get("vars", []):
        if variables.get(key) in (None, "", [], {}):
            missing.append(f"agents.{meta['name']}.{key}")
    return missing


def validate_vars(agents: dict[str, Any], catalog: Path) -> None:
    """Check ``[agents.*]``: known agents, known variables, same type as the default.

    Raises:
        MthError: Names the offending key (SPEC-0012/AC-19).
    """
    for name, table in agents.items():
        if not isinstance(table, dict):
            raise MthError(f"'agents.{name}' debe ser una tabla.")
        defaults = load_meta(catalog, name).get("vars", {})
        for key, value in table.items():
            if key not in defaults:
                known = ", ".join(defaults) or "ninguna"
                raise MthError(f"Clave desconocida en la configuración: 'agents.{name}.{key}' "
                               f"(variables de {name}: {known}).")
            expected = type(defaults[key])
            if expected is float and isinstance(value, int) and not isinstance(value, bool):
                continue
            if type(value) is not expected:
                raise MthError(f"'agents.{name}.{key}' debe ser de tipo {expected.__name__}.")


def _deep_merge(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in child.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TemplateError(f"Valor no admitido en un guard: {v!r}.")


def _dump_guard(data: dict[str, Any]) -> str:
    """Canonical TOML of a guard: top-level scalars first, then one level of tables."""
    lines = [f"{k} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    if lines:
        lines.append("")
    for table, body in data.items():
        if not isinstance(body, dict):
            continue
        lines.append(f"[{table}]")
        for k, v in body.items():
            if isinstance(v, dict):
                raise TemplateError(f"Tabla anidada no admitida en un guard: {table}.{k}.")
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    return "\n".join(lines)


def _render_guard(catalog: Path, name: str, ctx: dict[str, Any]) -> str:
    path = catalog / name / "guard.toml"
    if not path.is_file():
        raise TemplateError(f"{name}: falta guard.toml (todo agente del catálogo lleva guard).")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base = data.pop("extends", None)
    if base:
        data = _deep_merge(tomllib.loads((catalog / base).read_text(encoding="utf-8")), data)

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            return _subst(v, ctx, str)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return _dump_guard(walk(data))


def _digest(agent_md: str, guard: str | None) -> str:
    blank = _LOCAL.sub(LOCAL_BEGIN + LOCAL_END, _HEADER.sub("", agent_md))
    return hashlib.sha256((blank + "\0" + (guard or "")).encode("utf-8")).hexdigest()


def render(catalog: Path, name: str, config: dict[str, Any], installed_md: str | None = None) -> Rendered:
    """Render an agent. With ``installed_md``, keep its local section.

    Raises:
        TemplateError: Unmet requirements, unknown variable or fragment, wrong number of
            local sections, missing guard.
    """
    meta = load_meta(catalog, name)
    missing = missing_requirements(meta, config)
    if missing:
        raise TemplateError(f"{name}: requisitos sin configurar: {', '.join(missing)}.",
                            hint="Añádelos a .claude/methodology.toml y vuelve a intentarlo.")
    ctx = {"config": config, "vars": merged_vars(meta, config),
           "agent": {"name": meta["name"], "version": meta["version"]}}
    text = _partials((catalog / name / "agent.md.tmpl").read_text(encoding="utf-8"), catalog / "_shared")
    text = _subst(text, ctx, _fmt_md)
    expected = 1 if meta.get("local_section") else 0
    blocks = _LOCAL.findall(text)
    if len(blocks) != expected:
        raise TemplateError(f"{name}: la plantilla debe tener {expected} sección local y tiene {len(blocks)}.")
    if installed_md and blocks:
        kept = _LOCAL.findall(installed_md)
        if len(kept) == 1:
            text = _LOCAL.sub(lambda _m: LOCAL_BEGIN + kept[0] + LOCAL_END, text)
    guard = _render_guard(catalog, name, ctx)
    digest = _digest(text, guard)
    m = _FRONTMATTER.match(text)
    if not m:
        raise TemplateError(f"{name}: la plantilla no tiene frontmatter.")
    header = f"<!-- mth:template {meta['name']}@{meta['version']} sha256={digest} -->\n"
    text = text[:m.end()] + header + text[m.end():]
    review = None
    if "review" in meta:
        r = meta["review"]
        review = {"order": r["order"], "branches": r["branches"],
                  "paths": [_subst(p, ctx, str) for p in r.get("paths", [])]}
    return Rendered(meta["name"], meta["version"], text, guard, digest, review)


def installed(agent_md: str, guard: str | None) -> Installed | None:
    """Template origin of an installed agent, or None if it does not come from the catalog."""
    m = _HEADER.search(agent_md)
    if not m:
        return None
    return Installed(m.group(1), m.group(2), _digest(agent_md, guard) != m.group(3))


def local_section(agent_md: str) -> str | None:
    """Content of the local section, or None when the agent has none."""
    blocks = _LOCAL.findall(agent_md)
    return blocks[0] if len(blocks) == 1 else None
