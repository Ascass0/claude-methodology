"""Traceability checks: IDs, markdown links and acceptance-criteria coverage.

Checks are deterministic and report every finding at once (no fail-on-first),
so a single run gives the complete list to fix.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

from . import compact, globs, plan, testlabels
from .config import Config
from .ids import IdRegistry, read_text

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_HTML_ANCHOR = re.compile(r"<a\s+(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)
_MD_LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_AC = re.compile(r"\*\*(AC-\d{2,3})\*\*")


@dataclass(frozen=True)
class Finding:
    """One traceability problem located in a file."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def github_slug(heading: str) -> str:
    """Anchor GitHub generates for a heading (lowercase, punctuation dropped)."""
    text = _MD_LINK_TEXT.sub(r"\1", heading).strip().lower()
    out = []
    for ch in text:
        if ch == " ":
            out.append("-")
        elif ch in "-_" or unicodedata.category(ch)[0] in "LN" or unicodedata.category(ch) in ("Mn", "Mc"):
            out.append(ch)
    return "".join(out)


def _anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        anchors.update(_HTML_ANCHOR.findall(line))
        if m := _HEADING.match(line):
            slug = github_slug(m.group(1))
            count = seen.get(slug, 0)
            anchors.add(slug if count == 0 else f"{slug}-{count}")
            seen[slug] = count + 1
    return anchors


def _prose_lines(text: str):
    """Yield ``(lineno, line)`` outside fenced code, with inline code removed."""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield lineno, _INLINE_CODE.sub("", line)


class Tracer:
    """Runs every enabled check over the repository files.

    Args:
        cfg: Repository configuration.
        files: Repository files (relative POSIX paths).
    """

    def __init__(self, cfg: Config, files: list[str]) -> None:
        self.cfg = cfg
        self.root = cfg.root
        self.files = [f for f in files if globs.match_any(f, cfg["trace"]["include"])
                      and not globs.match_any(f, cfg["trace"]["exclude"])]
        self._texts: dict[Path, str | None] = {}
        self.registry = IdRegistry(cfg, files, self._read)
        self._anchor_cache: dict[str, set[str]] = {}
        self._verified: dict[tuple[str, str], list[tuple[str, int]]] | None = None

    def _read(self, path: Path) -> str | None:
        """The text of ``path``, read once per run: the checks and the ID registry all go through here."""
        if path not in self._texts:
            self._texts[path] = read_text(path)
        return self._texts[path]

    def run(self) -> list[Finding]:
        findings = self._duplicates()
        texts = {f: t for f in self.files if (t := self._read(self.root / f)) is not None}
        findings += self._references(texts)
        if self.cfg["trace"]["links"]:
            findings += self._links(texts)
        if self.cfg["trace"]["acceptance"]:
            findings += self._acceptance(texts)
        findings += self._plans(texts)
        findings += self._compact(texts)
        findings += self._test_labels(texts)
        return findings

    def _test_labels(self, texts: dict[str, str]) -> list[Finding]:
        """Tests without a declared purpose (ADR-0015)."""
        patterns = self.cfg["trace"]["test_patterns"]
        spec_pattern = self.registry.kinds[self.cfg["trace"]["spec_kind"]]
        out = []
        for path, text in texts.items():
            if not globs.match_any(path, self.cfg["paths"]["tests"]):
                continue
            opening = testlabels.pattern_for(path, patterns)
            if opening is None and not testlabels.is_test_file(path):
                continue
            out += [Finding(path, p.line, p.message) for p in testlabels.file_problems(text, opening, spec_pattern)]
        return out

    def single_test(self) -> list[Finding]:
        """Acceptance criteria verified by exactly one test (a warning, never an error)."""
        texts = {f: t for f in self.files if (t := self._read(self.root / f)) is not None}
        spec_kind = self.cfg["trace"]["spec_kind"]
        specs_dir = self.cfg["paths"]["specs"].rstrip("/") + "/"
        counts = self._verifications(texts)
        out = []
        for path, text in texts.items():
            if not (path.startswith(specs_dir) and path.endswith(".md")):
                continue
            spec_id = next((i for i, places in self.registry.definitions.items()
                            if any(p == path for p, _ in places) and self.registry.kind_of(i) == spec_kind), None)
            if spec_id is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for ac in _AC.findall(line):
                    if len(counts.get((spec_id, ac), ())) == 1:
                        out.append(Finding(path, lineno, f"{spec_id}/{ac} tiene un único test"))
        return out

    def _verifications(self, texts: dict[str, str]) -> dict[tuple[str, str], list[tuple[str, int]]]:
        """Places of every ``verifies: SPEC-NNNN/AC-NN`` comment in the test files (computed once per run)."""
        if self._verified is not None:
            return self._verified
        id_re = self.registry.kinds[self.cfg["trace"]["spec_kind"]]
        verifies = re.compile(rf"verifies:\s*({id_re})/(AC-\d{{2,3}})", re.IGNORECASE)
        found: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for path, text in texts.items():
            if globs.match_any(path, self.cfg["paths"]["tests"]):
                for lineno, line in enumerate(text.splitlines(), 1):
                    for m in verifies.finditer(line):
                        found.setdefault((m.group(1), m.group(2).upper()), []).append((path, lineno))
        self._verified = found
        return found

    def _compact(self, texts: dict[str, str]) -> list[Finding]:
        """Compact-format checks (ADR-0014): only documents that declare the format, plus ``SPEC-NNNN/FM-NN`` refs."""
        vocab = self.cfg.vocab
        specs_dir = self.cfg["paths"]["specs"].rstrip("/") + "/"
        adr_dir = self.cfg["paths"]["adr"].rstrip("/") + "/"
        spec_kind, adr_kind = self.cfg["trace"]["spec_kind"], self.cfg["trace"]["adr_kind"]
        owners: dict[str, str] = {}
        for ident, places in self.registry.definitions.items():
            for path, _ in places:
                owners.setdefault(path, ident)

        def at(path: str, problems: list[compact.Problem]) -> list[Finding]:
            return [Finding(path, p.line, p.message) for p in problems]

        modes: dict[str, set[str]] = {}
        out: list[Finding] = []
        for path, text in texts.items():
            owner = owners.get(path)
            if not (path.endswith(".md") and owner):
                continue
            kind = self.registry.kind_of(owner)
            if kind == spec_kind and path.startswith(specs_dir):
                defs, untagged = compact.failure_modes(text, vocab)
                modes[owner] = {i for i, _ in defs}
                if compact.is_compact(text, vocab):
                    out += at(path, untagged + compact.duplicate_failure_modes(defs) + compact.criteria_problems(text, vocab)
                              + compact.security_problems(text, vocab)
                              + compact.local_failure_refs(text, defs, self.registry.kinds[spec_kind]))
            elif kind == adr_kind and path.startswith(adr_dir) and compact.is_compact(text, vocab):
                out += at(path, compact.adr_problems(text, vocab))
        qualified = re.compile(rf"({self.registry.kinds[spec_kind]})/(FM-\d{{2,3}})(?![\w-])")
        for path, text in texts.items():
            for lineno, line in enumerate(text.splitlines(), 1):
                for m in qualified.finditer(line):
                    if self.registry.is_defined(m.group(1)) and m.group(2) not in modes.get(m.group(1), set()):
                        out.append(Finding(path, lineno, f"referencia a {m.group(1)}/{m.group(2)}, que la spec no define"))
        return out

    def _plans(self, texts: dict[str, str]) -> list[Finding]:
        """Work-plan errors of every spec that has a plan section (SPEC-0001)."""
        specs_dir = self.cfg["paths"]["specs"].rstrip("/") + "/"
        out = []
        for path, text in texts.items():
            if path.startswith(specs_dir) and path.endswith(".md") and plan.has_plan(text):
                out += [Finding(path, p.line, f"plan de trabajo: {p.message}") for p in plan.check(text, self.cfg["models"]["ladder"], self.cfg.vocab)[1]]
        return out

    def _duplicates(self) -> list[Finding]:
        out = []
        for ident, places in sorted(self.registry.definitions.items()):
            for path, line in places[1:]:
                first = f"{places[0][0]}:{places[0][1]}"
                out.append(Finding(path, line, f"{ident} definido dos veces (primera definición en {first})"))
        return out

    def _references(self, texts: dict[str, str]) -> list[Finding]:
        out = []
        for path, text in texts.items():
            for lineno, line in enumerate(text.splitlines(), 1):
                for ident in self.registry.find(line):
                    if not self.registry.is_defined(ident):
                        out.append(Finding(path, lineno, f"referencia a {ident}, que no está definido"))
        return out

    def _links(self, texts: dict[str, str]) -> list[Finding]:
        out = []
        for path, text in texts.items():
            if not path.endswith(".md"):
                continue
            for lineno, line in _prose_lines(text):
                targets = _LINK.findall(line) + _REF_DEF.findall(line)
                for target in targets:
                    if msg := self._check_link(path, target):
                        out.append(Finding(path, lineno, msg))
        return out

    def _check_link(self, source: str, target: str) -> str | None:
        if _SCHEME.match(target) or target.startswith("//"):
            return None
        raw_path, _, anchor = target.partition("#")
        rel = unquote(raw_path)
        if rel:
            resolved = os.path.normpath(os.path.join(os.path.dirname(source), rel))
            if resolved == ".." or resolved.startswith("../") or os.path.isabs(rel):
                return f"enlace fuera del repositorio: {target}"
            if not (self.root / resolved).exists():
                return f"enlace roto: {target}"
        else:
            resolved = source
        if anchor and resolved.endswith(".md") and (self.root / resolved).is_file():
            if unquote(anchor).lower() not in self._anchors_of(resolved):
                return f"ancla inexistente: {target}"
        return None

    def _anchors_of(self, rel: str) -> set[str]:
        if rel not in self._anchor_cache:
            self._anchor_cache[rel] = _anchors(self._read(self.root / rel) or "")
        return self._anchor_cache[rel]

    def _acceptance(self, texts: dict[str, str]) -> list[Finding]:
        spec_kind = self.cfg["trace"]["spec_kind"]
        specs_dir = self.cfg["paths"]["specs"].rstrip("/") + "/"
        vocab = self.cfg.vocab
        status_re = re.compile(rf"^-\s*{re.escape(vocab.status_label)}:\s*([a-záéíóú]+)", re.IGNORECASE | re.MULTILINE)

        covered = {key: places[0] for key, places in self._verifications(texts).items()}
        out = []

        declared: set[tuple[str, str]] = set()
        for path, text in texts.items():
            if not (path.startswith(specs_dir) and path.endswith(".md")):
                continue
            spec_id = next((i for i, places in self.registry.definitions.items()
                            if any(p == path for p, _ in places)
                            and self.registry.kind_of(i) == spec_kind), None)
            if spec_id is None:
                continue
            acs = []
            for lineno, line in enumerate(text.splitlines(), 1):
                for ac in _AC.findall(line):
                    acs.append((ac, lineno))
                    declared.add((spec_id, ac))
            status = (status_re.search(text) or [None, ""])[1].lower()
            if status == vocab.implemented:
                if not acs:
                    out.append(Finding(path, 1, f"{spec_id} está implementada pero no declara criterios de aceptación"))
                for ac, lineno in acs:
                    if (spec_id, ac) not in covered:
                        out.append(Finding(path, lineno,
                                           f"{spec_id}/{ac} no tiene ningún test con 'verifies: {spec_id}/{ac}'"))
        for spec_id, ac in sorted(set(covered) - declared):
            path, lineno = covered[(spec_id, ac)]
            out.append(Finding(path, lineno, f"un test verifica {spec_id}/{ac}, que no existe en la spec"))
        return out


def partition(findings: list[Finding], legacy_files: set[str]) -> tuple[list[Finding], list[Finding]]:
    """Split findings into errors and those located in legacy files (SPEC-0005)."""
    errors = [f for f in findings if f.path not in legacy_files]
    return errors, [f for f in findings if f.path in legacy_files]


def check(cfg: Config, files: list[str]) -> list[Finding]:
    """Run all traceability checks and return the findings (empty = OK)."""
    return Tracer(cfg, files).run()
