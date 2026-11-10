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

from . import globs
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
_STATUS = re.compile(r"^-\s*Estado:\s*([a-záéíóú]+)", re.IGNORECASE | re.MULTILINE)
_AC = re.compile(r"\*\*(AC-\d{2,3})\*\*")
_IMPLEMENTED = "implementada"


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
        self.files = [f for f in files if not globs.match_any(f, cfg["trace"]["exclude"])]
        self.registry = IdRegistry(cfg, files)
        self._anchor_cache: dict[str, set[str]] = {}

    def run(self) -> list[Finding]:
        findings = self._duplicates()
        texts = {f: t for f in self.files if (t := read_text(self.root / f)) is not None}
        findings += self._references(texts)
        if self.cfg["trace"]["links"]:
            findings += self._links(texts)
        if self.cfg["trace"]["acceptance"]:
            findings += self._acceptance(texts)
        return findings

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
            self._anchor_cache[rel] = _anchors(read_text(self.root / rel) or "")
        return self._anchor_cache[rel]

    def _acceptance(self, texts: dict[str, str]) -> list[Finding]:
        spec_kind = self.cfg["trace"]["spec_kind"]
        specs_dir = self.cfg["paths"]["specs"].rstrip("/") + "/"
        id_re = self.registry.kinds[spec_kind]
        verifies = re.compile(rf"verifies:\s*({id_re})/(AC-\d{{2,3}})", re.IGNORECASE)

        covered: set[tuple[str, str]] = set()
        out = []
        for path, text in texts.items():
            if globs.match_any(path, self.cfg["paths"]["tests"]):
                for lineno, line in enumerate(text.splitlines(), 1):
                    for m in verifies.finditer(line):
                        covered.add((m.group(1), m.group(2).upper()))

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
            status = (_STATUS.search(text) or [None, ""])[1].lower()
            if status == _IMPLEMENTED:
                if not acs:
                    out.append(Finding(path, 1, f"{spec_id} está implementada pero no declara criterios de aceptación"))
                for ac, lineno in acs:
                    if (spec_id, ac) not in covered:
                        out.append(Finding(path, lineno,
                                           f"{spec_id}/{ac} no tiene ningún test con 'verifies: {spec_id}/{ac}'"))
        for spec_id, ac in sorted(covered - declared):
            out.append(Finding(self.cfg["paths"]["specs"], 0,
                               f"un test verifica {spec_id}/{ac}, que no existe en la spec"))
        return out


def check(cfg: Config, files: list[str]) -> list[Finding]:
    """Run all traceability checks and return the findings (empty = OK)."""
    return Tracer(cfg, files).run()
