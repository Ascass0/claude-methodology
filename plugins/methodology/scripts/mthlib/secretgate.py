"""Secrets gate (ADR-0020, SPEC-0022): scan commits with gitleaks and report findings without values.

The tool does the detection; this module runs it, fails closed when it is missing or breaks,
never prints a secret value and removes the temporary report whatever happens.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MthError
from .proc import run

TOOL = "gitleaks"
MODES = ("", "off", "block")
EXIT_LEAKS = 2  # passed as --exit-code so a tool failure (1) is not read as a finding
INSTALL_HINT = "Instala gitleaks (https://github.com/gitleaks/gitleaks#installing) o pon secrets.mode = \"off\"."
ACCEPT_WARNING = ("Los secretos aceptados siguen en el historial: rótalos en su servicio. "
                  "Aceptarlos no los invalida.")


@dataclass(frozen=True)
class Finding:
    rule: str
    file: str
    line: int
    commit: str

    def __str__(self) -> str:
        return f"{self.rule} · {self.file}:{self.line} · {self.commit[:8]}"


def validate(section: dict[str, Any]) -> None:
    """Check the ``[secrets]`` table.

    Raises:
        MthError: The mode is unknown or the baseline path is empty (fail-fast).
    """
    if section["mode"] not in MODES:
        raise MthError(f"'secrets.mode' = {section['mode']!r} debe ser \"\" (sin decidir), \"off\" o \"block\".")
    if not section["baseline"].strip():
        raise MthError("'secrets.baseline' debe ser una ruta no vacía.")


def is_installed() -> bool:
    return shutil.which(TOOL) is not None


def parse_report(text: str) -> list[Finding]:
    """Findings of a gitleaks JSON report; the secret value is never read.

    Raises:
        MthError: The report is not a JSON list of findings.
    """
    if not text.strip():
        return []
    try:
        items = json.loads(text)
        return [Finding(str(i["RuleID"]), str(i["File"]), int(i["StartLine"]), str(i["Commit"])) for i in items]
    except (ValueError, TypeError, KeyError) as exc:
        raise MthError("El informe de gitleaks no se puede leer.",
                       hint="Actualiza gitleaks o repite el escaneo.") from exc


def scan(root: Path, rev_range: str | None, baseline: Path | None, report_copy: Path | None = None) -> list[Finding]:
    """Run gitleaks over a commit range (or the whole history) and return the findings.

    Args:
        root: Repository root.
        rev_range: ``git log`` range to scan, or None for the whole history.
        baseline: Accepted findings to ignore; used only if the file exists.
        report_copy: Where to store the redacted report (to write the baseline).

    Raises:
        MthError: The tool is missing, fails or leaves an unreadable report.
    """
    if not is_installed():
        raise MthError(f"No se encuentra '{TOOL}': sin él no se puede comprobar que no hay secretos.", hint=INSTALL_HINT)
    with tempfile.TemporaryDirectory(prefix="mth-secrets-") as tmp:
        report = Path(tmp) / "report.json"
        args = [TOOL, "git", str(root), "--redact", "--no-banner", "--exit-code", str(EXIT_LEAKS),
                "--report-format", "json", "--report-path", str(report)]
        if rev_range:
            args.append(f"--log-opts={rev_range}")
        if baseline is not None and baseline.is_file():
            args += ["--baseline-path", str(baseline)]
        done = run(args, cwd=root, check=False)
        if done.returncode not in (0, EXIT_LEAKS):
            tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["sin salida"]
            raise MthError(f"gitleaks falló (código {done.returncode}): {tail[0]}",
                           hint="Revisa el rango de commits (un clon superficial puede no tenerlo) y repite.")
        text = report.read_text(encoding="utf-8") if report.is_file() else ""
        found = parse_report(text)
        if done.returncode == EXIT_LEAKS and not found:
            raise MthError("gitleaks avisó de hallazgos pero no dejó informe.", hint="Repite el escaneo.")
        if report_copy is not None:
            report_copy.parent.mkdir(parents=True, exist_ok=True)
            report_copy.write_text(text if text.strip() else "[]\n", encoding="utf-8")
        return found


def enforce(root: Path, section: dict[str, Any], rev_range: str | None) -> None:
    """Scan and fail on any finding outside the baseline.

    Raises:
        MthError: There are findings, or the scan could not run.
    """
    found = scan(root, rev_range, root / section["baseline"])
    if found:
        listing = "\n".join(f"  - {f}" for f in found[:50])
        more = f"\n  … y {len(found) - 50} más" if len(found) > 50 else ""
        raise MthError(f"Secretos en el historial ({len(found)} hallazgos):\n{listing}{more}",
                       hint="Rota el secreto en su servicio y retíralo del código. Los valores no se imprimen.")


def accept_history(root: Path, section: dict[str, Any]) -> int:
    """Write the baseline with every finding in the history and return how many there are."""
    return len(scan(root, None, None, report_copy=root / section["baseline"]))
