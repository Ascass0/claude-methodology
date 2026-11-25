"""Repository configuration: ``.claude/methodology.toml``.

Invalid configuration is a fail-fast condition: every command refuses to run
and the error names the offending key.
"""
from __future__ import annotations

import copy
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__, catalog, forge, lang, versions, work
from .errors import MthError

CONFIG_PATH = Path(".claude") / "methodology.toml"

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "remote": "origin",
    "forge": "github",  # SPEC-0016
    "commands": {"test": None, "precommit": ""},
    "paths": {
        "docs": "docs",
        "specs": "specs/features",
        "adr": "specs/adr",
        "changes": "changes",
        "changelog": "CHANGELOG.md",
        "claude_md": "CLAUDE.md",
        "tests": ["tests/**", "test/**", "**/test_*.*", "**/*_test.*",
                  "**/*.test.*", "**/*.spec.*"],
    },
    "ids": {
        "SPEC": {"pattern": r"SPEC-\d{4}", "defined_in": ["specs/features/**/*.md"]},
        "ADR": {"pattern": r"ADR-\d{4}", "defined_in": ["specs/adr/**/*.md"]},
    },
    "branches": {"main": "main", "development": "development", "extra": {}},
    "commits": {"require_refs": ["feat", "fix", "refactor", "perf"], "external_refs": []},
    "changes": {"required_for": ["feat", "fix", "hotfix"]},
    "review": {"agents": [], "required_for": ["feat", "fix", "hotfix"], "paths": {}},
    "roles": {"coder": "", "documenter": "", "verifier": ""},
    "ci": {"required": True},
    "trace": {"links": True, "acceptance": True, "spec_kind": "SPEC",
              "adr_kind": "ADR", "include": ["**"], "exclude": [], "legacy_base": "",
              "test_patterns": {
                  "**/*.py": r"^\s*(?:async\s+)?def\s+test\w*\s*\(",
                  **{f"**/*.{ext}": r"^\s*(?:it|test)(?:\.\w+)*\s*\(" for ext in ("js", "jsx", "mjs", "cjs", "ts", "tsx")},
                  "**/*.go": r"^func\s+Test\w*\s*\(",
              }},
    "release": {"github_release": True, "sign_tags": False, "tag_prefix": "v", "version_files": []},
    "models": {"ladder": ["haiku", "sonnet", "opus"], "task": "sonnet",
               "review": "sonnet", "documenter": "sonnet"},
    "language": {"docs": "es"},
    "hooks": {"commit_msg": "own"},
    "autonomy": {"level": "full"},
    "work": {"dirs": []},
    "agents": {},
}

# Model aliases understood by Claude Code's Agent tool (ADR-0002).
MODEL_ALIASES = ("haiku", "sonnet", "opus", "fable")
MODEL_ROLES = ("task", "review", "documenter")
HOOK_MODES = ("own", "replace", "chain")  # SPEC-0006
AUTONOMY_LEVELS = ("full", "until-pr", "supervised")  # SPEC-0007

# Expected type of every leaf key. Tables not listed here are rejected.
_SCHEMA: dict[str, Any] = {
    "version": int,
    "remote": str,
    "forge": str,
    "commands": {"test": str, "precommit": str},
    "paths": {"docs": str, "specs": str, "adr": str, "changes": str,
              "changelog": str, "claude_md": str, "tests": list},
    "ids": dict,
    "branches": {"main": str, "development": str, "extra": dict},
    "commits": {"require_refs": list, "external_refs": list},
    "changes": {"required_for": list},
    "review": {"agents": list, "required_for": list, "paths": dict},
    "roles": {"coder": str, "documenter": str, "verifier": str},
    "ci": {"required": bool},
    "trace": {"links": bool, "acceptance": bool, "spec_kind": str,
              "adr_kind": str, "include": list, "exclude": list, "legacy_base": str,
              "test_patterns": dict},
    "release": {"github_release": bool, "sign_tags": bool, "tag_prefix": str, "version_files": list},
    "models": {"ladder": list, "task": str, "review": str, "documenter": str},
    "language": {"docs": str},
    "hooks": {"commit_msg": str},
    "autonomy": {"level": str},
    "work": {"dirs": list},
    "agents": dict,  # SPEC-0012: validated against the catalog metas
}

# SPEC-0009: an unknown key is usually one from a newer plugin, not a typo.
UNKNOWN_KEY_HINT = ("Si no es una errata, la clave es de una versión posterior del plugin: "
                    "actualízalo con /plugin y abre una sesión nueva de Claude Code.")

_EXTRA_NAME = re.compile(r"^[a-z]+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_TAG_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_RESERVED_KINDS = {"feat", "fix", "chore", "hotfix", "release"}


@dataclass(frozen=True)
class Config:
    """Validated configuration. ``data`` keeps the merged raw tables."""

    root: Path
    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    @property
    def remote(self) -> str:
        return self.data["remote"]

    @property
    def forge(self) -> str:
        return self.data["forge"]

    @property
    def main(self) -> str:
        return self.data["branches"]["main"]

    @property
    def development(self) -> str:
        return self.data["branches"]["development"]

    @property
    def test_command(self) -> str:
        return self.data["commands"]["test"]

    @property
    def tag_prefix(self) -> str:
        return self.data["release"]["tag_prefix"]

    @property
    def vocab(self) -> lang.Vocabulary:
        return lang.vocabulary(self.data["language"]["docs"])


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        # [ids] replaces the defaults entirely: a repo declares its own scheme.
        if key != "ids" and isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _check_types(data: dict[str, Any], schema: dict[str, Any], prefix: str) -> None:
    for key, value in data.items():
        path = f"{prefix}{key}"
        if key not in schema:
            raise MthError(f"Clave desconocida en la configuración: '{path}' "
                           f"(claude-methodology {__version__} no la reconoce).", hint=UNKNOWN_KEY_HINT)
        expected = schema[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise MthError(f"'{path}' debe ser una tabla.")
            _check_types(value, expected, path + ".")
        elif not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise MthError(f"'{path}' debe ser de tipo {expected.__name__}.")


def _check_semantics(data: dict[str, Any]) -> None:
    if data["version"] != 1:
        raise MthError(f"Versión de configuración no soportada: {data['version']}.")
    if data["commands"]["test"] is None:
        raise MthError("'commands.test' es obligatorio.",
                       hint='Usa test = "" de forma explícita si el repo aún no tiene tests.')
    if not data["ids"]:
        raise MthError("'[ids]' no puede estar vacío: la trazabilidad necesita al menos un tipo de ID.")
    for kind, spec in data["ids"].items():
        if not isinstance(spec, dict) or set(spec) != {"pattern", "defined_in"}:
            raise MthError(f"'ids.{kind}' debe tener exactamente 'pattern' y 'defined_in'.")
        try:
            re.compile(spec["pattern"])
        except re.error as exc:
            raise MthError(f"'ids.{kind}.pattern' no es una expresión regular válida: {exc}.") from exc
        if not isinstance(spec["defined_in"], list) or not spec["defined_in"]:
            raise MthError(f"'ids.{kind}.defined_in' debe ser una lista no vacía de globs.")
    for key in ("spec_kind", "adr_kind"):
        if data["trace"][key] not in data["ids"]:
            raise MthError(f"'trace.{key}' = '{data['trace'][key]}' no está definido en [ids].")
    for name, spec in data["branches"]["extra"].items():
        if not _EXTRA_NAME.match(name) or name in _RESERVED_KINDS:
            raise MthError(f"Prefijo de rama extra inválido o reservado: '{name}'.")
        if not isinstance(spec, dict) or spec.get("flow") not in ("feature", "hotfix"):
            raise MthError(f"'branches.extra.{name}.flow' debe ser 'feature' o 'hotfix'.")
    if not _TAG_PREFIX.match(data["release"]["tag_prefix"]):
        raise MthError("'release.tag_prefix' debe empezar por una letra y contener solo letras, dígitos, '.', '_' o '-'.")
    versions.validate(data["release"]["version_files"])
    work.validate(data["work"]["dirs"])
    if data["forge"] not in forge.FORGES:
        raise MthError(f"'forge' = '{data['forge']}' debe ser uno de {', '.join(forge.FORGES)}.")
    if data["hooks"]["commit_msg"] not in HOOK_MODES:
        raise MthError(f"'hooks.commit_msg' = '{data['hooks']['commit_msg']}' debe ser uno de {', '.join(HOOK_MODES)}.")
    if data["autonomy"]["level"] not in AUTONOMY_LEVELS:
        raise MthError(f"'autonomy.level' = '{data['autonomy']['level']}' debe ser uno de {', '.join(AUTONOMY_LEVELS)}.")
    legacy = data["trace"]["legacy_base"]
    if legacy and not _COMMIT.match(legacy):
        raise MthError(f"'trace.legacy_base' = '{legacy}' debe ser el hash completo de un commit (40 caracteres hexadecimales).")
    for glob, regex in data["trace"]["test_patterns"].items():
        if not isinstance(regex, str):
            raise MthError(f"'trace.test_patterns.\"{glob}\"' debe ser una expresión regular (texto) o \"\" para desactivarla.")
        try:
            re.compile(regex)
        except re.error as exc:
            raise MthError(f"'trace.test_patterns.\"{glob}\"' no es una expresión regular válida: {exc}.") from exc
    if data["language"]["docs"] not in lang.LANGUAGES:
        raise MthError(f"'language.docs' = '{data['language']['docs']}' no es un idioma admitido ({', '.join(lang.LANGUAGES)}).")
    _check_models(data["models"])
    catalog.validate_vars(data["agents"], catalog.CATALOG_DIR)
    agents = data["review"]["agents"]
    if len(set(agents)) != len(agents) or not all(isinstance(a, str) and a for a in agents):
        raise MthError("'review.agents' debe ser una lista de nombres únicos.")
    for agent, patterns in data["review"]["paths"].items():
        if agent not in agents:
            raise MthError(f"'review.paths.{agent}' no corresponde a ningún agente de review.agents.")
        if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
            raise MthError(f"'review.paths.{agent}' debe ser una lista no vacía de globs.")


def _check_models(models: dict[str, Any]) -> None:
    ladder = models["ladder"]
    if not ladder or not all(isinstance(m, str) for m in ladder) or len(set(ladder)) != len(ladder):
        raise MthError("'models.ladder' debe ser una lista no vacía de alias sin repetir.")
    unknown = [m for m in ladder if m not in MODEL_ALIASES]
    if unknown:
        raise MthError(f"'models.ladder' contiene alias desconocidos: {', '.join(unknown)}.",
                       hint=f"Alias admitidos: {', '.join(MODEL_ALIASES)}.")
    for role in MODEL_ROLES:
        if models[role] not in ladder:
            raise MthError(f"'models.{role}' = '{models[role]}' no está en models.ladder.")


def parse(root: Path, text: str, source: str = str(CONFIG_PATH)) -> Config:
    """Validate configuration text without touching the repository.

    Raises:
        MthError: TOML syntax error or invalid content.
    """
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise MthError(f"{source} no es TOML válido: {exc}.") from exc
    _check_types(raw, _SCHEMA, "")
    data = _merge(DEFAULTS, raw)
    _check_semantics(data)
    return Config(root=root, data=data)


def load(root: Path) -> Config:
    """Load and validate the repository configuration.

    Raises:
        MthError: Missing file, TOML syntax error or invalid content.
    """
    path = root / CONFIG_PATH
    if not path.is_file():
        raise MthError(f"El repositorio no ha adoptado la metodología (falta {CONFIG_PATH}).",
                       hint="Usa la skill mth-init.")
    return parse(root, path.read_text(encoding="utf-8"))
