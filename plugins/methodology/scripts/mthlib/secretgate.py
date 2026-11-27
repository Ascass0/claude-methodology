"""Secrets gate (ADR-0020, SPEC-0022): scan commits with gitleaks and report findings without values.

The tool does the detection; this module runs it, fails closed when it is missing or breaks,
never prints a secret value and removes the temporary report whatever happens.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from . import secretci, tools
from .errors import MthError
from .files import atomic_write
from .proc import run

TOOL = "gitleaks"
MODES = ("", "off", "block")
TOGGLES = ("", "off", "on")  # secrets.hook and secrets.ci (SPEC-0024)
EXIT_LEAKS = 2  # passed as --exit-code so a tool failure (1) is not read as a finding
SCAN_TIMEOUT = 600  # seconds: nothing waits forever; a timeout blocks like any other failure (SPEC-0022/AC-15)
MIN_VERSION = (8, 19, 0)  # the release that replaced `protect` and `detect` by `git` (SPEC-0024)
INSTALL_HINT = "Instálalo con `mth tools install gitleaks`, ponlo en el PATH o pon secrets.mode = \"off\"."
ACCEPT_WARNING = ("Los secretos aceptados siguen en el historial: rótalos en su servicio. "
                  "Aceptarlos no los invalida.")


@dataclass(frozen=True)
class Finding:
    rule: str
    file: str
    line: int
    commit: str

    def __str__(self) -> str:
        where = f"{self.rule} · {self.file}:{self.line}"
        return f"{where} · {self.commit[:8]}" if self.commit else where  # a staged finding has no commit yet


def validate(section: dict[str, Any]) -> None:
    """Check the ``[secrets]`` table.

    Raises:
        MthError: A value is unknown or the baseline path is empty (fail-fast).
    """
    if section["mode"] not in MODES:
        raise MthError(f"'secrets.mode' = {section['mode']!r} debe ser \"\" (sin decidir), \"off\" o \"block\".")
    for key in ("hook", "ci"):
        if section[key] not in TOGGLES:
            raise MthError(f"'secrets.{key}' = {section[key]!r} debe ser \"\" (sin decidir), \"off\" o \"on\".")
    if section["ci"] == "on":  # the baseline ends inside the workflow script (SPEC-0024/AC-11)
        secretci.check_baseline(section["baseline"])
    raw = section["baseline"].strip()
    parts = PurePath(raw).parts
    if not raw or PurePath(raw).is_absolute() or ".." in parts or (parts and parts[0] == ".git"):
        raise MthError(f"'secrets.baseline' = {section['baseline']!r} debe ser una ruta relativa dentro del repo, "
                       "sin '..' y fuera de .git/.")  # the value comes from the repo: never trust it (SPEC-0022/AC-14)


def baseline_path(root: Path, section: dict[str, Any]) -> Path:
    """The baseline file inside the repository.

    Raises:
        MthError: The path resolves (symbolic links included) outside the repository or into ``.git``.
    """
    top = root.resolve()
    path = (top / section["baseline"]).resolve()
    if not path.is_relative_to(top) or path.is_relative_to(top / ".git"):
        raise MthError(f"'secrets.baseline' = {section['baseline']!r} apunta fuera del repo o dentro de .git/.",
                       hint="Usa una ruta relativa dentro del repo.")
    return path


def resolve() -> tools.Resolved:
    """Where to run ``gitleaks`` from: the PATH if it reaches ``MIN_VERSION``, else the managed copy (SPEC-0025, ADR-0023).

    Raises:
        MthError: There is no ``gitleaks`` (with the remedy) or the managed copy was altered.
    """
    try:
        return tools.resolve(tools.tool_named(TOOL), MIN_VERSION)
    except tools.NotFound as exc:
        raise MthError(f"No se encuentra '{TOOL}': sin él no se puede comprobar que no hay secretos.", hint=INSTALL_HINT) from exc


def is_installed() -> bool:
    try:
        resolve()
    except MthError:
        return False
    return True


def parse_report(text: str) -> list[Finding]:
    """Findings of a gitleaks JSON report; the secret value is never read.

    Raises:
        MthError: The report is not a JSON list of findings.
    """
    if not text.strip():
        return []
    try:
        items = json.loads(text)
        return [Finding(str(i["RuleID"]), str(i["File"]), int(i["StartLine"]), str(i.get("Commit", ""))) for i in items]
    except (ValueError, TypeError, KeyError) as exc:
        raise MthError("El informe de gitleaks no se puede leer.",
                       hint="Actualiza gitleaks o repite el escaneo.") from exc


def scan(root: Path, rev_range: str | None, baseline: Path | None, report_copy: Path | None = None,
         staged: bool = False) -> list[Finding]:
    """Run gitleaks over a commit range, the whole history or what is staged, and return the findings.

    Args:
        root: Repository root.
        rev_range: ``git log`` range to scan, or None for the whole history.
        baseline: Accepted findings to ignore; used only if the file exists.
        report_copy: Where to store the redacted report (to write the baseline).
        staged: Scan only what is staged (``--pre-commit --staged``, SPEC-0024); ``rev_range`` is ignored.

    Raises:
        MthError: The tool is missing, fails or leaves an unreadable report.
    """
    resolved = resolve()
    with tempfile.TemporaryDirectory(prefix="mth-secrets-") as tmp:
        report = Path(tmp) / "report.json"
        args = [str(resolved.path), "git", str(root), "--redact", "--no-banner", "--exit-code", str(EXIT_LEAKS),
                "--report-format", "json", "--report-path", str(report)]
        if staged:
            args += ["--pre-commit", "--staged"]
        elif rev_range:
            args.append(f"--log-opts={rev_range}")
        if baseline is not None and baseline.is_file():
            args += ["--baseline-path", str(baseline)]
        done = run(args, cwd=root, check=False, timeout=SCAN_TIMEOUT)
        if done.returncode not in (0, EXIT_LEAKS):
            # The tool's own output is not echoed: it can quote a match before --redact applies.
            raise MthError(f"gitleaks falló (código {done.returncode}).",
                           hint="Revisa el rango de commits (un clon superficial puede no tenerlo) y repite el escaneo.")
        # gitleaks may write no report when there is nothing to report: exit 0 without one is clean.
        text = report.read_text(encoding="utf-8") if report.is_file() else ""
        found = parse_report(text)
        if done.returncode == EXIT_LEAKS and not found:
            raise MthError("gitleaks avisó de hallazgos pero no dejó informe.", hint="Repite el escaneo.")
        if report_copy is not None:  # redacted by --redact: the baseline never stores a secret value
            report_copy.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(report_copy, text if text.strip() else "[]\n")
        return found


def enforce(root: Path, section: dict[str, Any], rev_range: str | None) -> None:
    """Scan and fail on any finding outside the baseline.

    Raises:
        MthError: There are findings, or the scan could not run.
    """
    found = scan(root, rev_range, baseline_path(root, section))
    if found:
        listing = "\n".join(f"  - {f}" for f in found[:50])
        more = f"\n  … y {len(found) - 50} más" if len(found) > 50 else ""
        raise MthError(f"Secretos en el historial ({len(found)} hallazgos):\n{listing}{more}",
                       hint="Rota el secreto en su servicio y retíralo del código. Los valores no se imprimen.")


def enforce_staged(root: Path, section: dict[str, Any]) -> None:
    """Scan what is staged and fail on any finding outside the baseline (the pre-commit hook, SPEC-0024).

    Raises:
        MthError: There are findings, or the scan could not run (the commit is rejected either way).
    """
    found = scan(root, None, baseline_path(root, section), staged=True)
    if found:
        listing = "\n".join(f"  - {f}" for f in found[:50])
        raise MthError(f"Secretos en lo preparado para el commit ({len(found)} hallazgos):\n{listing}",
                       hint="Quita el secreto del cambio y rótalo si ya lo has usado. Los valores no se imprimen.")


def accept_history(root: Path, section: dict[str, Any]) -> int:
    """Write the baseline with every finding in the history and return how many there are."""
    return len(scan(root, None, None, report_copy=baseline_path(root, section)))
