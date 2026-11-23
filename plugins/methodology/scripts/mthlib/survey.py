"""Deterministic inventory of a repository before adoption (SPEC-0004, ADR-0003).

It only reads. It classifies the repository in a profile and decides which
interview questions are needed: the base questions of the profile plus the
ones each detected signal triggers. An adopted repository gets the
reconfiguration inventory instead: every applicable question with its current
value (SPEC-0011, ADR-0007).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH, Config
from .errors import MthError
from .git import Git

PLUGIN_AGENTS = Path(__file__).resolve().parents[2] / "agents"
QUESTIONS = ("alcance", "ramas", "commits", "versiones", "specs", "decisiones", "tests", "revisores",
             "colision", "instrucciones", "autonomia", "idioma", "ci", "modelos")
PROFILES = ("new", "existing", "methodology", "fork")
RECONFIGURE = "reconfigure"
# Thematic blocks of the reconfiguration form (SPEC-0011): every question in exactly one.
GROUPS: dict[str, tuple[str, ...]] = {
    "flujo": ("ramas", "commits", "versiones", "ci"),
    "documentacion": ("alcance", "specs", "decisiones", "idioma", "instrucciones"),
    "calidad": ("tests", "revisores", "colision"),
    "agente": ("autonomia", "modelos"),
}
# "revisores" is always asked: it also offers the catalog agents (SPEC-0012).
BASE: dict[str, tuple[str, ...]] = {
    "new": ("revisores", "autonomia", "idioma", "modelos"),
    "existing": ("alcance", "revisores", "autonomia", "modelos"),
    "methodology": ("alcance", "revisores", "autonomia", "modelos"),
    "fork": ("alcance", "versiones", "revisores", "autonomia", "modelos"),
}
PROCESS_SIGNALS = ("specs", "adrs", "agents", "claude_dirs", "instructions", "commit_hook",
                   "hook_managers", "release_tools")

_TRIVIAL = re.compile(r"^(README[^/]*|LICENSE[^/]*|\.gitignore|\.gitattributes|\.claude/settings[^/]*\.json)$",
                      re.IGNORECASE)
_BRANCHES = ("main", "master", "development", "develop", "dev")
_SPEC_DIRS = ("specs", "spec", "rfcs", "rfc", "design", "docs/specs", "docs/rfcs", "docs/design")
_ADR_DIRS = ("adr", "adrs", "decisions", "docs/adr", "docs/adrs", "docs/decisions", "doc/adr", "specs/adr")
_HEADING_ID = re.compile(r"^#{1,6}\s+([A-Z]+)-(\d+)\b", re.MULTILINE)
_TAG = re.compile(r"^([A-Za-z][A-Za-z0-9._-]*?)?(\d+)\.(\d+)\.(\d+)$")
_SEMVER = r'(\d+\.\d+\.\d+)'
_VERSION_FILES = {
    "package.json": rf'"version":\s*"{_SEMVER}"',
    "pyproject.toml": rf'^version\s*=\s*"{_SEMVER}"',
    "Cargo.toml": rf'^version\s*=\s*"{_SEMVER}"',
}
_HOOK_MANAGERS = (".husky", "lefthook.yml", "lefthook.yaml", ".pre-commit-config.yaml")
_COMMITLINT = re.compile(r"^(commitlint\.config\.[a-z]+|\.commitlintrc.*)$")
_RELEASE_TOOLS = ("release-please-config.json", ".changeset", ".releaserc", ".releaserc.json",
                  ".releaserc.yml", "release.config.js")
_MAX_READ = 64 * 1024
_WORDS = re.compile(r"[a-záéíóúñü]+")
_STOPWORDS = {
    "es": {"el", "la", "los", "las", "que", "de", "del", "para", "con", "una", "por", "es", "se", "en", "y"},
    "en": {"the", "and", "to", "of", "is", "for", "with", "that", "this", "are", "in", "it", "be", "on"},
}
_MIN_WORDS = 40


@dataclass
class Survey:
    profile: str
    signals: dict[str, Any]
    questions: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)

    def asked(self) -> list[str]:
        return [q["id"] for q in self.questions]

    def to_json(self) -> str:
        return json.dumps({"profile": self.profile, "signals": self.signals, "questions": self.questions,
                           "warnings": self.warnings}, ensure_ascii=False, indent=2)


class _Reader:
    """Bounded reads of repository files; an unreadable file becomes a warning (SPEC-0004)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.warnings: list[str] = []

    def text(self, rel: str | Path) -> str:
        try:
            with open(self.root / rel, encoding="utf-8") as fh:
                return fh.read(_MAX_READ)
        except (OSError, UnicodeDecodeError) as exc:
            self.warnings.append(f"no se pudo leer {rel}: {exc.__class__.__name__}")
            return ""


def _id_pattern(reader: _Reader, files: list[str]) -> str | None:
    """Most frequent ``PREFIX-\\d{N}`` among the headings of ``files``."""
    found: Counter[tuple[str, int]] = Counter()
    for rel in files:
        for prefix, digits in _HEADING_ID.findall(reader.text(rel)):
            found[(prefix, len(digits))] += 1
    if not found:
        return None
    (prefix, width), _ = found.most_common(1)[0]
    return f"{prefix}-\\d{{{width}}}"


def _doc_dirs(reader: _Reader, files: list[str], candidates: tuple[str, ...],
              skip: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    out = []
    for folder in candidates:
        docs = [f for f in files if f.startswith(folder + "/") and f.endswith(".md")
                and not any(f.startswith(d + "/") for d in skip)]
        if docs:
            out.append({"path": folder, "files": len(docs), "pattern": _id_pattern(reader, docs)})
    return out


def _language(reader: _Reader, files: list[str]) -> str:
    texts = [f for f in files if f.lower() == "readme.md" or (f.startswith("docs/") and f.endswith(".md"))]
    counts = Counter()
    budget = _MAX_READ
    for rel in texts:
        if budget <= 0:
            break
        text = reader.text(rel)[:budget].lower()
        budget -= len(text)
        for word in _WORDS.findall(text):
            for code, words in _STOPWORDS.items():
                if word in words:
                    counts[code] += 1
    if sum(counts.values()) < _MIN_WORDS:
        return "unknown"
    return "es" if counts["es"] >= counts["en"] else "en"


def _tests(reader: _Reader, files: list[str]) -> list[str]:
    names = set(files)
    out = []
    if "package.json" in names:
        try:
            if json.loads(reader.text("package.json") or "{}").get("scripts", {}).get("test"):
                out.append("npm test")
        except (json.JSONDecodeError, AttributeError):
            reader.warnings.append("package.json no es JSON válido")
    pytest_config = bool({"pytest.ini", "conftest.py"} & names) or (
        "pyproject.toml" in names and "[tool.pytest" in reader.text("pyproject.toml"))
    if pytest_config or any(re.search(r"(^|/)test_[^/]*\.py$", f) for f in files):
        out.append("pytest")
    if "Makefile" in names and re.search(r"^test:", reader.text("Makefile"), re.MULTILINE):
        out.append("make test")
    if "go.mod" in names:
        out.append("go test ./...")
    if "Cargo.toml" in names:
        out.append("cargo test")
    return out


def _tags(git: Git) -> dict[str, Any] | None:
    prefixes: Counter[str] = Counter()
    for tag in git.out("tag", "--list").split():
        m = _TAG.match(tag)
        if m:
            prefixes[m.group(1) or ""] += 1
    if not prefixes:
        return None
    prefix, count = prefixes.most_common(1)[0]
    return {"prefix": prefix, "count": count}


def signals(git: Git) -> tuple[dict[str, Any], list[str]]:
    """Every signal of the repository (see the table of SPEC-0004) and the read warnings."""
    root = git.root
    reader = _Reader(root)
    files = git.files()
    names = set(files)
    top = {f.split("/", 1)[0] for f in files}
    remote_branches = set(git.remote_branches()) if git.has_remote() else set()
    plugin_agents = {p.stem for p in PLUGIN_AGENTS.glob("*.md")}
    agents = sorted(Path(f).stem for f in files if re.fullmatch(r"\.claude/agents/[^/]+\.md", f))
    hook = git.hooks_dir() / "commit-msg"
    foreign_hook = hook.is_file() and "managed-by: claude-methodology" not in reader.text(hook)
    changelog = reader.text("CHANGELOG.md") if "CHANGELOG.md" in names else None
    found: dict[str, Any] = {
        "files": sum(1 for f in files if not _TRIVIAL.match(f)),
        "branches": sorted(b for b in _BRANCHES if b in remote_branches),
        "upstream": git.ok("remote", "get-url", "upstream"),
        "tags": _tags(git),
        "specs": _doc_dirs(reader, files, _SPEC_DIRS, skip=_ADR_DIRS),
        "adrs": _doc_dirs(reader, files, _ADR_DIRS),
        "agents": agents,
        "agent_collisions": sorted(set(agents) & plugin_agents),
        "claude_dirs": sorted(d for d in (".claude/skills", ".claude/commands") if any(f.startswith(d + "/") for f in files)),
        "instructions": sorted(f for f in ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md")
                               if f in names and reader.text(f).strip()),
        "commit_hook": foreign_hook,
        "hook_managers": sorted({m for m in _HOOK_MANAGERS if m in top or m in names}
                                | {f for f in names if _COMMITLINT.match(f)}),
        "release_tools": sorted({t for t in _RELEASE_TOOLS if t in top or t in names}
                                | ({"CHANGELOG.md"} if changelog is not None and "<!-- mth:releases -->" not in changelog else set())),
        "version_files": [{"path": p, "pattern": pattern} for p, pattern in _VERSION_FILES.items()
                          if p in names and re.search(pattern, reader.text(p), re.MULTILINE)],
        "ci": any(f.startswith(".github/workflows/") for f in files),
        "tests": _tests(reader, files),
        "language": _language(reader, files),
    }
    return found, reader.warnings


def profile_of(found: dict[str, Any]) -> str:
    if found["upstream"]:
        return "fork"
    if any(found[s] for s in PROCESS_SIGNALS):
        return "methodology"
    return "new" if found["files"] == 0 else "existing"


def questions(profile: str, found: dict[str, Any]) -> list[dict[str, str]]:
    """Base questions of the profile plus those triggered by a signal, in catalogue order."""
    triggers = {
        "ramas": (None if "development" in found["branches"] or profile == "new"  # a new repo just creates it
                  else "no existe development en el remoto"),
        "commits": _evidence(found, "commit_hook", "hook_managers"),
        "versiones": _evidence(found, "tags", "release_tools", "version_files"),
        "specs": _evidence(found, "specs"),
        "decisiones": _evidence(found, "adrs"),
        "tests": (f"candidatos: {', '.join(found['tests']) or 'ninguno'}"
                  if found["files"] and len(found["tests"]) != 1 else None),
        "revisores": _evidence(found, "agents"),
        "colision": _evidence(found, "agent_collisions"),
        "instrucciones": _evidence(found, "instructions"),
        "idioma": None if found["language"] == "es" else f"idioma detectado: {found['language']}",
        "ci": None if found["ci"] else "no hay workflows en .github/workflows",
    }
    out = []
    for qid in QUESTIONS:
        reason = triggers.get(qid)
        if qid in BASE[profile]:
            out.append({"id": qid, "evidence": reason or f"base del perfil {profile}"})
        elif reason:
            out.append({"id": qid, "evidence": reason})
    return out


def _evidence(found: dict[str, Any], *keys: str) -> str | None:
    parts = [f"{k}: {json.dumps(found[k], ensure_ascii=False)}" for k in keys if found[k]]
    return "; ".join(parts) or None


def run(git: Git) -> Survey:
    """Inventory of a repository that has not adopted the methodology.

    Raises:
        MthError: The repository already has ``.claude/methodology.toml``.
    """
    if (git.root / CONFIG_PATH).exists():
        raise MthError("El repositorio ya ha adoptado la metodología.", hint="Usa `mth doctor`.")
    found, warnings = signals(git)
    profile = profile_of(found)
    return Survey(profile, found, questions(profile, found), warnings)


def select(only: str | None) -> set[str]:
    """Question IDs named by ``--only`` (IDs or block names, comma separated); every question if None.

    Raises:
        MthError: An unknown name.
    """
    if only is None:
        return set(QUESTIONS)
    chosen: set[str] = set()
    for name in (n.strip() for n in only.split(",") if n.strip()):
        if name in GROUPS:
            chosen |= set(GROUPS[name])
        elif name in QUESTIONS:
            chosen.add(name)
        else:
            raise MthError(f"--only: '{name}' no es una pregunta ni un bloque.",
                           hint=f"Bloques: {', '.join(GROUPS)}. Preguntas: {', '.join(QUESTIONS)}.")
    return chosen


def current(cfg: Config, qid: str) -> str:
    """The present value of the keys that question ``qid`` decides."""
    d = cfg.data
    spec_kind, adr_kind = d["trace"]["spec_kind"], d["trace"]["adr_kind"]
    values = {
        "alcance": f"trace.legacy_base = {d['trace']['legacy_base'][:7] or '(vacío: adopción completa)'}",
        "ramas": f"branches.development = {cfg.development}",
        "commits": f"hooks.commit_msg = {d['hooks']['commit_msg']}",
        "versiones": f"release.tag_prefix = {cfg.tag_prefix}; version_files: "
                     + (", ".join(v["path"] for v in d["release"]["version_files"]) or "ninguno"),
        "specs": f"paths.specs = {d['paths']['specs']}; ids.{spec_kind} = {d['ids'][spec_kind]['pattern']}",
        "decisiones": f"paths.adr = {d['paths']['adr']}; ids.{adr_kind} = {d['ids'][adr_kind]['pattern']}",
        "tests": f"commands.test = {cfg.test_command or '(vacío)'}",
        "revisores": f"review.agents = {', '.join(d['review']['agents']) or '(ninguno)'}",
        "colision": f"review.agents = {', '.join(d['review']['agents']) or '(ninguno)'}",
        "instrucciones": f"paths.claude_md = {d['paths']['claude_md']}",
        "autonomia": f"autonomy.level = {d['autonomy']['level']}",
        "idioma": f"language.docs = {d['language']['docs']}",
        "ci": f"ci.required = {str(d['ci']['required']).lower()}",
        "modelos": f"models.ladder = {', '.join(d['models']['ladder'])}; task = {d['models']['task']}; "
                   f"review = {d['models']['review']}",
    }
    return values[qid]


def reconfigure(git: Git, cfg: Config, only: str | None = None) -> Survey:
    """Inventory of an adopted repository: every applicable question with its current value.

    Raises:
        MthError: The repository has not adopted the methodology, ``only`` names something
            unknown or leaves no applicable question.
    """
    if not (git.root / CONFIG_PATH).exists():
        raise MthError("El repositorio no ha adoptado la metodología.", hint="Usa la skill mth-init.")
    chosen = select(only)
    found, warnings = signals(git)
    triggered = {q["id"]: q["evidence"] for q in questions("existing", found) if "base del perfil" not in q["evidence"]}
    out = []
    for qid in QUESTIONS:
        if qid not in chosen or (qid == "colision" and not found["agent_collisions"]):
            continue
        evidence = triggered.get(qid, "reestructuración")
        out.append({"id": qid, "evidence": evidence, "current": current(cfg, qid)})
    if not out:
        raise MthError("--only no deja ninguna pregunta aplicable en este repo.")
    return Survey(RECONFIGURE, found, out, warnings)
