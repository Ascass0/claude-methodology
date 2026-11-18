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
            "no declara ficheros": spec_text("| T-01 | 1 |  | AC-01, AC-02, AC-03 |"),
            "comillas invertidas": spec_text("| T-01 | 1 | src/a.py | AC-01, AC-02, AC-03 |"),
            "ruta no permitida": spec_text("| T-01 | 1 | `/etc/passwd` | AC-01, AC-02, AC-03 |"),
            "ruta no permitida ": spec_text("| T-01 | 1 | `../x.py` | AC-01, AC-02, AC-03 |"),
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                problems = plan.check(text)[1]
                self.assertTrue(any(expected.strip() in p.message for p in problems), problems)
                self.assertTrue(all(p.line > 0 for p in problems if expected.strip() in p.message))

    def test_too_many_tasks(self):
        # verifies: SPEC-0001/AC-02
        rows = "\n".join(f"| T-{i:02d} | {i} | `f{i}` | AC-01 |" for i in range(1, 52))
        self.assertTrue(any("máximo 50" in m for m in messages(spec_text(rows, criteria="- **AC-01**: a.\n"))))

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
                self.assertTrue(any("pueden tocar el mismo fichero" in m for m in messages(spec_text(rows))))

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


class RepoTestCase(unittest.TestCase):
    """A throwaway repository that adopted the methodology, with a committed spec that has a plan."""

    rows = """
        | T-01 | 1 | `src/a.py`, `tests/test_a.py` | AC-01 |
        | T-02 | 1 | `src/b/**` | AC-02 |
        | T-03 | 2 | `src/c.py` | AC-03 |
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.env = {**os.environ, **GIT_ENV}
        self.git("init", "-q", "-b", "feat/demo")
        self.write(".claude/methodology.toml",
                   'version = 1\n[commands]\ntest = ""\n[review]\nagents = ["verificador"]\n')
        self.write(f"specs/features/{SPEC_ID}-demo.md", spec_text(self.rows))
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
        self.assertIn("Oleada 1: T-01, T-02", out)
        self.assertIn("Oleada 2: T-03", out)


class WaveVerifyTests(RepoTestCase):
    def test_accepts_matching_wave(self):
        # verifies: SPEC-0001/AC-06
        out = self.verify(self.wave_one(), ok=True)
        self.assertIn(f"Oleada 1 de {SPEC_ID} verificada", out)

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
        out = self.verify([*self.wave_one(), self.manifest("dup", task="T-02", files=["src/b/new.py"],
                                                          criteria=["AC-02"])], ok=False)
        self.assertIn("manifiesto duplicado de T-02", out)

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

    def record(self, report, ok):
        return self.mth("review", "record", "verificador", "--report", report, "--summary", "s", ok=ok)

    def test_blocking_count_comes_from_report(self):
        # verifies: SPEC-0001/AC-12
        report = self.tmp / "r.txt"
        report.write_text("HALLAZGOS\n1. [bloqueante] a.py:1 — x.\n\nBLOQUEANTES: 1\n\n", encoding="utf-8")
        self.assertIn("(1 bloqueantes)", self.record(str(report), ok=True))
        self.assertEqual(self.recorded()["verificador"]["blocking"], 1)

    def test_unfinished_reviewer_is_not_recorded(self):
        # verifies: SPEC-0001/AC-12
        empty = self.tmp / "empty.txt"
        empty.write_text("", encoding="utf-8")
        cut = self.tmp / "cut.txt"
        cut.write_text("HALLAZGOS\n1. [importante] a.py:1 — x.\n", encoding="utf-8")
        huge = self.tmp / "huge.txt"
        huge.write_text("x" * (256 * 1024 + 1) + "\nBLOQUEANTES: 0\n", encoding="utf-8")
        for report in (str(self.tmp / "missing.txt"), str(empty), str(cut), str(huge)):
            with self.subTest(report=report):
                out = self.record(report, ok=False)
                self.assertIn("revisor no ejecutado", out)
                self.assertNotIn("verificador", self.recorded())


if __name__ == "__main__":
    unittest.main()
