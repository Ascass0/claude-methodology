"""Tests of verifiable delegation: work plans, task manifests and reviewer reports (SPEC-0001)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "methodology"
MTH = PLUGIN / "scripts" / "mth.py"
sys.path.insert(0, str(PLUGIN / "scripts"))

from mthlib import plan, trace  # noqa: E402
from mthlib.config import Config, DEFAULTS, _merge  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

# Fixture IDs are built at runtime so mth trace does not read them as references.
SPEC_ID = "SPEC-" + "0042"
OTHER_ID = "SPEC-" + "0043"


def spec_text(rows: str, criteria: str = "- **AC-01**: a.\n- **AC-02**: b.\n- **AC-03**: c.\n",
              header: str = "| Tarea | Oleada | Ficheros | Criterios |") -> str:
    return (f"# {SPEC_ID} · Demo\n\n- Estado: aprobada\n\n## Criterios de aceptación\n\n{criteria}\n"
            f"## Plan de trabajo\n\n{header}\n|---|---|---|---|\n{textwrap.dedent(rows).strip()}\n\n## Notas\n")


VALID_ROWS = """
    | T-01 | 1 | `src/a.py`, `tests/test_a.py` | AC-01 |
    | T-02 | 1 | `src/b/**` | AC-02 |
    | T-03 | 2 | `src/a.py` | AC-03 |
"""


def messages(text: str) -> list[str]:
    return [p.message for p in plan.check(text)[1]]


class PlanCheckTests(unittest.TestCase):
    def test_valid_plan_grouped_by_wave(self):
        # verifies: SPEC-0001/AC-01
        tasks, problems = plan.check(spec_text(VALID_ROWS))
        self.assertEqual(problems, [])
        by_wave = plan.waves(tasks)
        self.assertEqual({w: [t.id for t in ts] for w, ts in by_wave.items()}, {1: ["T-01", "T-02"], 2: ["T-03"]})
        self.assertEqual(tasks[0].files, ("src/a.py", "tests/test_a.py"))

    def test_plan_inside_code_fence_is_ignored(self):
        # verifies: SPEC-0001/AC-01
        text = "# X\n\n```markdown\n## Plan de trabajo\n| bad |\n```\n"
        self.assertFalse(plan.has_plan(text))

    def test_malformed_plans_report_their_line(self):
        # verifies: SPEC-0001/AC-02
        cases = {
            "cabecera inválida": spec_text(VALID_ROWS, header="| Tarea | Ficheros | Oleada | Criterios |"),
            "ID de tarea inválido": spec_text("| T1 | 1 | `a` | AC-01, AC-02, AC-03 |"),
            "repetida": spec_text("| T-01 | 1 | `a` | AC-01, AC-02 |\n| T-01 | 2 | `b` | AC-03 |"),
            "oleada inválida": spec_text("| T-01 | x | `a` | AC-01, AC-02, AC-03 |"),
            "oleada inválida ": spec_text("| T-01 | 0 | `a` | AC-01, AC-02, AC-03 |"),
            " oleada inválida": spec_text("| T-01 | ² | `a` | AC-01, AC-02, AC-03 |"),
            "no declara ficheros": spec_text("| T-01 | 1 |  | AC-01, AC-02, AC-03 |"),
            "comillas invertidas": spec_text("| T-01 | 1 | src/a.py | AC-01, AC-02, AC-03 |"),
            "ruta no permitida": spec_text("| T-01 | 1 | `/etc/passwd` | AC-01, AC-02, AC-03 |"),
            "ruta no permitida ": spec_text("| T-01 | 1 | `../x.py` | AC-01, AC-02, AC-03 |"),
            " ruta no permitida": spec_text("| T-01 | 1 | `./src/a.py` | AC-01, AC-02, AC-03 |"),
            "  ruta no permitida": spec_text("| T-01 | 1 | `src//a.py` | AC-01, AC-02, AC-03 |"),
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                problems = plan.check(text)[1]
                self.assertTrue(any(expected.strip() in p.message for p in problems), problems)
                self.assertTrue(all(p.line > 0 for p in problems if expected.strip() in p.message))

    def test_too_many_tasks(self):
        # verifies: SPEC-0001/AC-02
        rows = "\n".join(f"| T-{i:02d} | {i} | `f{i}` | AC-01 |" for i in range(1, 52))
        problems = plan.check(spec_text(rows, criteria="- **AC-01**: a.\n"))[1]
        self.assertTrue(any("máximo 50" in p.message and p.line > 0 for p in problems), problems)

    def test_overlap_in_same_wave(self):
        # verifies: SPEC-0001/AC-03
        cases = [
            ("`src/a.py`", "`src/a.py`"),        # exact path
            ("`src/**`", "`src/a.py`"),          # glob covers a path
            ("`src/*.py`", "`src/**/x.md`"),     # globs with compatible prefixes
        ]
        for left, right in cases:
            with self.subTest(left=left, right=right):
                rows = f"| T-01 | 1 | {left} | AC-01, AC-02 |\n| T-02 | 1 | {right} | AC-03 |"
                self.assertTrue(any("T-01 y T-02" in m and "pueden tocar el mismo fichero" in m
                                    for m in messages(spec_text(rows))))

    def test_no_overlap_across_waves_or_disjoint_globs(self):
        # verifies: SPEC-0001/AC-03
        self.assertEqual(messages(spec_text(VALID_ROWS)), [])  # src/a.py in waves 1 and 2
        rows = "| T-01 | 1 | `src/render/**` | AC-01, AC-02 |\n| T-02 | 1 | `tests/*.py` | AC-03 |"
        self.assertEqual(messages(spec_text(rows)), [])

    def test_unknown_and_unassigned_criteria(self):
        # verifies: SPEC-0001/AC-04
        found = messages(spec_text("| T-01 | 1 | `a` | AC-01, AC-09 |"))
        self.assertTrue(any("AC-09, que la spec no declara" in m for m in found), found)
        self.assertTrue(any("AC-02 no está asignado" in m for m in found), found)
        self.assertTrue(any("AC-03 no está asignado" in m for m in found), found)

    def test_complete_plan_with_a_criterion_split_across_tasks_is_accepted(self):
        # verifies: SPEC-0001/AC-04
        rows = "| T-01 | 1 | `a` | AC-01, AC-02 |\n| T-02 | 2 | `b` | AC-02, AC-03 |"
        self.assertEqual(messages(spec_text(rows)), [])


class TracePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_trace_reports_plan_errors_only_for_specs_with_plan(self):
        # verifies: SPEC-0001/AC-05
        bad = self.tmp / f"specs/features/{SPEC_ID}-demo.md"
        bad.parent.mkdir(parents=True)
        bad.write_text(spec_text("| T-01 | 1 | `a` | AC-01 |"), encoding="utf-8")
        plain = self.tmp / f"specs/features/{OTHER_ID}-plain.md"
        plain.write_text(f"# {OTHER_ID} · Plain\n\n- **AC-01**: x.\n", encoding="utf-8")
        cfg = Config(root=self.tmp, data=_merge(DEFAULTS, {"commands": {"test": ""}}))
        files = [f"specs/features/{SPEC_ID}-demo.md", f"specs/features/{OTHER_ID}-plain.md"]
        findings = [str(f) for f in trace.check(cfg, files)]
        plan_findings = [f for f in findings if "plan de trabajo" in f]
        self.assertTrue(plan_findings)
        self.assertTrue(all(f.startswith(f"specs/features/{SPEC_ID}-demo.md") for f in plan_findings))

    def test_trace_is_silent_about_a_valid_plan(self):
        # verifies: SPEC-0001/AC-05
        good = self.tmp / f"specs/features/{SPEC_ID}-demo.md"
        good.parent.mkdir(parents=True)
        good.write_text(spec_text(VALID_ROWS), encoding="utf-8")
        cfg = Config(root=self.tmp, data=_merge(DEFAULTS, {"commands": {"test": ""}}))
        findings = [str(f) for f in trace.check(cfg, [f"specs/features/{SPEC_ID}-demo.md"])]
        self.assertEqual([f for f in findings if "plan de trabajo" in f], [])


class RepoTestCase(unittest.TestCase):
    """A throwaway repository that adopted the methodology, with a committed spec that has a plan."""

    rows = """
        | T-01 | 1 | `src/a.py`, `tests/test_a.py` | AC-01 |
        | T-02 | 1 | `src/b/**` | AC-02 |
        | T-03 | 2 | `src/c.py` | AC-03 |
    """
    header = "| Tarea | Oleada | Ficheros | Criterios |"
    config = 'version = 1\n[commands]\ntest = ""\n[review]\nagents = ["verificador"]\n'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.env = {**os.environ, **GIT_ENV}
        self.git("init", "-q", "-b", "feat/demo")
        self.write(".claude/methodology.toml", self.config)
        self.write(f"specs/features/{SPEC_ID}-demo.md", spec_text(self.rows, header=self.header))
        self.write("src/a.py", "a = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def write(self, rel: str, text: str) -> Path:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def mth(self, *args, ok=True):
        proc = subprocess.run([sys.executable, str(MTH), *args], cwd=self.work, env=self.env,
                              capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode == 0, ok, out)
        return out

    def manifest(self, name: str, **fields) -> str:
        data = {"task": "T-01", "status": "done", "files": [], "criteria": [],
                "tests": [{"name": "t", "result": "pass"}], "decisions": [], "deviations": [],
                "questions": [], **fields}
        path = self.tmp / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def wave_one(self, **overrides):
        """Real changes for wave 1 plus matching manifests; overrides patch T-01's manifest."""
        self.write("src/a.py", "a = 2\n")
        self.write("tests/test_a.py", "x = 1\n")
        self.write("src/b/new.py", "b = 1\n")
        t1 = {"task": "T-01", "files": ["src/a.py", "tests/test_a.py"], "criteria": ["AC-01"], **overrides}
        return [self.manifest("t1", **t1),
                self.manifest("t2", task="T-02", files=["src/b/new.py"], criteria=["AC-02"])]

    def verify(self, manifests, ok, wave="1"):
        args = ["plan", "verify", SPEC_ID, "--wave", wave]
        for m in manifests:
            args += ["--manifest", m]
        return self.mth(*args, ok=ok)


class PlanCommandTests(RepoTestCase):
    def test_plan_check_lists_waves(self):
        # verifies: SPEC-0001/AC-01
        out = self.mth("plan", "check", SPEC_ID)
        self.assertIn("3 tareas en 2 oleadas", out)
        self.assertIn("Oleada 1: T-01 (sonnet), T-02 (sonnet)", out)
        self.assertIn("Oleada 2: T-03 (sonnet)", out)


class WaveVerifyTests(RepoTestCase):
    def test_nothing_to_verify(self):
        # unit: plan.check
        # Failure mode of SPEC-0001: spec without plan, undefined ID or missing wave.
        self.write("specs/features/" + OTHER_ID + "-plain.md", f"# {OTHER_ID} · Plain\n\n- **AC-01**: x.\n")
        self.write("specs/adr/ADR-" + "0007-x.md", "# ADR-" + "0007 · X\n")
        manifests = self.wave_one()
        cases = {
            OTHER_ID: "no tiene sección '## Plan de trabajo'",
            "SPEC-" + "0099": "no es una spec definida",
            "ADR-" + "0007": "no es una spec definida",
        }
        for spec_id, expected in cases.items():
            with self.subTest(spec_id=spec_id):
                out = self.mth("plan", "verify", spec_id, "--wave", "1", "--manifest", manifests[0], ok=False)
                self.assertIn(expected, out)
        self.assertIn("El plan no tiene oleada 7", self.verify(manifests, ok=False, wave="7"))

    def test_accepts_matching_wave(self):
        # verifies: SPEC-0001/AC-06
        out = self.verify(self.wave_one(), ok=True)
        self.assertIn(f"Oleada 1 de {SPEC_ID} verificada", out)

    def test_accepts_a_later_wave_with_a_single_task(self):
        # verifies: SPEC-0001/AC-06
        self.write("src/c.py", "c = 1\n")
        manifest = self.manifest("t3", task="T-03", files=["src/c.py"], criteria=["AC-03"])
        out = self.verify([manifest], ok=True, wave="2")
        self.assertIn(f"Oleada 2 de {SPEC_ID} verificada", out)

    def test_task_without_manifest_did_not_run(self):
        # verifies: SPEC-0001/AC-07
        manifests = self.wave_one()
        self.git("checkout", "--", "src/a.py")
        os.remove(self.work / "tests/test_a.py")
        out = self.verify(manifests[1:], ok=False)
        self.assertIn("T-01 no ejecutada", out)

    def test_blocked_or_failed_task_not_completed(self):
        # verifies: SPEC-0001/AC-07
        for status in ("blocked", "failed"):
            with self.subTest(status=status):
                out = self.verify(self.wave_one(status=status), ok=False)
                self.assertIn(f"T-01 no completada (status: {status})", out)

    def test_invalid_manifests(self):
        # verifies: SPEC-0001/AC-08
        bad_json = self.tmp / "bad.json"
        bad_json.write_text("{not json", encoding="utf-8")
        huge = self.tmp / "huge.json"
        huge.write_text(" " * (plan.MAX_MANIFEST_BYTES + 1), encoding="utf-8")
        missing_field = self.tmp / "missing.json"
        missing_field.write_text(json.dumps({"task": "T-01"}), encoding="utf-8")
        cases = {
            "no es JSON válido": str(bad_json),
            "máximo": str(huge),
            "falta el campo 'status'": str(missing_field),
            "campo no permitido 'extra'": self.manifest("extra", extra=1),
            "'status' debe ser uno de": self.manifest("status", status="ok"),
            "'files' debe ser una lista de cadenas": self.manifest("files", files="src/a.py"),
            "'tests' debe ser una lista": self.manifest("tests", tests=[{"name": "t", "result": "ok"}]),
            "no pertenece a la oleada 1": self.manifest("t3", task="T-03"),
        }
        for expected, manifest in cases.items():
            with self.subTest(expected=expected):
                out = self.verify([*self.wave_one(), manifest], ok=False)
                self.assertIn(expected, out)
        valid = self.wave_one()
        out = self.verify([str(bad_json), valid[1]], ok=False)
        self.assertIn("T-01 no ejecutada", out)
        out = self.verify([*self.wave_one(), self.manifest("dup", task="T-02", files=["src/b/new.py"],
                                                          criteria=["AC-02"])], ok=False)
        self.assertIn("manifiesto duplicado de T-02", out)

    def test_a_manifest_that_is_not_a_json_object_is_rejected(self):
        # verifies: SPEC-0001/AC-08
        array = self.tmp / "array.json"
        array.write_text("[]", encoding="utf-8")
        out = self.verify([*self.wave_one(), str(array)], ok=False)
        self.assertIn("debe ser un objeto JSON", out)

    def test_scope_and_real_changes(self):
        # verifies: SPEC-0001/AC-09
        self.write("src/other.py", "o = 1\n")
        out = self.verify(self.wave_one(files=["src/a.py", "tests/test_a.py", "src/other.py"]), ok=False)
        self.assertIn("'src/other.py' está fuera de los ficheros de la tarea", out)
        self.git("checkout", "--", ".")
        shutil.rmtree(self.work / "src/b")
        os.remove(self.work / "tests/test_a.py")
        os.remove(self.work / "src/other.py")

        manifests = self.wave_one()
        self.write("README.md", "stray\n")
        out = self.verify(manifests, ok=False)
        self.assertIn("cambio que ningún manifiesto declara: 'README.md'", out)
        os.remove(self.work / "README.md")

        self.git("checkout", "--", "src/a.py")
        out = self.verify(manifests, ok=False)
        self.assertIn("declara 'src/a.py', que no tiene cambios", out)

    def test_a_sibling_directory_of_a_task_glob_is_out_of_scope(self):
        # verifies: SPEC-0001/AC-09
        self.write("src/bb/x.py", "x = 1\n")
        manifests = self.wave_one()
        t2 = self.manifest("t2", task="T-02", files=["src/b/new.py", "src/bb/x.py"], criteria=["AC-02"])
        out = self.verify([manifests[0], t2], ok=False)
        self.assertIn("'src/bb/x.py' está fuera de los ficheros de la tarea", out)

    def test_deleted_and_renamed_files_are_changes(self):
        # unit: plan.verify_wave
        self.write("src/b/old.py", "o = 1\n")
        self.write("src/b/gone.py", "g = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "old")
        manifests = self.wave_one()
        self.git("mv", "src/b/old.py", "src/b/moved.py")
        os.remove(self.work / "src/b/gone.py")
        out = self.verify(manifests, ok=False)
        for path in ("src/b/moved.py", "src/b/old.py", "src/b/gone.py"):
            self.assertIn(f"cambio que ningún manifiesto declara: '{path}'", out)
        t2 = self.manifest("t2", task="T-02", criteria=["AC-02"],
                           files=["src/b/new.py", "src/b/moved.py", "src/b/old.py", "src/b/gone.py"])
        self.verify([manifests[0], t2], ok=True)

    def test_done_manifest_must_be_complete(self):
        # verifies: SPEC-0001/AC-10
        cases = {
            "no cubre AC-01": {"criteria": []},
            "criterios ajenos a la tarea: AC-02": {"criteria": ["AC-01", "AC-02"]},
            "no informa de ningún test": {"tests": []},
            "tests en rojo: t": {"tests": [{"name": "t", "result": "fail"}]},
            "preguntas abiertas": {"questions": ["¿qué formato?"]},
        }
        for expected, override in cases.items():
            with self.subTest(expected=expected):
                out = self.verify(self.wave_one(**override), ok=False)
                self.assertIn(expected, out)

    def test_only_the_failing_tests_are_reported_as_red(self):
        # verifies: SPEC-0001/AC-10
        tests = [{"name": "good", "result": "pass"}, {"name": "bad", "result": "fail"}]
        out = self.verify(self.wave_one(tests=tests), ok=False)
        self.assertIn("tests en rojo: bad", out)
        self.assertNotIn("tests en rojo: good", out)

    def test_deviations_are_warnings(self):
        # verifies: SPEC-0001/AC-11
        out = self.verify(self.wave_one(deviations=["usa una lista en vez de un set"]), ok=True)
        self.assertIn("⚠ T-01 desvío: usa una lista en vez de un set", out)
        self.assertIn("1 desvíos por resolver", out)


class ReviewReportTests(RepoTestCase):
    def recorded(self) -> dict:
        from mthlib import review
        sha = self.git("rev-parse", "HEAD").strip()
        return review.results(self.work / ".git", "feat/demo", sha)

    @property
    def inbox(self) -> Path:
        folder = self.work / ".work" / "tmp"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def report_file(self, name: str, body: str) -> str:
        path = self.inbox / name
        path.write_text(body, encoding="utf-8")
        return str(path)

    def record(self, report, ok):
        return self.mth("review", "record", "verificador", "--report", report, "--summary", "s", ok=ok)

    def test_blocking_count_is_computed_from_the_findings(self):
        # verifies: SPEC-0013/AC-01
        report = self.report_file("r.txt", "HALLAZGOS\n1. [bloqueante] a.py:1 — x.\n2. [Importante] b.py:2 — y.\n"
                            "   continuación de la línea anterior\nRESUMEN: r\nBLOQUEANTES: 1\n\n")
        self.assertIn("(1 bloqueantes, intento 1)", self.record(report, ok=True))
        entry = self.recorded()["verificador"]
        self.assertEqual((entry["status"], entry["blocking"]), ("ok", 1))
        self.assertEqual(entry["findings"], {"bloqueante": 1, "importante": 1, "sugerencia": 0})

    def test_ninguno_counts_zero(self):
        # verifies: SPEC-0013/AC-01
        report = self.report_file("r.txt", "CRITERIOS\n- AC-01: sí\nHALLAZGOS\nninguno\nRESUMEN: r\nBLOQUEANTES: 0\n")
        self.record(report, ok=True)
        self.assertEqual(self.recorded()["verificador"]["blocking"], 0)

    def test_a_declared_figure_that_differs_is_a_failed_review(self):
        # verifies: SPEC-0013/AC-02
        for name, body in (("lower.txt", "HALLAZGOS\n1. [bloqueante] a.py:1 — x.\nBLOQUEANTES: 0\n"),
                           ("higher.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n")):
            with self.subTest(name=name):
                out = self.record(self.report_file(name, body), ok=False)
                self.assertIn("declara", out)
                self.assertEqual(self.recorded()["verificador"]["status"], "failed")
                from mthlib import review
                approved, state = review.describe(self.recorded()["verificador"])
                self.assertFalse(approved)
                self.assertIn("fallida (intento", state)

    def test_a_declared_blocker_with_only_other_findings_is_a_failed_review(self):
        # verifies: SPEC-0013/AC-02
        body = "HALLAZGOS\n1. [importante] a.py:1 — x.\n2. [sugerencia] b.py:2 — y.\nBLOQUEANTES: 1\n"
        out = self.record(self.report_file("others.txt", body), ok=False)
        self.assertIn("declara", out)
        self.assertEqual(self.recorded()["verificador"]["status"], "failed")

    def test_an_unreadable_format_is_a_failed_review(self):
        # verifies: SPEC-0013/AC-03
        cases = {
            "nosection": "RESUMEN: r\nBLOQUEANTES: 0\n",
            "twice": "HALLAZGOS\nninguno\nHALLAZGOS\nninguno\nBLOQUEANTES: 0\n",
            "bullets": "HALLAZGOS\n- [bloqueante] a.py:1 — x.\nBLOQUEANTES: 0\n",
            "severity": "HALLAZGOS\n1. [grave] a.py:1 — x.\nBLOQUEANTES: 0\n",
            "both": "HALLAZGOS\nninguno\n1. [sugerencia] a.py:1 — x.\nBLOQUEANTES: 0\n",
            "stray": "HALLAZGOS\nninguno\nAfirmaciones y estado:\nBLOQUEANTES: 0\n",
            "cut": "HALLAZGOS\n1. [importante] a.py:1 — x.\n",
        }
        for name, body in cases.items():
            with self.subTest(name=name):
                self.record(self.report_file(f"{name}.txt", body), ok=False)
                self.assertEqual(self.recorded()["verificador"]["status"], "failed")
                self.assertNotIn("blocking", self.recorded()["verificador"])

    def test_missing_empty_or_oversized_reports_are_failed_reviews(self):
        # verifies: SPEC-0013/AC-04
        # verifies: SPEC-0001/AC-12
        huge = self.report_file("huge.txt", "x" * (256 * 1024 + 1) + "\nBLOQUEANTES: 0\n")
        cases = ((str(self.inbox / "missing.txt"), "no se puede leer"), (self.report_file("empty.txt", ""), "vacío"),
                 (huge, "supera"))
        for report, reason in cases:
            with self.subTest(report=report):
                self.record(report, ok=False)
                entry = self.recorded()["verificador"]
                self.assertEqual(entry["status"], "failed")
                self.assertIn(reason, entry["reason"])
                self.assertNotIn("report_sha256", entry)

    def test_a_report_of_exactly_the_size_limit_is_accepted(self):
        # verifies: SPEC-0013/AC-04
        tail = "\nBLOQUEANTES: 0\n"
        head = "HALLAZGOS\nninguno\nRESUMEN: "
        body = head + "x" * (256 * 1024 - len(head) - len(tail)) + tail
        self.assertEqual(len(body.encode()), 256 * 1024)
        self.record(self.report_file("limit.txt", body), ok=True)
        self.assertEqual(self.recorded()["verificador"]["status"], "ok")

    def test_the_report_is_archived_verbatim_and_never_overwritten(self):
        # verifies: SPEC-0013/AC-05
        body = "HALLAZGOS\r\nninguno\r\nBLOQUEANTES: 0\r\n"
        report = self.inbox / "r.txt"
        report.write_bytes(body.encode())
        self.record(str(report), ok=True)
        sha = self.git("rev-parse", "HEAD").strip()
        entry = self.recorded()["verificador"]
        archived = self.work / ".work" / "reviews" / f"{sha}-verificador-1.md"
        self.assertEqual(archived.read_bytes(), body.encode())
        self.assertEqual(entry["report"], str(archived))
        import hashlib
        self.assertEqual(entry["report_sha256"], hashlib.sha256(body.encode()).hexdigest())
        archived.write_text("otro", encoding="utf-8")  # a second record must not touch attempt 1
        self.record(str(report), ok=True)
        self.assertEqual(archived.read_text(encoding="utf-8"), "otro")
        self.assertTrue((self.work / ".work" / "reviews" / f"{sha}-verificador-2.md").is_file())

    def test_attempts_are_counted_and_survive_a_later_success(self):
        # verifies: SPEC-0013/AC-06
        # verifies: SPEC-0013/AC-09
        bad = self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n")
        good = self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n")
        self.assertIn("UNA corrección", self.record(bad, ok=False))
        self.assertEqual(self.recorded()["verificador"]["attempts"], 1)
        out = self.record(bad, ok=False)
        self.assertIn("detente", out)
        self.assertEqual(self.recorded()["verificador"]["attempts"], 2)
        self.record(good, ok=True)
        entry = self.recorded()["verificador"]
        self.assertEqual((entry["status"], entry["attempts"], entry["blocking"]), ("ok", 3, 0))
        self.assertEqual(entry["failures"], 0)
        self.git("commit", "--allow-empty", "-q", "-m", "chore: next\n\nRefs: n/a")
        self.assertNotIn("verificador", self.recorded())  # a new SHA starts from zero

    def test_integration_tells_a_failed_review_from_a_missing_one(self):
        # verifies: SPEC-0013/AC-07
        from mthlib import review
        from mthlib.errors import MthError
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        sha = self.git("rev-parse", "HEAD").strip()
        with self.assertRaises(MthError) as ctx:
            review.check(self.work / ".git", "feat/demo", sha, ["verificador"])
        self.assertIn("Revisión fallida", ctx.exception.message)
        self.assertIn("intento 1", ctx.exception.message)
        self.assertEqual(review.describe(None), (False, "pendiente"))

    def test_a_report_that_is_not_utf8_is_archived_and_failed(self):
        # verifies: SPEC-0013/AC-03
        report = self.inbox / "bin.txt"
        report.write_bytes(b"HALLAZGOS\nninguno\n\xff\xfe\nBLOQUEANTES: 0\n")
        self.record(str(report), ok=False)
        entry = self.recorded()["verificador"]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("UTF-8", entry["reason"])
        self.assertEqual(Path(entry["report"]).read_bytes(), report.read_bytes())

    def test_a_report_already_in_the_archive_is_not_copied(self):
        # verifies: SPEC-0013/AC-05
        sha = self.git("rev-parse", "HEAD").strip()
        folder = self.work / ".work" / "reviews"
        folder.mkdir(parents=True)
        own = folder / f"{sha}-verificador-1.md"
        own.write_text("HALLAZGOS\nninguno\nBLOQUEANTES: 0\n", encoding="utf-8")
        self.record(str(own), ok=True)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [own.name])

    def test_status_shows_the_failed_review_and_its_attempts(self):
        # verifies: SPEC-0013/AC-07
        from unittest import mock

        from mthlib import branches, cli, flow, review
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        approved, state = review.describe(self.recorded()["verificador"])
        self.assertFalse(approved)
        self.assertTrue(state.startswith("fallida (intento 1): el revisor declara 1"))
        # The command prints that state; the test repo has no remote, so the branch lookup is stubbed.
        info = mock.Mock()
        with mock.patch.object(branches, "parse", return_value=info), \
                mock.patch.object(flow, "required_reviewers", return_value=["verificador"]), \
                mock.patch.object(cli, "_ctx") as ctx, mock.patch("builtins.print") as shown:
            ctx.return_value.git.current_branch.return_value = "feat/demo"
            ctx.return_value.git.sha.return_value = self.git("rev-parse", "HEAD").strip()
            ctx.return_value.git.git_dir.return_value = self.work / ".git"
            ctx.return_value.cfg = {"review": {"agents": ["verificador"]}}
            cli._cmd_review(mock.Mock(action="status", agent=None))
        self.assertIn("fallida (intento 1)", shown.call_args.args[0])

    def test_a_blocker_mark_outside_the_counted_findings_fails_the_review(self):
        # verifies: SPEC-0013/AC-10
        cases = {
            "indented": "HALLAZGOS\n  1. [bloqueante] a.py:1 — x.\nBLOQUEANTES: 0\n",
            "after": "HALLAZGOS\nninguno\nFUERA DE ALCANCE\n1. [bloqueante] a.py:1 — x.\nBLOQUEANTES: 0\n",
            "prose": "HALLAZGOS\nninguno\nRESUMEN: hay un [Bloqueante] sin contar\nBLOQUEANTES: 0\n",
        }
        for name, body in cases.items():
            with self.subTest(name=name):
                out = self.record(self.report_file(f"{name}.txt", body), ok=False)
                self.assertIn("marcas [bloqueante]", out)
                self.assertEqual(self.recorded()["verificador"]["status"], "failed")

    def test_an_archive_that_escapes_the_repository_is_refused(self):
        # verifies: SPEC-0013/AC-11
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.work / ".work").mkdir(exist_ok=True)
        (self.work / ".work" / "reviews").symlink_to(outside)
        report = self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n")
        self.assertIn("queda fuera de", self.record(report, ok=False))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertNotIn("verificador", self.recorded())

    def test_unsafe_names_and_partial_copies(self):
        # verifies: SPEC-0013/AC-11
        from mthlib import review
        from mthlib.errors import MthError
        folder = self.work / ".work" / "reviews"
        for agent, sha in (("../x", "abc123"), ("a/b", "abc123"), ("..", "abc123"),
                           ("verificador", "../abc"), ("verificador", "a/b")):
            with self.subTest(agent=agent, sha=sha), self.assertRaises(MthError):
                review.archive(self.work, folder, sha, agent, 1, b"x")
        real_open = open

        def failing(path, mode="r", *a, **k):
            fh = real_open(path, mode, *a, **k)
            if mode == "xb":
                fh.write = mock.Mock(side_effect=OSError("disco lleno"))
            return fh

        with mock.patch("builtins.open", failing), self.assertRaises(MthError) as partial:
            review.archive(self.work, folder, "abc123", "verificador", 1, b"x")
        self.assertEqual(partial.exception.stage, "archive")
        self.assertEqual(list(folder.iterdir()), [])

    def test_the_stop_advice_counts_consecutive_failures(self):
        # verifies: SPEC-0013/AC-06
        bad = self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n")
        good = self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n")
        self.record(good, ok=True)
        self.assertIn("UNA corrección", self.record(bad, ok=False))  # a failure after an ok is the first
        self.assertEqual(self.recorded()["verificador"]["failures"], 1)

    def test_a_report_outside_the_repository_or_not_a_regular_file_is_refused(self):
        # verifies: SPEC-0013/AC-12
        secret = self.tmp / "secret.txt"
        secret.write_text("clave privada\n", encoding="utf-8")
        out = self.record(str(secret), ok=False)
        self.assertIn("queda fuera de", out)
        self.assertNotIn("verificador", self.recorded())
        fifo = self.inbox / "pipe"
        os.mkfifo(fifo)
        self.record(str(fifo), ok=False)
        self.assertIn("no es un fichero regular", self.recorded()["verificador"]["reason"])

    def test_a_failure_reason_never_quotes_the_report(self):
        # verifies: SPEC-0013/AC-12
        self.record(self.report_file("leak.txt", "HALLAZGOS\nclave-secreta-123\nBLOQUEANTES: 0\n"), ok=False)
        self.assertNotIn("clave-secreta", json.dumps(self.recorded()["verificador"]["reason"]))

    def test_a_report_with_text_after_the_blocker_line_is_not_approved(self):
        # verifies: SPEC-0001/AC-12
        self.record(self.report_file("late.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\nFin del informe\n"), ok=False)
        entry = self.recorded()["verificador"]
        self.assertEqual(entry["status"], "failed")
        self.assertNotIn("blocking", entry)

    def test_parallel_records_do_not_lose_updates(self):
        # verifies: SPEC-0013/AC-13
        from concurrent.futures import ThreadPoolExecutor

        from mthlib import review
        sha = self.git("rev-parse", "HEAD").strip()
        good = Path(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"))
        agents = [f"agente-{i}" for i in range(12)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda a: review.record_report(
                self.work / ".git", self.work, self.work / ".work" / "reviews", "feat/demo", sha, a, good, "s"), agents))
        self.assertEqual(sorted(review.results(self.work / ".git", "feat/demo", sha)), sorted(agents))

    def test_parallel_cli_processes_do_not_lose_updates(self):
        # verifies: SPEC-0013/AC-13
        report = self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n")
        agents = [f"agente-{i}" for i in range(4)]
        self.write(".claude/methodology.toml", f'version = 1\n[commands]\ntest = ""\n[review]\nagents = {json.dumps(agents)}\n')
        procs = [subprocess.Popen([sys.executable, str(MTH), "review", "record", a, "--report", report,
                                   "--summary", "s"], cwd=self.work, env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for a in agents]
        self.assertEqual([p.wait() for p in procs], [0] * len(agents))
        for p in procs:
            p.stdout.close()
        self.assertEqual(sorted(self.recorded()), sorted(agents))

    def test_a_missing_report_option_is_a_clear_error(self):
        # verifies: SPEC-0013/AC-12
        out = self.mth("review", "record", "verificador", "--summary", "s", ok=False)
        self.assertIn("necesita", out)

    def test_store_failures_and_limits_record_nothing_and_name_their_stage(self):
        # verifies: SPEC-0013/AC-14
        from mthlib import review
        from mthlib.errors import MthError
        sha = self.git("rev-parse", "HEAD").strip()
        git_dir, folder = self.work / ".git", self.work / ".work" / "reviews"
        good = Path(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"))

        def attempt(summary="s"):
            return review.record_report(git_dir, self.work, folder, "feat/demo", sha, "verificador", good, summary)

        with self.assertRaises(review.ReviewError) as long:
            attempt("x" * (review.MAX_SUMMARY + 1))
        self.assertEqual(long.exception.stage, "rejected")
        store = git_dir / "mth" / "reviews.json"
        store.parent.mkdir(exist_ok=True)
        store.write_text("{no es json", encoding="utf-8")
        with self.assertRaises(review.ReviewError) as corrupt:
            attempt()
        self.assertEqual(corrupt.exception.stage, "store")
        self.assertFalse(folder.exists())  # nothing archived before the store was read
        store.unlink()
        import fcntl
        with open(store.with_name("reviews.lock"), "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with mock.patch.object(review, "LOCK_TIMEOUT", 0.2), self.assertRaises(review.ReviewError) as busy:
                attempt()
        self.assertEqual(busy.exception.stage, "lock")
        self.assertNotIn("verificador", review.results(git_dir, "feat/demo", sha))
        with mock.patch.object(review, "record", side_effect=MthError("disco lleno")), \
                self.assertRaises(review.ReviewError) as orphan:
            attempt()
        self.assertEqual(orphan.exception.stage, "store")
        self.assertTrue(orphan.exception.archived.is_file())

    def test_the_cli_traces_not_recorded_with_its_stage_and_orphan(self):
        # verifies: SPEC-0013/AC-14
        store = self.work / ".git" / "mth" / "reviews.json"
        store.parent.mkdir(exist_ok=True)
        store.write_text("{no es json", encoding="utf-8")
        self.record(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"), ok=False)
        events = [json.loads(line) for line in (self.work / ".git" / "mth" / "trace.jsonl").read_text().splitlines()]
        event = [e for e in events if e["event"] == "review.not_recorded"][-1]
        self.assertEqual((event["stage"], event["agent"]), ("store", "verificador"))
        self.assertIsNone(event["orphan"])
        out = self.mth("review", "record", "verificador", "--summary", "s", ok=False)
        self.assertIn("necesita", out)

    def test_the_cli_traces_review_failed_with_its_reason_and_failures(self):
        # verifies: SPEC-0013/AC-14
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        events = [json.loads(line) for line in (self.work / ".git" / "mth" / "trace.jsonl").read_text().splitlines()]
        failed = [e for e in events if e["event"] == "review.failed"]
        self.assertEqual([e["failures"] for e in failed], [1, 2])
        self.assertIn("declara", failed[-1]["reason"])

    def test_the_cli_traces_the_orphan_archive_when_the_store_cannot_be_written(self):
        # verifies: SPEC-0013/AC-14
        store = self.work / ".git" / "mth" / "reviews.json"
        store.mkdir(parents=True)  # reading finds no file, replacing a directory fails after archiving
        self.record(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"), ok=False)
        events = [json.loads(line) for line in (self.work / ".git" / "mth" / "trace.jsonl").read_text().splitlines()]
        event = [e for e in events if e["event"] == "review.not_recorded"][-1]
        self.assertEqual(event["stage"], "store")
        self.assertTrue(Path(event["orphan"]).is_file())

    def test_integration_refuses_a_failed_review(self):
        # verifies: SPEC-0013/AC-07
        from unittest import mock

        from mthlib import branches, flow
        from mthlib.errors import MthError
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        ctx = mock.Mock()
        ctx.cfg = {"review": {"agents": ["verificador"], "required_for": ["feat"]}}
        ctx.git.git_dir.return_value = self.work / ".git"
        ctx.git.sha.return_value = self.git("rev-parse", "HEAD").strip()
        info = mock.Mock(is_child=False, kind="feat")
        with mock.patch.object(flow, "required_reviewers", return_value=["verificador"]), \
                self.assertRaises(MthError) as caught:
            flow._review(ctx, info, "feat/demo")
        self.assertIn("Revisión fallida", caught.exception.message)

    def test_a_summary_with_carriage_returns_stays_on_one_row(self):
        # verifies: SPEC-0013/AC-12
        from mthlib import flow
        self.assertEqual(flow._cell("a\r\nb | c\td"), "a b \\| c d")

    def test_a_report_outside_work_is_refused_even_inside_the_repository(self):
        # verifies: SPEC-0013/AC-12
        env = self.work / ".env"
        env.write_text("TOKEN=abc\n", encoding="utf-8")
        self.assertIn("queda fuera de", self.record(str(env), ok=False))
        self.assertNotIn("verificador", self.recorded())

    def test_a_summary_pipe_cannot_break_the_pr_table(self):
        # verifies: SPEC-0013/AC-12
        from mthlib import flow
        body = flow._pr_body("r", [], None, "ok", {"verificador": {"blocking": 0, "summary": "a | b\nc"}})
        self.assertIn("| verificador | 0 | a \\| b c |", body)

    def test_a_store_entry_of_the_wrong_shape_is_a_clear_store_error(self):
        # verifies: SPEC-0013/AC-14
        from mthlib import review
        sha = self.git("rev-parse", "HEAD").strip()
        store = self.work / ".git" / "mth" / "reviews.json"
        store.parent.mkdir(exist_ok=True)
        for entry in ({"attempts": "dos"}, "no es un objeto"):
            with self.subTest(entry=entry):
                store.write_text(json.dumps({"feat/demo": {sha: {"verificador": entry}}}), encoding="utf-8")
                good = Path(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"))
                with self.assertRaises(review.ReviewError) as caught:
                    review.record_report(self.work / ".git", self.work, self.work / ".work" / "reviews",
                                         "feat/demo", sha, "verificador", good, "s")
                self.assertEqual(caught.exception.stage, "store")

    def test_a_lock_error_that_is_not_contention_fails_at_once(self):
        # verifies: SPEC-0013/AC-14
        import fcntl

        from mthlib import review
        with mock.patch.object(fcntl, "flock", side_effect=OSError(37, "ENOLCK")), \
                self.assertRaises(review.ReviewError) as caught, review._locked(self.work / ".git", timeout=30):
            pass
        self.assertEqual(caught.exception.stage, "lock")

    def test_a_pipe_cell_has_no_backslash_inside_an_f_string(self):
        # verifies: SPEC-0013/AC-12
        import re as regex
        source = (Path(__file__).resolve().parent.parent / "plugins/methodology/scripts/mthlib/flow.py").read_text()
        self.assertIsNone(regex.search(r"""f"[^"\n]*\{[^}"\n]*\\""", source))  # Python 3.11 rejects it

    def test_an_overwritten_entry_is_visible_as_previous_status(self):
        # verifies: SPEC-0013/AC-14
        self.record(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"), ok=True)
        self.record(self.report_file("bad.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 1\n"), ok=False)
        self.assertEqual(self.recorded()["verificador"]["previous_status"], "ok")

    def test_an_unarchivable_report_records_nothing(self):
        # verifies: SPEC-0013/AC-08
        (self.work / ".work").mkdir(exist_ok=True)
        (self.work / ".work" / "reviews").write_text("no es un directorio", encoding="utf-8")
        report = self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n")
        self.assertIn("No se pudo archivar", self.record(report, ok=False))
        self.assertNotIn("verificador", self.recorded())

    def test_a_copy_that_fails_midway_records_nothing(self):
        # verifies: SPEC-0013/AC-08
        from mthlib import review
        sha = self.git("rev-parse", "HEAD").strip()
        good = Path(self.report_file("good.txt", "HALLAZGOS\nninguno\nBLOQUEANTES: 0\n"))
        real_open = open

        def failing(path, mode="r", *a, **k):
            fh = real_open(path, mode, *a, **k)
            if mode == "xb":
                fh.write = mock.Mock(side_effect=OSError("disco lleno"))
            return fh

        with mock.patch("builtins.open", failing), self.assertRaises(review.ReviewError) as caught:
            review.record_report(self.work / ".git", self.work, self.work / ".work" / "reviews",
                                 "feat/demo", sha, "verificador", good, "s")
        self.assertEqual(caught.exception.stage, "archive")
        self.assertNotIn("verificador", self.recorded())

    def test_an_ok_after_an_unreadable_report_keeps_the_computed_blockers(self):
        # verifies: SPEC-0013/AC-09
        self.record(str(self.inbox / "missing.txt"), ok=False)
        report = self.report_file("one.txt", "HALLAZGOS\n1. [bloqueante] a.py:1 — x.\nBLOQUEANTES: 1\n")
        self.record(report, ok=True)
        entry = self.recorded()["verificador"]
        self.assertEqual((entry["status"], entry["attempts"], entry["blocking"]), ("ok", 2, 1))
        self.assertEqual(entry["failures"], 0)

    def test_a_blocker_mark_before_the_findings_section_fails_the_review(self):
        # verifies: SPEC-0013/AC-10
        body = "CRITERIOS\n- [bloqueante] AC-01: no\nHALLAZGOS\nninguno\nBLOQUEANTES: 0\n"
        out = self.record(self.report_file("before.txt", body), ok=False)
        self.assertIn("marcas [bloqueante]", out)
        self.assertEqual(self.recorded()["verificador"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
