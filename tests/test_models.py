"""Tests of model tiers per task, retry escalation and metrics (SPEC-0002)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import plan  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_delegation import SPEC_ID, RepoTestCase, spec_text  # noqa: E402

BASE_CONFIG = 'version = 1\n[commands]\ntest = ""\n'
MODEL_HEADER = "| Tarea | Oleada | Ficheros | Criterios | Modelo |"


class ModelConfigTests(unittest.TestCase):
    def test_defaults(self):
        # verifies: SPEC-0002/AC-01
        models = parse(Path("."), BASE_CONFIG)["models"]
        self.assertEqual(models, {"ladder": ["haiku", "sonnet", "opus"], "task": "sonnet",
                                  "review": "sonnet", "documenter": "sonnet"})

    def test_invalid_models_fail_fast(self):
        # verifies: SPEC-0002/AC-02
        cases = {
            "lista no vacía": "ladder = []",
            "sin repetir": 'ladder = ["haiku", "haiku"]',
            "alias desconocidos: sonet": 'ladder = ["haiku", "sonet"]',
            "'models.task' = 'opus' no está": 'ladder = ["haiku", "sonnet"]\ntask = "opus"',
            "'models.review' = 'fable' no está": 'review = "fable"',
            "'models.documenter' = 'haiku' no está": 'ladder = ["sonnet", "opus"]\ndocumenter = "haiku"',
            "debe ser de tipo str": "task = 3",
        }
        for expected, body in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(MthError) as ctx:
                    parse(Path("."), BASE_CONFIG + "[models]\n" + body + "\n")
                self.assertIn(expected, ctx.exception.message)

    def test_valid_custom_ladder_is_accepted(self):
        # verifies: SPEC-0002/AC-02
        body = '[models]\nladder = ["fable", "opus"]\ntask = "opus"\nreview = "fable"\ndocumenter = "opus"\n'
        models = parse(Path("."), BASE_CONFIG + body)["models"]
        self.assertEqual(models, {"ladder": ["fable", "opus"], "task": "opus", "review": "fable",
                                  "documenter": "opus"})


class PlanModelColumnTests(unittest.TestCase):
    def test_model_column(self):
        # verifies: SPEC-0002/AC-03
        rows = "| T-01 | 1 | `a` | AC-01 | haiku |\n| T-02 | 1 | `b` | AC-02, AC-03 | |"
        tasks, problems = plan.check(spec_text(rows, header=MODEL_HEADER))
        self.assertEqual(problems, [])
        self.assertEqual([t.effective_model("sonnet") for t in tasks], ["haiku", "sonnet"])

    def test_four_columns_still_valid(self):
        # verifies: SPEC-0002/AC-03
        tasks, problems = plan.check(spec_text("| T-01 | 1 | `a` | AC-01, AC-02, AC-03 |"))
        self.assertEqual(problems, [])
        self.assertEqual(tasks[0].model, "")

    def test_model_outside_ladder(self):
        # verifies: SPEC-0002/AC-03
        rows = "| T-01 | 1 | `a` | AC-01, AC-02, AC-03 | fable |"
        problems = plan.check(spec_text(rows, header=MODEL_HEADER), ("haiku", "sonnet", "opus"))[1]
        self.assertTrue(any("modelo 'fable' fuera de models.ladder" in p.message and p.line > 0
                            for p in problems), problems)


class ModelRepoTestCase(RepoTestCase):
    header = MODEL_HEADER
    rows = """
        | T-01 | 1 | `src/a.py`, `tests/test_a.py` | AC-01 | haiku |
        | T-02 | 1 | `src/b/**` | AC-02 | |
        | T-03 | 2 | `src/c.py` | AC-03 | opus |
    """

    def events(self) -> list[dict]:
        path = self.work / ".git/mth/trace.jsonl"
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [e for e in map(json.loads, lines) if e["event"] == "plan.task"]


class ModelCommandTests(ModelRepoTestCase):
    def test_models_command_shows_defaults(self):
        # verifies: SPEC-0002/AC-01
        out = self.mth("models")
        self.assertIn("Escalera de reintento: haiku → sonnet → opus", out)
        self.assertIn("Tareas del plan sin modelo: sonnet", out)
        self.assertIn("Revisores: sonnet", out)
        self.assertIn("Documentador: sonnet", out)

    def test_models_command_shows_the_planner_as_fixed_opus(self):
        # verifies: SPEC-0023/AC-21
        self.assertIn("Planificador: opus (fijo)", self.mth("models"))
        custom = '[models]\nladder = ["fable", "opus"]\ntask = "opus"\nreview = "fable"\ndocumenter = "opus"\n'
        self.write(".claude/methodology.toml", self.config + custom)
        self.assertIn("Planificador: opus (fijo)", self.mth("models"))

    def test_plan_check_shows_effective_models(self):
        # verifies: SPEC-0002/AC-03
        out = self.mth("plan", "check", SPEC_ID)
        self.assertIn("Oleada 1: T-01 (haiku), T-02 (sonnet)", out)
        self.assertIn("Oleada 2: T-03 (opus)", out)

    def test_plan_model_and_retry(self):
        # verifies: SPEC-0002/AC-04
        self.assertEqual(self.mth("plan", "model", SPEC_ID, "T-01"), "haiku\n")
        self.assertEqual(self.mth("plan", "model", SPEC_ID, "T-01", "--retry"), "sonnet\n")
        self.assertEqual(self.mth("plan", "model", SPEC_ID, "T-02"), "sonnet\n")
        self.assertEqual(self.mth("plan", "model", SPEC_ID, "T-02", "--retry"), "opus\n")
        self.assertEqual(self.mth("plan", "model", SPEC_ID, "T-03", "--retry"), "opus\n")

    def test_plan_model_unknown_task(self):
        # verifies: SPEC-0002/AC-04
        out = self.mth("plan", "model", SPEC_ID, "T-09", ok=False)
        self.assertIn("T-09 no es una tarea del plan", out)
        for alias in ("haiku\n", "sonnet\n", "opus\n"):
            self.assertNotIn(alias, out)


class ModelFailureModeTests(ModelRepoTestCase):
    """Failure modes of SPEC-0002 not tied to a single acceptance criterion."""

    def test_plan_model_on_spec_without_plan(self):
        # unit: cli plan model
        other = "SPEC-" + "0043"
        self.write(f"specs/features/{other}-plain.md", f"# {other} · Plain\n\n- **AC-01**: x.\n")
        out = self.mth("plan", "model", other, "T-01", ok=False)
        self.assertIn("no tiene sección '## Plan de trabajo'", out)
        self.assertNotIn("sonnet\n", out)

    def test_trace_reports_model_outside_ladder(self):
        # unit: trace.check
        self.write(".claude/methodology.toml", self.config + '[models]\nladder = ["sonnet", "opus"]\n')
        out = self.mth("trace", ok=False)
        self.assertIn("T-01: modelo 'haiku' fuera de models.ladder", out)

    def test_invalid_models_config_blocks_commands(self):
        # unit: config.parse
        self.write(".claude/methodology.toml", self.config + '[models]\nladder = ["sonet"]\n')
        for args in (("plan", "check", SPEC_ID), ("models",), ("trace",)):
            with self.subTest(args=args):
                out = self.mth(*args, ok=False)
                self.assertIn("alias desconocidos: sonet", out)
                self.assertNotIn("✓", out)


class VerifyRecordsTests(ModelRepoTestCase):
    def test_records_each_task_of_accepted_wave(self):
        # verifies: SPEC-0002/AC-05
        self.verify(self.wave_one(), ok=True)
        events = {e["task"]: e for e in self.events()}
        self.assertEqual(set(events), {"T-01", "T-02"})
        self.assertEqual((events["T-01"]["model"], events["T-01"]["result"]), ("haiku", "ok"))
        self.assertEqual((events["T-02"]["model"], events["T-02"]["result"]), ("sonnet", "ok"))
        self.assertEqual(len(events["T-01"]["manifest"]), 64)
        self.assertEqual(events["T-01"]["spec"], SPEC_ID)
        self.assertEqual(events["T-01"]["wave"], 1)

    def test_records_outcomes_of_rejected_wave_and_model_override(self):
        # verifies: SPEC-0002/AC-05
        manifests = self.wave_one(status="blocked")
        self.verify(manifests, ok=False)
        self.assertEqual({e["task"]: e["result"] for e in self.events()}, {"T-01": "not_completed", "T-02": "ok"})

        self.verify(self.wave_one(tests=[]), ok=False)
        self.assertEqual(self.events()[-2]["result"], "rejected")

        self.verify(self.wave_one()[1:], ok=False, wave="1")
        last = {e["task"]: e for e in self.events()[-2:]}
        self.assertEqual((last["T-01"]["result"], last["T-01"]["manifest"]), ("not_run", ""))

        args = ["plan", "verify", SPEC_ID, "--wave", "1", "--model", "T-01=sonnet"]
        for m in self.wave_one():
            args += ["--manifest", m]
        self.mth(*args)
        last = {e["task"]: e for e in self.events()[-2:]}
        self.assertEqual((last["T-01"]["model"], last["T-01"]["result"]), ("sonnet", "ok"))
        self.assertEqual(last["T-02"]["model"], "sonnet")

    def test_invalid_model_overrides_abort(self):
        # verifies: SPEC-0002/AC-06
        manifests = self.wave_one()
        cases = {
            "T-01:opus": "--model mal formado",
            "T-01=fable": "no está en models.ladder",
            "T-03=opus": "T-03 no pertenece a la oleada",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                args = ["plan", "verify", SPEC_ID, "--wave", "1", "--model", value]
                for m in manifests:
                    args += ["--manifest", m]
                out = self.mth(*args, ok=False)
                self.assertIn(expected, out)
                self.assertNotIn("verificada", out)
                self.assertEqual(self.events(), [])

    def test_one_invalid_override_among_valid_ones_aborts_everything(self):
        # verifies: SPEC-0002/AC-06
        args = ["plan", "verify", SPEC_ID, "--wave", "1", "--model", "T-01=sonnet", "--model", "T-02=fable"]
        for m in self.wave_one():
            args += ["--manifest", m]
        out = self.mth(*args, ok=False)
        self.assertIn("no está en models.ladder", out)
        self.assertNotIn("verificada", out)
        self.assertEqual(self.events(), [])


class StatsTests(ModelRepoTestCase):
    def write_trace(self, lines: list[str]) -> None:
        path = self.work / ".git/mth/trace.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def event(task, model, result, manifest, spec=SPEC_ID) -> str:
        return json.dumps({"ts": "t", "run": "r", "cmd": "plan", "event": "plan.task", "spec": spec,
                           "task": task, "wave": 1, "model": model, "result": result, "manifest": manifest})

    def test_aggregates_per_model_with_dedup_and_filter(self):
        # verifies: SPEC-0002/AC-07
        other = "SPEC-" + "0077"
        self.write_trace([
            self.event("T-01", "haiku", "rejected", "a"),
            self.event("T-01", "haiku", "rejected", "a"),     # same attempt verified again
            self.event("T-01", "sonnet", "ok", "b"),          # retry one step up
            self.event("T-02", "sonnet", "not_run", ""),
            self.event("T-02", "sonnet", "ok", "c"),
            self.event("T-05", "opus", "ok", "d", spec=other),
            json.dumps({"event": "plan.verify", "spec": SPEC_ID}),
        ])
        out = self.mth("plan", "stats")
        lines = {line.split()[0]: line.split()[1:] for line in out.splitlines()[1:]}
        self.assertEqual(lines["haiku"], ["1", "0", "1", "0%"])
        self.assertEqual(lines["sonnet"], ["3", "2", "1", "67%"])
        self.assertEqual(lines["opus"], ["1", "1", "0", "100%"])
        self.assertLess(out.index("haiku"), out.index("sonnet"))
        self.assertLess(out.index("sonnet"), out.index("opus"))

        filtered = self.mth("plan", "stats", "--spec", other)
        self.assertIn("opus", filtered)
        self.assertNotIn("haiku", filtered)

    def test_stats_counts_verify_runs_end_to_end(self):
        # verifies: SPEC-0002/AC-07
        manifests = self.wave_one()
        self.verify(manifests, ok=True)
        self.verify(manifests, ok=True)  # same manifests: same attempts
        out = self.mth("plan", "stats", "--spec", SPEC_ID)
        lines = {line.split()[0]: line.split()[1:] for line in out.splitlines()[1:]}
        self.assertEqual(lines["haiku"], ["1", "1", "0", "100%"])
        self.assertEqual(lines["sonnet"], ["1", "1", "0", "100%"])

    def test_no_trace_and_unreadable_lines(self):
        # verifies: SPEC-0002/AC-08
        self.assertIn("No hay datos", self.mth("plan", "stats"))
        self.write_trace(["{broken", "[1, 2]", json.dumps({"event": "plan.task", "task": 3}),
                          self.event("T-01", "haiku", "ok", "a")])
        out = self.mth("plan", "stats")
        self.assertIn("3 líneas ilegibles de la traza ignoradas", out)
        self.assertIn("haiku", out)

    def test_readable_trace_has_no_warning(self):
        # verifies: SPEC-0002/AC-08
        self.write_trace([self.event("T-01", "haiku", "ok", "a")])
        out = self.mth("plan", "stats")
        self.assertIn("haiku", out)
        self.assertNotIn("ilegibles", out)


if __name__ == "__main__":
    unittest.main()
