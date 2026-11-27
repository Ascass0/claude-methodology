"""Compact document format checks (ADR-0014, SPEC-0018): EARS criteria, ADR fields, failure-mode IDs.

Pure functions over text and a ``Vocabulary``: no file or git access, so they test without a repository.
A document opts in with the header line ``- Formato: compacto`` (``- Format: compact``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .lang import Vocabulary

AC_LINE = re.compile(r"\*\*(AC-\d{2,3})\*\*(?:\s*\[[A-Z]+\])?\s*:\s*(.*)")
FM_ID = re.compile(r"FM-\d{2,3}")
_FM_ROW = re.compile(r"^\s*\|\s*(FM-\d{2,3})\s*\|")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Problem:
    line: int
    message: str


def is_compact(text: str, vocab: Vocabulary) -> bool:
    """Whether the document declares the compact format in its header."""
    marker = re.compile(rf"^-\s*{re.escape(vocab.format_label)}:\s*{re.escape(vocab.compact)}\s*$",
                        re.IGNORECASE | re.MULTILINE)
    return marker.search(text) is not None


def ears_problem(criterion: str, vocab: Vocabulary) -> str | None:
    """Why ``criterion`` (text after ``**AC-NN**:``) breaks every EARS pattern, or None if it follows one."""
    k = vocab.ears
    must = "(?:" + "|".join(k.must) + ")"
    opening = f"(?:{k.when}|{k.while_}|{k.if_})"
    if re.match(rf"(?:{k.when}|{k.while_})\s+.+?,\s+.*\b{must}\b", criterion):
        return None
    if re.match(rf"{k.if_}\s+.+?,\s*{k.then}\s+.*\b{must}\b", criterion):
        return None
    if not re.match(rf"{opening}\b", criterion) and re.search(rf"\b{must}\b", criterion):
        return None
    return (f"no sigue ningún patrón EARS ({k.when} …, … {k.must[0]} …; {k.if_} …, {k.then} … {k.must[0]} …; "
            f"{k.while_} …, … {k.must[0]} …; o «sistema {k.must[0]} respuesta»)")


def criteria_problems(text: str, vocab: Vocabulary) -> list[Problem]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if m := AC_LINE.search(line):
            if msg := ears_problem(m.group(2).strip(), vocab):
                out.append(Problem(lineno, f"{m.group(1)} {msg}"))
    return out


def adr_problems(text: str, vocab: Vocabulary) -> list[Problem]:
    """Missing required ADR fields (level-2 headings)."""
    found = {m.group(2).strip().lower() for line in text.splitlines() if (m := _HEADING.match(line)) and len(m.group(1)) == 2}
    return [Problem(1, f"falta el campo «{f}» del ADR") for f in vocab.adr_fields if f.lower() not in found]


def failure_modes(text: str, vocab: Vocabulary) -> tuple[list[tuple[str, int]], list[Problem]]:
    """``FM-NN`` rows of the spec as ``(id, line)``, plus rows of the failure table that have no ID."""
    defs = [(m.group(1), n) for n, line in enumerate(text.splitlines(), 1) if (m := _FM_ROW.match(line))]
    problems: list[Problem] = []
    in_section = in_fence = False
    header_seen = False
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
        if in_fence:
            continue
        if h := _HEADING.match(line):
            in_section = len(h.group(1)) == 2 and h.group(2).strip().lower() == vocab.failure_section.lower()
            header_seen = False
            continue
        if not (in_section and line.lstrip().startswith("|")):
            continue
        first = line.strip().strip("|").split("|")[0].strip()
        if not header_seen:
            header_seen = True  # column titles
        elif set(first) <= set("-: "):
            continue  # separator
        elif not FM_ID.fullmatch(first):
            problems.append(Problem(n, f"fila de modos de fallo sin ID FM-NN: «{first or '(vacío)'}»"))
    return defs, problems


def duplicate_failure_modes(defs: list[tuple[str, int]]) -> list[Problem]:
    seen: dict[str, int] = {}
    out = []
    for ident, line in defs:
        if ident in seen:
            out.append(Problem(line, f"{ident} definido dos veces (primera definición en la línea {seen[ident]})"))
        seen.setdefault(ident, line)
    return out


def local_failure_refs(text: str, defs: list[tuple[str, int]], spec_id_pattern: str) -> list[Problem]:
    """Bare ``FM-NN`` references (not definition rows, not ``SPEC-NNNN/FM-NN``) to a mode the spec lacks."""
    known = {i for i, _ in defs}
    qualified = re.compile(rf"(?:{spec_id_pattern})/$")
    out = []
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
        if in_fence or _FM_ROW.match(line):
            continue
        for m in FM_ID.finditer(line):
            before = line[:m.start()]
            if m.start() and (before[-1:].isalnum() or before[-1:] in "-_"):
                continue
            if not qualified.search(before) and m.group(0) not in known:
                out.append(Problem(n, f"referencia a {m.group(0)}, que la spec no define"))
    return out


def security_problems(text: str, vocab: Vocabulary) -> list[Problem]:
    """A declared security surface (header other than «none») needs at least one tagged criterion (SPEC-0026)."""
    header = re.search(rf"^-\s*{re.escape(vocab.security_label)}:[ \t]*(.*?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if header is None or header.group(1).strip().lower() == vocab.security_none.lower():
        return []
    tagged = re.compile(rf"\*\*AC-\d{{2,3}}\*\*\s*\[{re.escape(vocab.security_tag)}\]\s*:\s*(.*)")
    if any((m := tagged.search(line)) and ears_problem(m.group(1).strip(), vocab) is None for line in text.splitlines()):
        return []
    line = text[:header.start()].count("\n") + 1
    return [Problem(line, f"la spec declara superficie de seguridad y no tiene ningún criterio «**AC-NN** [{vocab.security_tag}]»")]
