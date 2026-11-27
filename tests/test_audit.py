"""Baseline packs, report verification and the static auditor agent (SPEC-0027, ADR-0024)."""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import tomllib
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import audit, cli, setup  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

PLUGIN = HERE.parent / "plugins" / "methodology"
PACK = b"""id = "demo"
title = "Demo"
version = "2"
reviewed = "2026-01-31"
review_months = 6

[source]
name = "Demo"
version = "1"
url = "https://example.com/demo"

[[control]]
id = "demo.a"
title = "A"
level = "minimo"
url = "https://example.com/a"

[[control]]
id = "demo.b"
title = "B"
level = "recomendado"
url = "https://example.com/b"
"""


def pack(raw: bytes = PACK) -> audit.Pack:
    return audit.parse_pack(raw, "demo.toml")


def report(p: audit.Pack, *rows: str) -> str:
    return f"Línea base: {p.id}@{p.version} sha256={p.sha256}\n" + "\n".join(rows) + "\n"


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class PackTests(unittest.TestCase):
    def test_packs_listing_shows_every_pack_with_its_state_and_hash(self):
        # verifies: SPEC-0027/AC-01
        code, out = run("audit", "packs")
        self.assertEqual(code, 0)
        for name in ("comun", "docker", "kubernetes"):
            line = next(line for line in out.splitlines() if line.startswith(f"{name}@"))
            self.assertRegex(line, r"\d+ controles · revisado \d{4}-\d\d-\d\d · (vigente|caducado) · sha256=[0-9a-f]{64}")

    def test_an_invalid_pack_is_rejected_naming_the_pack(self):
        # verifies: SPEC-0027/AC-02
        # verifies: SPEC-0027/FM-01
        cases = {"toml": PACK + b"[", "missing field": PACK.replace(b'title = "Demo"\n', b"", 1),
                 "repeated id": PACK.replace(b'id = "demo.b"', b'id = "demo.a"'),
                 "bad level": PACK.replace(b'"recomendado"', b'"opcional"'),
                 "bad months": PACK.replace(b"review_months = 6", b"review_months = 0"),
                 "no controls": PACK.split(b"[[control]]")[0]}
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(MthError) as ctx:
                audit.parse_pack(raw, "demo.toml")
            self.assertIn("demo.toml", ctx.exception.message)

    def test_a_pack_expires_after_its_review_period_and_doctor_warns_without_blocking(self):
        # verifies: SPEC-0027/AC-03
        p = pack()
        self.assertEqual(p.expires(), date(2026, 7, 28))
        self.assertFalse(p.expired(date(2026, 7, 28)))
        self.assertTrue(p.expired(date(2026, 7, 29)))
        lines = []
        with mock.patch.object(audit, "load_packs", return_value={"demo": p}), mock.patch.object(setup, "date") as today:
            today.today.return_value = date(2027, 1, 1)
            setup._doctor_packs(lambda ok, msg, blocking=True: lines.append((ok, msg, blocking)))
        self.assertEqual([(ok, blocking) for ok, _, blocking in lines], [(False, False)])
        self.assertIn("demo@2", lines[0][1])


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.p = pack()
        self.packs = {"demo": self.p}
        self.good = report(self.p, "- demo.a | cumple | Dockerfile:3 USER app", "- demo.b | no evaluable | herramienta ausente")

    def test_a_well_formed_report_is_accepted(self):
        # verifies: SPEC-0027/AC-04
        self.assertEqual(audit.verify_report(self.good, self.packs), [])

    def test_a_control_the_pack_does_not_define_is_rejected(self):
        # verifies: SPEC-0027/AC-05
        # verifies: SPEC-0027/FM-02
        problems = audit.verify_report(self.good + "- demo.zzz | cumple | x\n", self.packs)
        self.assertEqual(len(problems), 1)
        self.assertIn("demo.zzz no existe", problems[0])

    def test_a_missing_mandatory_control_is_rejected_but_a_missing_recommended_one_is_not(self):
        # verifies: SPEC-0027/AC-06
        # verifies: SPEC-0027/FM-03
        self.assertIn("demo.a", audit.verify_report(report(self.p, "- demo.b | no evaluable | x"), self.packs)[0])
        self.assertEqual(audit.verify_report(report(self.p, "- demo.a | no evaluable | sin Dockerfile"), self.packs), [])

    def test_bad_results_and_missing_evidence_are_rejected(self):
        # verifies: SPEC-0027/AC-07
        for row, expected in (("- demo.a | quizá | x", "resultado"), ("- demo.a | cumple | ", "evidencia"),
                              ("- demo.a | no cumple |", "evidencia")):
            with self.subTest(row=row):
                problems = audit.verify_report(report(self.p, row, "- demo.b | no evaluable | x"), self.packs)
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_a_baseline_that_does_not_match_the_pack_is_rejected(self):
        # verifies: SPEC-0027/AC-08
        # verifies: SPEC-0027/FM-04
        altered = pack(PACK.replace(b'title = "A"', b'title = "A2"'))
        problems = audit.verify_report(report(altered, "- demo.a | cumple | x"), self.packs)
        self.assertTrue(any("no coincide" in p for p in problems))
        self.assertIn("falta la línea", audit.verify_report("- demo.a | cumple | x\n", self.packs)[0])
        self.assertIn("no existe", audit.verify_report(self.good.replace("demo@", "otro@"), self.packs)[0])

    def test_a_report_never_certifies(self):
        # verifies: SPEC-0027/AC-09
        for word in ("certificado", "Certifica", "certificada"):
            with self.subTest(word):
                text = self.good + f"Resumen: sistema {word}\n"
                self.assertTrue(any("no certifica" in p for p in audit.verify_report(text, self.packs)))

    def test_the_verify_command_reports_problems_with_a_failing_code(self):
        # verifies: SPEC-0027/AC-04
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(audit, "load_packs", return_value=self.packs):
            path = Path(tmp) / "r.md"
            path.write_text(self.good, encoding="utf-8")
            self.assertEqual(run("audit", "verify", str(path))[0], 0)
            path.write_text(self.good + "- demo.q | cumple | x\n", encoding="utf-8")
            code, out = run("audit", "verify", str(path))
            self.assertEqual(code, 1)
            self.assertIn("demo.q", out)
            self.assertEqual(run("audit", "verify", str(Path(tmp) / "absent.md"))[0], 1)


class ShippedPacksTests(unittest.TestCase):
    def test_the_shipped_packs_are_valid_sourced_and_reviewed(self):
        # verifies: SPEC-0027/AC-10
        packs = audit.load_packs()
        self.assertEqual(set(packs), {"comun", "docker", "kubernetes"})
        for p in packs.values():
            with self.subTest(pack=p.id):
                self.assertTrue(p.source_url.startswith("https://"))
                self.assertTrue(p.controls)
                self.assertTrue(any(c.level == "minimo" for c in p.controls))
                for c in p.controls:
                    self.assertTrue(c.id.startswith(p.id + "."), c.id)
                    self.assertTrue(c.url.startswith("https://"), c.id)
        docker_rules = {c.rule for c in packs["docker"].controls}
        self.assertTrue(all(re.fullmatch(r"DL\d{4}", r) for r in docker_rules), docker_rules)


class AgentTests(unittest.TestCase):
    def test_the_agent_guard_is_read_only_with_offline_tools_and_one_report_directory(self):
        # verifies: SPEC-0027/AC-11
        guard = tomllib.loads((PLUGIN / "catalog/auditor-estatico/guard.toml").read_text(encoding="utf-8"))
        allowed = " ".join(guard["bash"]["allow"])
        for forbidden in ("curl", "wget", "ssh", "push", "commit", "tools install"):
            self.assertNotIn(forbidden, allowed)
        self.assertEqual(guard["write"]["allow"], [".work/security-report/**"])
        self.assertEqual(guard["bash"]["mode"], "allowlist")

    def test_the_agent_text_marks_missing_tools_as_not_evaluable_and_never_certifies(self):
        # verifies: SPEC-0027/AC-12
        text = (PLUGIN / "catalog/auditor-estatico/agent.md.tmpl").read_text(encoding="utf-8")
        self.assertIn("`no evaluable`", text)
        self.assertRegex(text, r"herramienta ausente")
        self.assertIn("Nunca escribes «certificado»", text)

    def test_skill_agent_and_readme_document_the_flow(self):
        # verifies: SPEC-0027/AC-13
        for rel in ("skills/mth-audit/SKILL.md", "catalog/auditor-estatico/agent.md.tmpl"):
            text = (PLUGIN / rel).read_text(encoding="utf-8")
            self.assertIn("mth audit verify", text, rel)
        readme = (HERE.parent / "README.md").read_text(encoding="utf-8")
        for needle in ("mth audit", "auditor-estatico", "certific"):
            self.assertIn(needle, readme)


if __name__ == "__main__":
    unittest.main()
