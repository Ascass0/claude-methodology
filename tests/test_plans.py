"""Tests of the agreed plans module (SPEC-0023, ADR-0021): format, numbering, states and the gate."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import plans  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

HEADER = "# PLAN-0001 · Demo\n\n- Estado: {state}\n- Fecha: 2026-11-26\n- Acordado con: —\n- Refs: —\n- Rama: {branch}\n\n"
BODY = """## Idea

Algo.

## Decisiones acordadas

1. Hecho.

## Fuera de alcance

- Nada.

## Tareas

| Tarea | Oleada | Agente sugerido | Depende de | Ficheros | Hecho cuando |
|---|---|---|---|---|---|
{rows}
## Agentes a instalar

Ninguno.

## Verificación y cierre

- Tests.

## Riesgos

- Ninguno.

## Preguntas abiertas

{questions}

## Registro de ejecución

| Tarea | Agente real | Modelo | Resultado | Desviación y motivo |
|---|---|---|---|---|
"""
ROWS = ("| T-01 | 1 | hilo principal | — | `src/a.py` | Hecho |\n"
        "| T-02 | 2 | `verificador` | T-01 | `src/b.py` | Hecho |\n")
ROADMAP = """## Idea

Algo.

## Decisiones acordadas

1. Hecho.

## Fases

| Fase | Qué |
|---|---|
| 1 | Algo |

## Fuera de alcance

- Nada.

## Riesgos

- Ninguno.

## Preguntas abiertas

Ninguna.

## Registro de ejecución
"""


def text(state: str = "borrador", rows: str = ROWS, questions: str = "Ninguna.", branch: str = "—") -> str:
    return HEADER.format(state=state, branch=branch) + BODY.format(rows=rows, questions=questions)


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path


class FormatTests(TempDir):
    def test_header_is_parsed(self):
        # verifies: SPEC-0023/AC-03
        path = self.write("PLAN-0001-demo.md", text("en curso", branch="`feat/x`, `fix/y` (nota con `un comando`)"))
        plan = plans.parse(path.read_text(), path)
        self.assertEqual((plan.ident, plan.slug, plan.state, plan.title), ("PLAN-0001", "demo", "en curso", "Demo"))
        self.assertEqual(plan.branches, ("feat/x", "fix/y"))

    def test_unreadable_or_malformed_files_fail_naming_the_file(self):
        # verifies: SPEC-0023/AC-12
        # verifies: SPEC-0023/FM-03
        cases = {"PLAN-0001-demo.md": "",
                 "plan-1.md": text(),
                 "PLAN-0002-demo.md": text(),  # title says PLAN-0001
                 "PLAN-0003-demo.md": text().replace("Estado: borrador", "Estado: casi")}
        for name, content in cases.items():
            path = self.write(name, content)
            with self.assertRaises(MthError, msg=name) as ctx:
                plans.read(path)
            self.assertIn(name, ctx.exception.message)
        with self.assertRaises(MthError) as ctx:
            plans.read(self.dir / "PLAN-0009-ausente.md")
        self.assertIn("PLAN-0009-ausente.md", ctx.exception.message)

    def test_listing_separates_readable_from_broken(self):
        # verifies: SPEC-0023/AC-03
        self.write("PLAN-0001-demo.md", text())
        self.write("PLAN-0002-roto.md", "nada")
        found, broken = plans.listing(self.dir)
        self.assertEqual([p.ident for p in found], ["PLAN-0001"])
        self.assertEqual([p.name for p in broken], ["PLAN-0002-roto.md"])

    def test_find_by_id(self):
        # verifies: SPEC-0023/AC-03
        self.write("PLAN-0004-demo.md", text())
        self.assertEqual(plans.find(self.dir, "PLAN-0004").name, "PLAN-0004-demo.md")
        for bad in ("PLAN-4", "PLAN-0005"):
            with self.assertRaises(MthError):
                plans.find(self.dir, bad)

    def test_two_files_with_the_same_number_fail_naming_both(self):
        # verifies: SPEC-0023/AC-03
        # verifies: SPEC-0023/FM-14
        self.write("PLAN-0004-uno.md", text())
        self.write("PLAN-0004-dos.md", text())
        with self.assertRaises(MthError) as ctx:
            plans.find(self.dir, "PLAN-0004")
        self.assertIn("PLAN-0004-uno.md", ctx.exception.message)
        self.assertIn("PLAN-0004-dos.md", ctx.exception.message)

    def test_raw_reads_a_plan_that_does_not_follow_the_format(self):
        # verifies: SPEC-0023/AC-03
        self.assertEqual(plans.raw(self.write("PLAN-0001-roto.md", "basura")), "basura")

    def test_a_plan_over_the_size_limit_is_unreadable(self):
        # verifies: SPEC-0023/AC-12
        # verifies: SPEC-0023/FM-13
        path = self.write("PLAN-0001-demo.md", text() + "x" * plans.MAX_BYTES)
        with self.assertRaises(MthError) as ctx:
            plans.read(path)
        self.assertIn("PLAN-0001-demo.md", ctx.exception.message)
        self.assertEqual(plans.listing(self.dir)[1], [path])


class CreateTests(TempDir):
    def test_numbers_follow_the_highest_and_never_overwrite(self):
        # verifies: SPEC-0023/AC-02
        first = plans.create(self.dir, "uno", "Uno", date(2026, 11, 26))
        self.assertEqual(first.name, "PLAN-0001-uno.md")
        self.assertIn("- Estado: borrador", first.read_text())
        self.write("PLAN-0007-viejo.md", "x")
        self.assertEqual(plans.create(self.dir, "dos", "Dos").name, "PLAN-0008-dos.md")
        with self.assertRaises(MthError):
            plans.create(self.dir, "Mal Slug", "x")

    def test_a_number_taken_in_the_meantime_moves_to_the_next(self):
        # verifies: SPEC-0023/AC-02
        # verifies: SPEC-0023/FM-04
        self.write("PLAN-0001-uno.md", text())
        with mock.patch.object(Path, "glob", return_value=iter([])):  # stale listing: another session wrote first
            created = plans.create(self.dir, "uno", "Uno")
        self.assertEqual(created.name, "PLAN-0002-uno.md")
        self.assertTrue((self.dir / "PLAN-0001-uno.md").read_text().startswith("# PLAN-0001"))

    def test_a_title_cannot_inject_header_fields(self):
        # verifies: SPEC-0023/AC-02
        # verifies: SPEC-0023/FM-12
        for title in ("a\n- Estado: en curso", "a\r- Rama: `feat/y`", "", "   ", "x" * (plans.MAX_TITLE + 1), "a\x00b"):
            with self.assertRaises(MthError, msg=repr(title)):
                plans.create(self.dir, "demo", title)
        self.assertEqual(list(self.dir.glob("PLAN-*")), [])
        self.assertEqual(plans.parse(plans.create(self.dir, "demo", "Título válido").read_text(), self.dir / "PLAN-0001-demo.md").state, "borrador")

    def test_header_fields_are_read_only_from_the_header(self):
        # verifies: SPEC-0023/AC-02
        path = self.write("PLAN-0001-demo.md", text("borrador").replace("## Idea\n", "## Idea\n\n- Estado: acordado\n- Rama: `feat/y`\n"))
        plan = plans.read(path)[0]
        self.assertEqual((plan.state, plan.branches), ("borrador", ()))

    def test_the_template_has_every_section_but_is_not_ready_to_agree(self):
        # verifies: SPEC-0023/AC-04
        created = plans.create(self.dir, "uno", "Uno")
        problems = plans.check(created.read_text())
        self.assertTrue(problems)
        self.assertFalse([p for p in problems if "falta la sección" in p.message])


class CheckTests(unittest.TestCase):
    def messages(self, content: str) -> list[str]:
        return [p.message for p in plans.check(content)]

    def test_valid_plans_pass(self):
        # verifies: SPEC-0023/AC-04
        self.assertEqual(self.messages(text()), [])
        self.assertEqual(self.messages(HEADER.format(state="acordado", branch="—") + ROADMAP), [])
        read_only = "| T-01 | 1 | `explorador-specs` | — | solo lectura | Hecho |\n| T-02 | 1 | hilo principal | — | — | Hecho |\n"
        self.assertEqual(self.messages(text(rows=read_only)), [])

    def test_missing_sections_and_open_questions_are_listed(self):
        # verifies: SPEC-0023/AC-04
        # verifies: SPEC-0023/FM-06
        self.assertIn("falta la sección «Riesgos»", self.messages(text().replace("## Riesgos", "## Otra")))
        open_ = self.messages(text(questions="1. ¿Seguimos?\n2. ¿Cómo?"))
        self.assertEqual(sum("pregunta abierta sin resolver" in m for m in open_), 2)
        self.assertTrue([m for m in self.messages(text(questions="")) if "vacía" in m])

    def test_sections_out_of_order_are_rejected(self):
        # verifies: SPEC-0023/AC-04
        swapped = text().replace("## Riesgos", "## TEMP").replace("## Fuera de alcance", "## Riesgos").replace("## TEMP", "## Fuera de alcance")
        self.assertTrue([m for m in self.messages(swapped) if "orden" in m])

    def test_task_graph_problems(self):
        # verifies: SPEC-0023/AC-05
        # verifies: SPEC-0023/FM-07
        def bad(rows: str) -> str:
            return " ".join(self.messages(text(rows=rows)))

        self.assertIn("repetido", bad("| T-01 | 1 | a | — | `a.py` | h |\n| T-01 | 2 | a | — | `b.py` | h |\n"))
        self.assertIn("no existe", bad("| T-01 | 1 | a | T-09 | `a.py` | h |\n"))
        self.assertIn("oleada posterior", bad("| T-01 | 1 | a | — | `a.py` | h |\n| T-02 | 1 | a | T-01 | `b.py` | h |\n"))
        self.assertIn("ciclo", bad("| T-01 | 2 | a | T-02 | `a.py` | h |\n| T-02 | 1 | a | T-01 | `b.py` | h |\n"))
        self.assertIn("comparten ficheros", bad("| T-01 | 1 | a | — | `src/*.py` | h |\n| T-02 | 1 | a | — | `src/a.py` | h |\n"))
        self.assertIn("inválido", bad("| X-1 | 1 | a | — | `a.py` | h |\n"))
        self.assertIn("ruta no permitida", bad("| T-01 | 1 | a | — | `../a.py` | h |\n"))
        self.assertEqual(self.messages(text(rows="| T-01 | 1 | a | — | `a.py` | h |\n| T-02 | 2 | a | T-01 | `a.py` | h |\n")), [])
        many = "".join(f"| T-{i:02d} | {i} | a | — | `f{i}.py` | h |\n" for i in range(1, 52))
        self.assertIn("más de 50", bad(many))

    def test_problems_carry_their_line(self):
        # verifies: SPEC-0023/AC-05
        found = plans.check(text(rows="| T-01 | 1 | a | T-09 | `a.py` | h |\n"))
        self.assertTrue(found and found[0].line > 0)
        self.assertIn(f"línea {found[0].line}", str(found[0]))


class StateTests(TempDir):
    def test_agree_validates_stamps_the_date_and_leaves_invalid_plans_untouched(self):
        # verifies: SPEC-0023/AC-04
        # verifies: SPEC-0023/FM-05
        good = self.write("PLAN-0001-demo.md", text())
        plan = plans.transition(good, "acordado", date(2026, 12, 1))
        self.assertEqual(plan.state, "acordado")
        self.assertIn("la persona que desarrolla (2026-12-01)", good.read_text())
        bad = self.write("PLAN-0002-demo.md", text(questions="1. ¿Seguimos?").replace("PLAN-0001", "PLAN-0002"))
        before = bad.read_text()
        with self.assertRaises(MthError) as ctx:
            plans.transition(bad, "acordado")
        self.assertIn("pregunta abierta", ctx.exception.message)
        self.assertEqual(bad.read_text(), before)

    def test_allowed_transitions_and_rejections_name_the_state(self):
        # verifies: SPEC-0023/AC-07
        # verifies: SPEC-0023/FM-09
        path = self.write("PLAN-0001-demo.md", text("acordado"))
        self.assertEqual(plans.transition(path, "ejecutado").state, "ejecutado")
        with self.assertRaises(MthError) as ctx:
            plans.transition(path, "acordado")
        self.assertIn("«ejecutado»", ctx.exception.message)
        for state, target in (("borrador", "ejecutado"), ("borrador", "en curso"), ("ejecutado", "abandonado")):
            other = self.write("PLAN-0001-demo.md", text(state))
            with self.assertRaises(MthError, msg=f"{state}→{target}"):
                plans.transition(other, target)
        self.assertEqual(plans.transition(self.write("PLAN-0001-demo.md", text("en curso")), "abandonado").state, "abandonado")
        self.assertEqual(plans.transition(self.write("PLAN-0001-demo.md", text("borrador")), "abandonado").state, "abandonado")

    def test_add_branch_moves_agreed_to_in_progress_and_is_idempotent(self):
        # verifies: SPEC-0023/AC-09
        path = self.write("PLAN-0001-demo.md", text("acordado"))
        self.assertEqual(plans.add_branch(path, "feat/x").state, "en curso")
        again = plans.add_branch(path, "feat/x")
        self.assertEqual(again.branches, ("feat/x",))
        self.assertEqual(plans.add_branch(path, "fix/y").branches, ("feat/x", "fix/y"))
        self.assertEqual(plans.read(path)[0].state, "en curso")


class GateTests(TempDir):
    def test_a_new_branch_needs_an_agreed_or_running_plan(self):
        # verifies: SPEC-0023/AC-09
        # verifies: SPEC-0023/FM-01
        # verifies: SPEC-0023/FM-02
        with self.assertRaises(MthError) as ctx:
            plans.for_start(self.dir, None, "feat")
        self.assertIn("--plan", ctx.exception.message)
        self.assertIn("mth-plan", ctx.exception.hint)
        for state in ("borrador", "ejecutado", "abandonado"):
            self.write("PLAN-0001-demo.md", text(state))
            with self.assertRaises(MthError, msg=state) as ctx:
                plans.for_start(self.dir, "PLAN-0001", "feat")
            self.assertIn(f"«{state}»", ctx.exception.message)
        for state in ("acordado", "en curso"):
            self.write("PLAN-0001-demo.md", text(state))
            self.assertEqual(plans.for_start(self.dir, "PLAN-0001", "feat").name, "PLAN-0001-demo.md")
        with self.assertRaises(MthError):
            plans.for_start(self.dir, "PLAN-0042", "feat")

    def test_integration_needs_a_running_plan_that_lists_the_branch(self):
        # verifies: SPEC-0023/AC-10
        # verifies: SPEC-0023/FM-08
        with self.assertRaises(MthError):
            plans.for_branch(self.dir / "inexistente", "feat/x")  # a fresh clone has no plans directory
        self.write("PLAN-0001-demo.md", text("en curso", branch="`feat/x`"))
        self.assertEqual(plans.for_branch(self.dir, "feat/x").ident, "PLAN-0001")
        for state in ("acordado", "borrador", "ejecutado"):
            self.write("PLAN-0001-demo.md", text(state, branch="`feat/x`"))
            with self.assertRaises(MthError, msg=state):
                plans.for_branch(self.dir, "feat/x")
        self.write("PLAN-0001-demo.md", text("en curso", branch="`feat/otra`"))
        with self.assertRaises(MthError):
            plans.for_branch(self.dir, "feat/x")

    def test_the_running_rule_is_one_function(self):
        # verifies: SPEC-0023/AC-10
        found = [plans.Plan("PLAN-0001", "a", self.dir, "en curso", "A", ("feat/x",)),
                 plans.Plan("PLAN-0002", "b", self.dir, "acordado", "B", ("feat/y",))]
        self.assertEqual(plans.running_for(found, "feat/x").ident, "PLAN-0001")
        self.assertIsNone(plans.running_for(found, "feat/y"))

    def test_a_corrupt_plan_never_counts_and_is_named(self):
        # verifies: SPEC-0023/AC-12
        self.write("PLAN-0001-roto.md", "basura")
        with self.assertRaises(MthError) as ctx:
            plans.for_branch(self.dir, "feat/x")
        self.assertIn("PLAN-0001-roto.md", ctx.exception.message)
        self.write("PLAN-0002-demo.md", text("en curso", branch="`feat/x`").replace("PLAN-0001", "PLAN-0002"))
        self.assertEqual(plans.for_branch(self.dir, "feat/x").ident, "PLAN-0002")  # another plan's damage does not block


if __name__ == "__main__":
    unittest.main()
