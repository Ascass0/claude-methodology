"""Tests of the adoption triage: deduce, default or ask (SPEC-0015, ADR-0011)."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import adoption, cli, lang, review, survey  # noqa: E402
from mthlib.config import DEFAULTS, parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402
from test_adoption import RepoCase  # noqa: E402

SKILL = HERE.parent / "plugins" / "methodology" / "skills" / "mth-init"
SPANISH = "El proyecto es para la gente que trabaja con el código de la casa y que lo usa en el día a día. " * 6


def inventory(profile: str = "existing", **signals) -> survey.Survey:
    """An inventory built from signals alone (no repository)."""
    found = {"files": 500, "branches": ["main"], "upstream": profile == "fork", "tags": None, "specs": [],
             "adrs": [], "agents": [], "agent_collisions": [], "claude_dirs": [], "instructions": [],
             "commit_hook": False, "hook_managers": [], "release_tools": [], "version_files": [],
             "ci": False, "tests": [], "language": "es", "forge": "github",
             "integration": {"candidates": [], "working": 0, "from_candidate": 0}, **signals}
    return survey.Survey(profile, found, survey.questions(profile, found))


def outcomes(inv: survey.Survey) -> dict[str, str]:
    return {q["id"]: q["outcome"] for q in inv.questions}


class ClassificationTests(unittest.TestCase):
    def test_every_question_has_an_outcome_in_dependency_order(self):
        # verifies: SPEC-0015/AC-01
        inv = inventory("methodology", commit_hook=True, adrs=[{"path": "docs/adr", "files": 3, "pattern": None}],
                        instructions=["CLAUDE.md"], forge="other")
        for question in inv.questions:
            self.assertIn(question["outcome"], survey.OUTCOMES)
            if question["outcome"] == survey.DECISION:
                self.assertNotIn("answer", question)
            else:
                self.assertIn("answer", question)
                self.assertTrue(question["basis"])
        ids = [q["id"] for q in inv.questions]
        self.assertEqual(ids, sorted(ids, key=survey.QUESTIONS.index))
        self.assertEqual(inv.asked()[:2], ["instrucciones", "autonomia"])
        self.assertTrue(all(inv.question(q)["outcome"] == survey.DECISION for q in inv.asked()))
        self.assertEqual(json.loads(inv.to_json())["questions"][0]["outcome"], survey.DECISION)

    def test_integration_branch_rule(self):
        # verifies: SPEC-0015/AC-02
        def branches(candidates, working, from_candidate):
            return inventory(integration={"candidates": candidates, "working": working,
                                          "from_candidate": from_candidate}).question("ramas")
        single = branches(["dev"], 3, 3)
        self.assertEqual((single["outcome"], single["answer"]), (survey.DEDUCED, {"option": "usar", "branch": "dev"}))
        self.assertIn("3 ramas de trabajo", single["basis"])
        none = branches([], 0, 0)
        self.assertEqual((none["outcome"], none["answer"], none["options"]), (survey.DEFAULT, {"option": "crear"}, ["crear"]))
        for candidates, working, from_candidate in ((["dev", "develop"], 2, 2), (["dev"], 0, 0), (["dev"], 3, 2)):
            with self.subTest(candidates=candidates, working=working, from_candidate=from_candidate):
                asked = branches(candidates, working, from_candidate)
                self.assertEqual(asked["outcome"], survey.DECISION)
                self.assertEqual(asked["options"], ["usar", "crear"])

    def test_foreign_commit_hook_is_always_chained(self):
        # verifies: SPEC-0015/AC-03
        for signal in ({"commit_hook": True}, {"hook_managers": [".husky"]}):
            with self.subTest(signal=signal):
                inv = inventory("methodology", **signal)
                question = inv.question("commits")
                self.assertEqual((question["outcome"], question["answer"], question["options"]),
                                 (survey.DEDUCED, {"option": "encadenar"}, ["encadenar"]))
                self.assertNotIn("sustituir", adoption.OPTIONS["commits"])
                with self.assertRaises(MthError) as ctx:
                    adoption.validate(inv, {**self.decisions(inv), "commits": {"option": "sustituir"}})
                self.assertIn("opción desconocida 'sustituir'", ctx.exception.message)

    def decisions(self, inv: survey.Survey) -> dict:
        defaults = {"autonomia": {"option": "full"}, "revisores": {"option": "agentes", "agents": []},
                    "instrucciones": {"option": "metodologia"}, "tests": {"option": "ninguno"},
                    "decisiones": {"option": "archivar"}, "versiones": {"option": "continuar"},
                    "ci": {"option": "sin-ci"}}
        return {q: defaults[q] for q in inv.asked()}

    def test_without_github_nothing_that_needs_it_is_offered(self):
        # verifies: SPEC-0015/AC-04
        other = inventory("existing", forge="other", tags={"prefix": "v", "count": 2})
        self.assertEqual((other.question("ci")["outcome"], other.question("ci")["answer"], other.question("ci")["options"]),
                         (survey.DEDUCED, {"option": "sin-ci"}, ["sin-ci"]))
        releases = other.question("versiones")
        self.assertEqual((releases["outcome"], releases["answer"], releases["options"]), (survey.DEDUCED, None, []))
        for qid, answer in (("ci", {"option": "crear"}), ("versiones", {"option": "continuar"}),
                            ("versiones", {"option": "prefijo", "tag_prefix": "r"})):
            with self.subTest(qid=qid, answer=answer), self.assertRaises(MthError) as ctx:
                adoption.validate(other, {**self.decisions(other), qid: answer})
            self.assertIn("no funciona con este repo", ctx.exception.message)
        github = inventory("existing", tags={"prefix": "v", "count": 2})
        self.assertEqual([github.question(q)["outcome"] for q in ("ci", "versiones")], [survey.DECISION] * 2)
        self.assertNotIn("options", github.question("ci"))
        adoption.validate(github, {**self.decisions(github), "ci": {"option": "crear"}})

    def test_test_command_comes_from_the_project_entry_point(self):
        # verifies: SPEC-0015/AC-05
        for candidates, expected in ((["pytest", "make test"], "make test"), (["npm test", "just test"], "just test"),
                                     (["make test", "just test"], "make test")):
            with self.subTest(candidates=candidates):
                question = inventory(tests=candidates).question("tests")
                self.assertEqual((question["outcome"], question["answer"]),
                                 (survey.DEDUCED, {"option": "comando", "command": expected}))
        for candidates in (["pytest", "npm test"], []):
            with self.subTest(candidates=candidates):
                self.assertEqual(inventory(tests=candidates).question("tests")["outcome"], survey.DECISION)

    def test_language_models_and_scope(self):
        # verifies: SPEC-0015/AC-06
        self.assertEqual((inventory(language="en").question("idioma")["outcome"],
                          inventory(language="en").question("idioma")["answer"]), (survey.DEDUCED, {"option": "en"}))
        unknown = inventory("new", language="unknown", files=0)
        self.assertEqual((unknown.question("idioma")["outcome"], unknown.question("idioma")["answer"]),
                         (survey.DEFAULT, {"option": "es"}))
        self.assertEqual(unknown.question("modelos")["outcome"], survey.DEFAULT)
        self.assertIsNone(unknown.question("alcance"))
        for profile in ("existing", "methodology", "fork"):
            with self.subTest(profile=profile):
                scope = inventory(profile).question("alcance")
                self.assertEqual((scope["outcome"], scope["answer"]), (survey.DEDUCED, {"option": "gradual"}))


class AnswersTests(unittest.TestCase):
    def test_only_decisions_are_required_and_anything_can_be_overridden(self):
        # verifies: SPEC-0015/AC-07
        inv = inventory(language="en", forge="other", tags={"prefix": "v", "count": 1}, tests=["make test"])
        self.assertEqual(inv.asked(), ["autonomia", "revisores"])
        answers = {"autonomia": {"option": "supervised"}, "revisores": {"option": "agentes", "agents": []}}
        adoption.validate(inv, answers)
        template = (lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
        plan = adoption.build(template, inv, answers, "main", "a" * 40)
        by_question = {d.question: d for d in plan.decisions}
        self.assertEqual(plan.data["language"]["docs"], "en")
        self.assertEqual(plan.data["trace"]["legacy_base"], "a" * 40)
        self.assertFalse(plan.data["ci"]["required"])
        self.assertEqual((by_question["idioma"].outcome, by_question["autonomia"].outcome),
                         (survey.DEDUCED, survey.DECISION))
        self.assertEqual((by_question["versiones"].option, by_question["versiones"].outcome), ("ninguna", survey.DEDUCED))
        self.assertEqual(by_question["modelos"].outcome, survey.DEFAULT)
        # An explicit answer replaces the deduced value and is recorded as a decision.
        answers["idioma"] = {"option": "es"}
        adoption.validate(inv, answers)
        plan = adoption.build(template, inv, answers, "main", "a" * 40)
        self.assertEqual(plan.data["language"]["docs"], "es")
        self.assertEqual({d.question: d.outcome for d in plan.decisions}["idioma"], survey.DECISION)
        for bad, expected in (({"specs": {"option": "archivar"}}, "no está en el inventario"),
                              ({"colision": {"option": "mantener"}}, "no está en el inventario"),
                              ({"ramas": {"option": "usar", "branch": "dev"}}, "no funciona con este repo")):
            with self.subTest(expected=expected), self.assertRaises(MthError) as ctx:
                adoption.validate(inv, {**answers, **bad})
            self.assertIn(expected, ctx.exception.message)
        with self.assertRaises(MthError) as ctx:
            adoption.validate(inv, {"revisores": answers["revisores"]})
        self.assertIn("autonomia: falta la respuesta", ctx.exception.message)

    def test_adoption_adr_records_the_outcome_of_every_question(self):
        # verifies: SPEC-0015/AC-09
        inv = inventory("methodology", language="en", forge="other", commit_hook=True, tests=["make test"])
        answers = {"autonomia": {"option": "full"}, "revisores": {"option": "agentes", "agents": []}}
        template = (lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
        plan = adoption.build(template, inv, answers, "main", "a" * 40)
        for code in ("es", "en"):
            text = adoption.adr_text("ADR-0001", inv, plan, lang.vocabulary(code))
            with self.subTest(code=code):
                for question in inv.questions:
                    row = next(line for line in text.splitlines() if line.startswith(f"| `{question['id']}` |"))
                    self.assertIn(f"| `{question['outcome']}` |", row)
        self.assertIn("| `commits` | `deducida` | `encadenar` | hooks.commit_msg = chain |", text)


class OfferedOptionsTests(unittest.TestCase):
    """What the interview offers is what the plugin does (ADR-0011, point 3)."""

    SAMPLES = {
        ("alcance", "gradual"): {}, ("alcance", "completa"): {},
        ("ramas", "usar"): {"branch": "dev"}, ("ramas", "crear"): {},
        ("commits", "encadenar"): {},
        ("versiones", "continuar"): {}, ("versiones", "prefijo"): {"tag_prefix": "r"},
        ("specs", "mapear"): {"path": "rfcs", "kind": "RFC", "pattern": "RFC-\\d{3}"},
        ("specs", "convertir"): {}, ("specs", "archivar"): {},
        ("decisiones", "mapear"): {"path": "docs/adr", "kind": "ADR", "pattern": "ADR-\\d{3}"},
        ("decisiones", "convertir"): {}, ("decisiones", "archivar"): {},
        ("tests", "comando"): {"command": "make test"}, ("tests", "ninguno"): {},
        ("revisores", "agentes"): {"agents": ["api-reviewer"], "paths": {"api-reviewer": ["api/**"]}},
        ("colision", "renombrar"): {"renames": {"verificador": "verificador-repo"}}, ("colision", "mantener"): {},
        ("instrucciones", "metodologia"): {}, ("instrucciones", "repo"): {"exceptions": ["x"]},
        ("autonomia", "full"): {}, ("autonomia", "until-pr"): {}, ("autonomia", "supervised"): {},
        ("idioma", "es"): {}, ("idioma", "en"): {},
        ("ci", "sin-ci"): {}, ("ci", "crear"): {},
        ("modelos", "equilibrado"): {}, ("modelos", "calidad"): {}, ("modelos", "ahorro"): {},
    }

    def test_every_option_applies_and_leaves_a_valid_configuration(self):
        # verifies: SPEC-0015/AC-10
        offered = {(q, o) for q, options in adoption.OPTIONS.items() for o in options}
        self.assertEqual(offered, set(self.SAMPLES), "every option needs a sample here")
        template = (lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
        for (qid, option), params in self.SAMPLES.items():
            with self.subTest(question=qid, option=option):
                inv = inventory("methodology", integration={"candidates": ["dev"], "working": 0, "from_candidate": 0},
                                agents=["api-reviewer", "verificador"], agent_collisions=["verificador"],
                                tags={"prefix": "v", "count": 1})
                if inv.question(qid) is None:
                    inv.questions.append({"id": qid, "evidence": "x", "outcome": survey.DECISION})
                answers = {**{q: self.decision(q) for q in inv.asked() if q != qid}, qid: {"option": option, **params}}
                adoption.validate(inv, answers)
                plan = adoption.build(template, inv, answers, "main", "a" * 40)
                parse(Path("."), adoption.dump_toml(plan.data))
                self.assertTrue(next(d for d in plan.decisions if d.question == qid).effect)

    @staticmethod
    def decision(qid: str) -> dict:
        return {"instrucciones": {"option": "metodologia"}, "autonomia": {"option": "full"},
                "revisores": {"option": "agentes", "agents": []}, "colision": {"option": "mantener"},
                "specs": {"option": "archivar"}, "decisiones": {"option": "archivar"},
                "versiones": {"option": "continuar"}, "ramas": {"option": "crear"},
                "tests": {"option": "ninguno"}, "ci": {"option": "sin-ci"}}[qid]

    def test_texts_only_promise_commands_and_keys_that_exist(self):
        # verifies: SPEC-0015/AC-10
        commands = set(cli._parser()._subparsers._group_actions[0].choices)
        for name in ("SKILL.md", "preguntas.md"):
            text = (SKILL / name).read_text(encoding="utf-8")
            for command in re.findall(r"`mth ([a-z-]+)", text):
                with self.subTest(file=name, command=command):
                    self.assertIn(command, commands)
            for key in set(re.findall(r"`([a-z_]+(?:\.[A-Za-z_]+)+)`", text)):
                table, _, rest = key.partition(".")
                if table not in DEFAULTS or table in ("ids", "agents"):
                    continue  # not a configuration key, or a table with dynamic names
                with self.subTest(file=name, key=key):
                    self.assertIn(rest.split(".")[0], DEFAULTS[table])

    def test_paths_limit_a_reviewer_to_an_area(self):
        # verifies: SPEC-0015/AC-10
        inv = inventory("methodology", agents=["api-reviewer"], forge="other", tests=["make test"])
        answers = {"revisores": {"option": "agentes", "agents": ["api-reviewer"],
                                 "paths": {"api-reviewer": ["api/**", "!api/docs/**"]}},
                   "instrucciones": {"option": "metodologia"}, "autonomia": {"option": "full"}}
        adoption.validate(inv, {q: a for q, a in answers.items() if q in inv.asked()})
        plan = adoption.build((lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8"), inv,
                              {q: a for q, a in answers.items() if q in inv.asked()}, "main", "a" * 40)
        cfg = parse(Path("."), adoption.dump_toml(plan.data))
        agents, paths = cfg["review"]["agents"], cfg["review"]["paths"]
        self.assertEqual(paths, {"api-reviewer": ["api/**", "!api/docs/**"]})
        self.assertEqual(review.required(agents, paths, ["api/users.py"]), ["verificador", "api-reviewer"])
        self.assertEqual(review.required(agents, paths, ["web/app.py", "api/docs/x.md"]), ["verificador"])
        bad = {**answers, "revisores": {"option": "agentes", "agents": [], "paths": {"api-reviewer": ["api/**"]}}}
        bad_plan = adoption.build((lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8"), inv,
                                  {q: a for q, a in bad.items() if q in inv.asked()}, "main", "a" * 40)
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), adoption.dump_toml(bad_plan.data))
        self.assertIn("review.paths.api-reviewer", ctx.exception.message)
        empty = {**answers, "revisores": {**answers["revisores"], "paths": {"api-reviewer": []}}}
        empty_plan = adoption.build((lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8"), inv,
                                    {q: a for q, a in empty.items() if q in inv.asked()}, "main", "a" * 40)
        with self.assertRaises(MthError) as ctx:
            parse(Path("."), adoption.dump_toml(empty_plan.data))
        self.assertIn("review.paths.api-reviewer", ctx.exception.message)


class SignalTests(RepoCase):
    def test_integration_signal_and_justfile(self):
        # verifies: SPEC-0015/AC-02, SPEC-0015/AC-05
        self.write("README.md", SPANISH)
        self.write("justfile", "set shell := ['sh', '-c']\n\ntest *args:\n\tpytest\n")
        self.commit()
        self.assertEqual(self.inventory().signals["tests"], ["just test"])
        remote = self.root.parent / (self.root.name + "-remote.git")
        self.git("init", "-q", "--bare", "-b", "main", str(remote))
        self.addCleanup(lambda: __import__("shutil").rmtree(remote, ignore_errors=True))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-b", "dev")
        self.write("src/a.py", "a = 1\n")
        self.commit()
        self.git("push", "-q", "origin", "dev")
        for name in ("feat/a", "feat/b"):
            self.git("checkout", "-q", "-b", name, "dev")
            self.write(f"src/{name[-1]}.py", "x = 1\n")
            self.commit()
            self.git("push", "-q", "origin", name)
        self.git("checkout", "-q", "-b", "fix/from-main", "main")
        self.write("src/c.py", "c = 1\n")
        self.commit()
        self.git("push", "-q", "origin", "fix/from-main")
        self.git("fetch", "-q", "origin")
        self.assertEqual(self.inventory().signals["integration"],
                         {"candidates": ["dev"], "working": 3, "from_candidate": 2})
        self.git("push", "-q", "origin", "--delete", "fix/from-main")
        self.git("fetch", "-q", "--prune", "origin")
        self.assertEqual(self.inventory().question("ramas")["outcome"], survey.DEDUCED)
        # Once dev is part of main, branching from it no longer tells anything: ask.
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-edit", "dev")
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")
        self.assertEqual(self.inventory().signals["integration"]["from_candidate"], 0)
        self.assertEqual(self.inventory().question("ramas")["outcome"], survey.DECISION)


class UnreadableForkPointTests(RepoCase):
    def test_a_branch_without_common_history_does_not_count(self):
        # verifies: SPEC-0015/AC-02
        self.write("README.md", SPANISH)
        self.commit()
        remote = self.root.parent / (self.root.name + "-remote.git")
        self.addCleanup(lambda: __import__("shutil").rmtree(remote, ignore_errors=True))
        self.git("init", "-q", "--bare", "-b", "main", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-b", "dev")
        self.write("src/a.py", "a = 1\n")
        self.commit()
        self.git("push", "-q", "origin", "dev")
        self.git("checkout", "-q", "--orphan", "feat/orphan")  # merge-base with dev fails
        self.commit()
        self.git("push", "-q", "origin", "feat/orphan")
        self.git("fetch", "-q", "origin")
        self.assertEqual(self.inventory().signals["integration"],
                         {"candidates": ["dev"], "working": 1, "from_candidate": 0})
        self.assertEqual(self.inventory().question("ramas")["outcome"], survey.DECISION)


class BoundedSignalTests(RepoCase):
    def test_more_branches_than_the_limit_never_confirm_the_rule(self):
        # verifies: SPEC-0015/AC-02
        self.write("README.md", SPANISH)
        self.commit()
        remote = self.root.parent / (self.root.name + "-remote.git")
        self.addCleanup(lambda: __import__("shutil").rmtree(remote, ignore_errors=True))
        self.git("init", "-q", "--bare", "-b", "main", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-b", "dev")
        self.write("src/a.py", "a = 1\n")
        self.commit()
        total = survey._MAX_WORKING_BRANCHES + 2
        for n in range(total):
            self.git("branch", f"feat/b{n:03d}", "dev")
        self.git("push", "-q", "origin", "dev", *[f"feat/b{n:03d}" for n in range(total)])
        self.git("fetch", "-q", "origin")
        signal = self.inventory().signals["integration"]
        self.assertEqual((signal["working"], signal["from_candidate"]), (total, survey._MAX_WORKING_BRANCHES))
        self.assertEqual(self.inventory().question("ramas")["outcome"], survey.DECISION)


class RealCaseTests(test_mth.EndToEndTests):
    """The adoption that motivated ADR-0011: GitLab, `dev`, a foreign hook, Makefile, 42 ADR, own CLAUDE.md."""

    test_full_flow = None  # inherited end-to-end flow: not part of this case

    def setUp(self):
        super().setUp()
        write = lambda rel, text: test_mth._write(self.work / rel, text)  # noqa: E731
        write("README.md", SPANISH)
        write("Makefile", "test:\n\tpytest\n")
        write("tests/test_app.py", "def test_ok():\n    pass\n")
        write("src/app.py", "print('x')\n")
        write("CLAUDE.md", "Pregunta antes de hacer commit.\nNunca uses squash.\n")
        for n in range(1, 43):
            write(f"docs/adr/ADR-{n:03d}-decision.md", f"# ADR-{n:03d} · Decisión {n}\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "legacy content")
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-b", "dev")
        write("src/dev.py", "x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "dev work")
        self.git("push", "-q", "origin", "dev")
        for name in ("feat/login", "fix/typo"):
            self.git("checkout", "-q", "-b", name, "dev")
            write(f"src/{name.split('/')[1]}.py", "y = 1\n")
            self.git("add", "-A")
            self.git("commit", "-q", "-m", name)
            self.git("push", "-q", "origin", name)
        self.git("checkout", "-q", "main")
        self.git("tag", "v1.2.0")
        hook = self.work / ".git" / "hooks" / "commit-msg"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        # The remote is on GitLab; git still reaches the local bare repository.
        gitlab = "https://gitlab.com/acme/app.git"
        self.git("config", f"url.{self.remote}.insteadOf", gitlab)
        self.git("remote", "set-url", "origin", gitlab)

    def survey(self) -> dict:
        return json.loads(self.mth("survey", "--json"))

    def answers(self, extra: dict | None = None) -> str:
        data = {"instrucciones": {"option": "metodologia"}, "autonomia": {"option": "full"},
                "decisiones": {"option": "mapear", "path": "docs/adr", "kind": "ADR", "pattern": "ADR-\\d{3}"},
                "revisores": {"option": "agentes", "agents": []}, **(extra or {})}
        path = self.tmp / "answers.json"
        path.write_text(json.dumps({"answers": data}), encoding="utf-8")
        return str(path)

    def test_the_interview_asks_four_questions_in_one_round(self):
        # verifies: SPEC-0015/AC-11, SPEC-0015/AC-01
        result = self.survey()
        by_id = {q["id"]: q for q in result["questions"]}
        self.assertEqual(result["profile"], "methodology")
        self.assertEqual([q for q, v in by_id.items() if v["outcome"] == "decision"],
                         ["instrucciones", "autonomia", "decisiones", "revisores"])
        self.assertEqual(by_id["ramas"]["answer"], {"option": "usar", "branch": "dev"})
        self.assertEqual(by_id["commits"]["answer"], {"option": "encadenar"})
        self.assertEqual(by_id["tests"]["answer"]["command"], "make test")
        self.assertEqual((by_id["ci"]["outcome"], by_id["versiones"]["answer"], by_id["alcance"]["outcome"],
                          by_id["modelos"]["outcome"]), ("deducida", None, "deducida", "por_defecto"))
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("una sola ronda", skill)
        self.assertIn("--plan", skill)
        self.assertLess(skill.index("--plan"), skill.index("--marketplace-repo"))

    def test_the_plan_is_shown_before_anything_is_written(self):
        # verifies: SPEC-0015/AC-08, SPEC-0015/AC-11
        before = self.git("status", "--porcelain"), self.git("branch", "--list")
        out = self.mth("init", "--answers", self.answers(), "--plan")
        self.assertEqual((self.git("status", "--porcelain"), self.git("branch", "--list")), before)
        self.assertFalse((self.work / ".claude/methodology.toml").exists())
        positions = [out.index(text) for text in ("Deducido del repo (", "Por defecto (", "Decidido (", "Capacidades")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ramas: usar → branches.development = dev (única candidata (dev) y las 2 ramas", out)
        self.assertIn("✗ mth integrate (PR con merge commit) — el remoto no es GitHub", out)
        self.assertIn("✗ mth release (versión, etiqueta y CHANGELOG) — el remoto no es GitHub: la publicación es manual", out)
        self.assertIn("✓ tests antes de integrar — commands.test = make test", out)
        self.assertIn("✓ validación de mensajes de commit — hooks.commit_msg = chain", out)
        self.assertIn("✗ CI exigida para integrar — ci.required = false", out)
        self.assertIn("--plan necesita --answers", self.mth("init", "--plan", ok=False))
        # A rejected answer (a GitHub workflow without GitHub) changes nothing.
        rejected = self.mth("init", "--answers", self.answers({"ci": {"option": "crear"}}), ok=False)
        self.assertIn("ci: la opción 'crear' no funciona con este repo", rejected)
        self.assertEqual((self.git("status", "--porcelain"), self.git("branch", "--list")), before)
        self.assertFalse((self.work / ".claude/methodology.toml").exists())
        # The adoption prints the same plan first, then writes.
        adoption_out = self.mth("init", "--answers", self.answers())
        self.assertLess(adoption_out.index("Plan de adopción"), adoption_out.index("Rama chore/adopt-methodology")
                        if "Rama chore/adopt-methodology" in adoption_out else len(adoption_out))
        self.assertEqual(self.git("branch", "--show-current"), "chore/adopt-methodology")
        adr = next((self.work / "docs/adr/methodology").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("| `ramas` | `deducida` | `usar` |", adr)
        self.assertIn("| `modelos` | `por_defecto` | `equilibrado` |", adr)
        self.assertIn("| `autonomia` | `decision` | `full` |", adr)


if __name__ == "__main__":
    unittest.main()
