"""Tests of guided adoption (SPEC-0004)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import adoption, guard, lang, session, setup, survey  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

SKILL = HERE.parent / "plugins" / "methodology" / "skills" / "mth-init"
CONFIG = 'version = 1\n[commands]\ntest = ""\n'
ENGLISH = "This is the readme of the project and it is for the team that works with it. " * 6
DEFAULT_ANSWERS = {"alcance": {"option": "gradual"}, "ramas": {"option": "crear"}, "tests": {"option": "ninguno"},
                   "autonomia": {"option": "until-pr"}, "idioma": {"option": "es"}, "ci": {"option": "sin-ci"},
                   "modelos": {"option": "calidad"}, "versiones": {"option": "continuar"},
                   "instrucciones": {"option": "metodologia"}, "revisores": {"option": "agentes", "agents": []}}


class RepoCase(unittest.TestCase):
    """A local repository (no remote unless the test adds one)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.env = {**os.environ, **test_mth.GIT_ENV}
        self.git("init", "-q", "-b", "main")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, rel: str, text: str = "x\n") -> None:
        test_mth._write(self.root / rel, text)

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "state")

    def inventory(self) -> survey.Survey:
        return survey.run(Git.discover(self.root))


class BeforeAdoptionTests(RepoCase):
    def test_session_shows_only_the_adoption_notice(self):
        # verifies: SPEC-0004/AC-01
        out = session.context(self.root, "mth")
        self.assertIn("repositorio sin adoptar", out)
        self.assertIn("mth init --decline", out)
        self.assertNotIn("reglas base", out)
        self.write(".claude/methodology.toml", CONFIG)
        self.assertIn("reglas base", session.context(self.root, "mth"))

    def test_guard_does_not_block_before_adoption(self):
        # verifies: SPEC-0004/AC-02
        self.commit()

        def run(command: str) -> int:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return guard.main(json.dumps({"tool_input": {"command": command}, "cwd": str(self.root)}))
        for command in ("git push origin main", "git rebase main", "git push --force"):
            with self.subTest(command=command):
                self.assertEqual(run(command), 0)
        self.write(".claude/methodology.toml", CONFIG)
        self.assertEqual(run("git rebase main"), guard.BLOCK)

    def test_session_with_an_unreadable_configuration_keeps_the_rules(self):
        # verifies: SPEC-0004/AC-01
        self.write(".claude/methodology.toml", "version = 99\n")
        out = session.context(self.root, "mth")
        self.assertIn("reglas base", out)
        self.assertNotIn("repositorio sin adoptar", out)

    def test_guard_blocks_pushing_to_main_once_adopted(self):
        # verifies: SPEC-0004/AC-02
        self.commit()
        self.write(".claude/methodology.toml", CONFIG)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = guard.main(json.dumps({"tool_input": {"command": "git push origin main"}, "cwd": str(self.root)}))
        self.assertEqual(code, guard.BLOCK)

    def test_decline_creates_the_settings_file_or_refuses_a_non_object(self):
        # verifies: SPEC-0004/AC-03
        settings = self.root / ".claude/settings.local.json"
        with contextlib.redirect_stderr(io.StringIO()):
            setup.decline(self.root)
        self.assertEqual(json.loads(settings.read_text()), {"enabledPlugins": {"methodology@claude-methodology": False}})
        settings.write_text("[]", encoding="utf-8")  # valid JSON, but not an object
        with self.assertRaises(MthError):
            setup.decline(self.root)
        self.assertEqual(settings.read_text(), "[]")

    def test_decline_disables_the_plugin_locally(self):
        # verifies: SPEC-0004/AC-03
        settings = self.root / ".claude/settings.local.json"
        self.write(".claude/settings.local.json", '{"permissions": {"allow": ["Bash(ls)"]}}')
        for _ in range(2):  # idempotent
            with contextlib.redirect_stderr(io.StringIO()):
                setup.decline(self.root)
            data = json.loads(settings.read_text())
            self.assertEqual(data, {"permissions": {"allow": ["Bash(ls)"]},
                                    "enabledPlugins": {"methodology@claude-methodology": False}})
        settings.write_text("{not json", encoding="utf-8")
        with self.assertRaises(MthError):
            setup.decline(self.root)
        self.assertEqual(settings.read_text(), "{not json")


class SurveyTests(RepoCase):
    def test_profiles(self):
        # verifies: SPEC-0004/AC-04
        self.write("README.md", "# demo\n")
        self.commit()
        self.assertEqual(self.inventory().profile, "new")
        self.write("src/app.py", "print('x')\n")
        self.assertEqual(self.inventory().profile, "existing")
        for rel in ("rfcs/001-auth.md", ".claude/agents/reviewer.md"):
            with self.subTest(signal=rel):
                self.write(rel)
                self.assertEqual(self.inventory().profile, "methodology")
                (self.root / rel).unlink()
        hook = Git.discover(self.root).hooks_dir() / "commit-msg"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.assertEqual(self.inventory().profile, "methodology")
        hook.unlink()
        self.git("remote", "add", "upstream", "https://example.invalid/upstream.git")
        self.assertEqual(self.inventory().profile, "fork")

    def test_empty_repo_is_new_and_a_plain_origin_is_not_a_fork(self):
        # verifies: SPEC-0004/AC-04
        self.assertEqual(self.inventory().profile, "new")
        self.write("src/app.py", "print('x')\n")
        self.commit()
        self.git("remote", "add", "origin", "https://example.invalid/origin.git")
        self.assertEqual(self.inventory().profile, "existing")

    def test_fork_questions_start_from_the_fork_base(self):
        # verifies: SPEC-0004/AC-05
        self.write("src/app.py")
        self.commit()
        self.git("remote", "add", "upstream", "https://example.invalid/upstream.git")
        inventory = self.inventory()
        self.assertEqual(inventory.profile, "fork")
        self.assertEqual([q["id"] for q in inventory.questions], ["autonomia", "forja", "alcance", "ramas", "versiones",
                                                                  "tests", "revisores", "idioma", "ci", "modelos"])

    def test_questions_follow_profile_and_signals(self):
        # verifies: SPEC-0004/AC-05
        self.write("README.md", "# demo\n")
        self.commit()
        new = self.inventory()
        # The repository has no remote, so the CI question is settled without asking (SPEC-0015).
        self.assertEqual([q["id"] for q in new.questions], ["autonomia", "forja", "revisores", "idioma", "ci", "modelos"])
        self.assertEqual(new.asked(), ["autonomia", "revisores"])
        self.write("src/app.py")
        self.write(".github/workflows/ci.yml", "on: push\n")
        self.write("docs/guia.md", "El proyecto es para la gente que trabaja con el código de la casa. " * 6)
        existing = self.inventory()
        self.assertEqual([q["id"] for q in existing.questions],
                         ["autonomia", "forja", "alcance", "ramas", "tests", "revisores", "ci", "modelos"])
        self.assertEqual(existing.asked(), ["autonomia", "tests", "revisores"])
        self.write("tests/test_app.py")  # one test candidate: no question
        self.assertNotIn("tests", self.inventory().asked())

    def test_signals(self):
        # verifies: SPEC-0004/AC-06
        self.write("README.md", ENGLISH)
        self.write("rfcs/001-auth.md", "# RFC-001 · Auth\n")
        self.write("rfcs/002-cache.md", "# RFC-002 · Cache\n")
        self.write("docs/decisions/ADR-01-db.md", "# ADR-01 · DB\n")
        self.write(".claude/agents/verificador.md")
        self.write(".claude/agents/security-reviewer.md")
        self.write(".husky/commit-msg")
        self.write("release-please-config.json", "{}")
        self.write("package.json", '{"name": "x", "version": "1.2.3", "scripts": {"test": "jest"}}')
        self.write("Makefile", "test:\n\tpytest\n")
        self.commit()
        self.git("tag", "v1.2.3")
        before = self.git("status", "--porcelain")
        found = self.inventory().signals
        self.assertEqual(found["specs"], [{"path": "rfcs", "files": 2, "pattern": "RFC-\\d{3}"}])
        self.assertEqual(found["adrs"], [{"path": "docs/decisions", "files": 1, "pattern": "ADR-\\d{2}"}])
        self.assertEqual(found["agents"], ["security-reviewer", "verificador"])
        self.assertEqual(found["agent_collisions"], ["verificador"])
        self.assertEqual(found["hook_managers"], [".husky"])
        self.assertEqual(found["release_tools"], ["release-please-config.json"])
        self.assertEqual([v["path"] for v in found["version_files"]], ["package.json"])
        self.assertEqual(found["tests"], ["npm test", "make test"])
        self.assertEqual(found["tags"], {"prefix": "v", "count": 1})
        self.assertEqual(found["language"], "en")
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_signals_of_a_plain_spanish_repo(self):
        # verifies: SPEC-0004/AC-06
        self.write("README.md", "El proyecto es para la gente que trabaja con el código de la casa y que lo usa cada día. " * 6)
        self.write("src/app.py")
        self.commit()
        found = self.inventory().signals
        for key in ("specs", "adrs", "agents", "agent_collisions", "hook_managers", "release_tools", "version_files", "tests"):
            self.assertEqual(found[key], [], key)
        self.assertIsNone(found["tags"])
        self.assertEqual(found["language"], "es")

    def test_a_huge_file_does_not_stop_the_inventory(self):
        # verifies: SPEC-0004/AC-07
        self.write("README.md", "El proyecto es para la gente que trabaja con el código de la casa y que lo usa cada día. " * 6000)
        self.commit()
        result = self.inventory()
        self.assertEqual(result.signals["language"], "es")
        self.assertTrue(result.questions)

    def test_adopted_repo_and_unreadable_files(self):
        # verifies: SPEC-0004/AC-07
        (self.root / "AGENTS.md").write_bytes(b"\xff\xfe binary")
        self.commit()
        result = self.inventory()
        self.assertIn("no se pudo leer AGENTS.md", "\n".join(result.warnings))
        self.assertTrue(result.questions)
        self.write(".claude/methodology.toml", CONFIG)
        with self.assertRaises(MthError) as ctx:
            self.inventory()
        self.assertIn("ya ha adoptado", ctx.exception.message)


class AnswersTests(unittest.TestCase):
    def survey_of(self, profile: str, **signals) -> survey.Survey:
        found = {"files": 3, "branches": ["main"], "upstream": profile == "fork", "tags": None, "specs": [],
                 "forge": "github", "forge_host": "github.com", "integration": {"candidates": [], "working": 0, "from_candidate": 0},
                 "adrs": [], "agents": [], "agent_collisions": [], "claude_dirs": [], "instructions": [],
                 "commit_hook": False, "hook_managers": [], "release_tools": [], "version_files": [],
                 "ci": False, "tests": [], "language": "es", **signals}
        return survey.Survey(profile, found, survey.questions(profile, found))

    def config(self, inventory: survey.Survey, answers: dict) -> dict:
        adoption.validate(inventory, answers)
        template = (lang.TEMPLATES / "methodology.toml").read_text(encoding="utf-8")
        plan = adoption.build(template, inventory, answers, "main", "a" * 40)
        text = adoption.dump_toml(plan.data)
        parse(Path("."), text)  # the generated configuration is valid
        return tomllib.loads(text)

    def test_effects_of_each_option(self):
        # verifies: SPEC-0004/AC-09
        inventory = self.survey_of(
            "methodology", specs=[{"path": "rfcs", "files": 2, "pattern": "RFC-\\d{3}"}],
            adrs=[{"path": "docs/decisions", "files": 1, "pattern": "ADR-\\d{2}"}],
            agents=["verificador", "security-reviewer"], agent_collisions=["verificador"],
            commit_hook=True, tags={"prefix": "rel-", "count": 3},
            version_files=[{"path": "package.json", "pattern": '"version":\\s*"(\\d+\\.\\d+\\.\\d+)"'}],
            instructions=["CLAUDE.md"], language="en",
            integration={"candidates": ["develop"], "working": 2, "from_candidate": 2})
        answers = {
            "forja": {"option": "gitlab"}, "alcance": {"option": "gradual"},
            "ramas": {"option": "usar", "branch": "develop"},
            "commits": {"option": "encadenar"},
            "versiones": {"option": "continuar", "version_files": inventory.signals["version_files"]},
            "specs": {"option": "mapear", "path": "rfcs", "kind": "RFC", "pattern": "RFC-\\d{3}"},
            "decisiones": {"option": "mapear", "path": "docs/decisions", "kind": "ADR", "pattern": "ADR-\\d{2}"},
            "tests": {"option": "comando", "command": "npm test"},
            "revisores": {"option": "agentes", "agents": ["security-reviewer"]},
            "colision": {"option": "renombrar", "renames": {"verificador": "verificador-repo"}},
            "instrucciones": {"option": "repo", "exceptions": ["pregunta antes de hacer commit"]},
            "autonomia": {"option": "supervised"}, "idioma": {"option": "en"}, "ci": {"option": "crear"},
            "modelos": {"option": "ahorro"},
        }
        self.assertEqual(sorted(answers), sorted(q["id"] for q in inventory.questions))
        self.assertTrue(set(inventory.asked()) <= set(answers))
        cfg = self.config(inventory, answers)
        self.assertEqual(cfg["trace"]["legacy_base"], "a" * 40)
        self.assertEqual(cfg["branches"]["development"], "develop")
        self.assertEqual(cfg["hooks"]["commit_msg"], "chain")
        self.assertEqual(cfg["release"]["tag_prefix"], "rel-")
        self.assertEqual(cfg["release"]["version_files"][0]["path"], "package.json")
        self.assertEqual((cfg["paths"]["specs"], cfg["trace"]["spec_kind"]), ("rfcs", "RFC"))
        self.assertEqual(cfg["ids"]["RFC"], {"pattern": "RFC-\\d{3}", "defined_in": ["rfcs/**/*.md"]})
        self.assertNotIn("SPEC", cfg["ids"])
        self.assertEqual(cfg["ids"]["ADR"]["defined_in"], ["docs/decisions/**/*.md"])
        self.assertEqual(cfg["commands"]["test"], "npm test")
        self.assertEqual(cfg["review"]["agents"], ["verificador", "security-reviewer", "verificador-repo"])
        self.assertEqual((cfg["autonomy"]["level"], cfg["language"]["docs"], cfg["ci"]["required"]),
                         ("supervised", "en", True))
        self.assertEqual(cfg["models"]["ladder"], ["haiku", "sonnet"])

    def test_defaults_fork_and_other(self):
        # verifies: SPEC-0004/AC-09
        inventory = self.survey_of("fork", ci=True, tests=["pytest"], branches=["main", "development"])
        answers = {"alcance": {"option": "completa"}, "versiones": {"option": "prefijo", "tag_prefix": "fork-v"},
                   "autonomia": {"option": "otro", "config": {"autonomy": {"level": "until-pr"}},
                                 "note": "solo confirmamos la integración"},
                   "modelos": {"option": "equilibrado"}, "revisores": {"option": "agentes", "agents": []}}
        cfg = self.config(inventory, answers)
        self.assertEqual((cfg["commands"]["test"], cfg["ci"]["required"]), ("pytest", True))
        self.assertEqual(cfg["paths"]["claude_md"], ".claude/CLAUDE.md")
        self.assertEqual(cfg["commits"]["external_refs"], ["refs/remotes/upstream/main"])
        self.assertEqual((cfg["release"]["tag_prefix"], cfg["autonomy"]["level"]), ("fork-v", "until-pr"))
        self.assertEqual(cfg["trace"]["legacy_base"], "")

    def test_catalog_is_only_for_adoption(self):
        # unit: adoption.validate
        inventory = survey.Survey(survey.RECONFIGURE, {}, [{"id": "revisores", "evidence": "x"}])
        with self.assertRaises(MthError) as ctx:
            adoption.validate(inventory, {"revisores": {"option": "agentes", "agents": [], "catalog": ["revisor-adr"]}})
        self.assertIn("mth agents add", ctx.exception.message)
        inventory = self.survey_of("new")
        with self.assertRaises(MthError) as ctx:
            adoption.validate(inventory, {**{q: DEFAULT_ANSWERS[q] for q in inventory.asked()},
                                          "revisores": {"option": "agentes", "agents": [], "catalog": ["revisor-adr"],
                                                        "vars": {"lector-estado": {"max_rows": 1}}}})
        self.assertIn("vars.lector-estado", ctx.exception.message)

    def test_invalid_answers(self):
        # verifies: SPEC-0004/AC-08
        inventory = self.survey_of("existing", integration={"candidates": ["develop"], "working": 0, "from_candidate": 0})
        valid = {q: DEFAULT_ANSWERS[q] for q in inventory.asked()}
        cases = {
            "falta la respuesta": {k: v for k, v in valid.items() if k != "autonomia"},
            "no está en el inventario": {**valid, "specs": {"option": "convertir"}},
            "opción desconocida 'yolo'": {**valid, "autonomia": {"option": "yolo"}},
            "parámetros desconocidos: color": {**valid, "ci": {"option": "sin-ci", "color": "red"}},
            "'usar' necesita 'branch'": {**valid, "ramas": {"option": "usar"}},
        }
        for expected, answers in cases.items():
            with self.subTest(expected=expected), self.assertRaises(MthError) as ctx:
                adoption.validate(inventory, answers)
            self.assertIn(expected, ctx.exception.message)
        with self.assertRaises(MthError) as ctx:
            self.config(inventory, {**valid, "autonomia": {"option": "otro", "config": {"autonomy": {"level": "x"}}}})
        self.assertIn("'autonomy.level' = 'x'", ctx.exception.message)


class AdoptionFlowTests(unittest.TestCase):
    setUp = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def answers(self, overrides: dict | None = None) -> Path:
        questions = json.loads(self.mth("survey", "--json"))["questions"]
        answers = {q["id"]: DEFAULT_ANSWERS[q["id"]] for q in questions if q["outcome"] == survey.DECISION}
        path = self.tmp / "answers.json"
        path.write_text(json.dumps({"answers": {**answers, **(overrides or {})}}), encoding="utf-8")
        return path

    def test_rejected_answers_change_nothing(self):
        # verifies: SPEC-0004/AC-08
        (self.tmp / "bad.json").write_text("{not json", encoding="utf-8")
        invalid_other = {"autonomia": {"option": "otro", "config": {"autonomy": {"level": "x"}}}}
        for path in (self.tmp / "bad.json", self.answers({"autonomia": {"option": "yolo"}}), self.answers(invalid_other)):
            with self.subTest(path=path.name):
                self.mth("init", "--answers", str(path), ok=False)
                self.assertEqual(self.git("branch", "--list"), "* main")
                self.assertEqual(self.git("status", "--porcelain"), "")
                self.assertFalse((self.work / ".claude/methodology.toml").exists())

    def test_catalog_agents_are_installed_in_the_adoption_commit(self):
        # verifies: SPEC-0012/AC-20
        reviewers = {"option": "agentes", "agents": [], "catalog": ["revisor-fallos", "revisor-seguridad", "lector-estado"],
                     "vars": {"lector-estado": {"databases": {"estado": "data/state.db"}}}}
        self.mth("init", "--answers", str(self.answers({"revisores": reviewers})))
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")
        files = self.git("show", "--name-only", "--format=", "HEAD").splitlines()
        for path in (".claude/agents/revisor-seguridad.md", ".claude/mth/agents/lector-estado.guard.toml",
                     ".claude/hooks/mth-agent-guard", ".claude/settings.json"):
            self.assertIn(path, files)
        cfg = tomllib.loads((self.work / ".claude/methodology.toml").read_text())
        self.assertEqual(cfg["review"]["agents"], ["verificador", "revisor-seguridad", "revisor-fallos"])
        self.assertEqual(cfg["agents"]["lector-estado"]["databases"], {"estado": "data/state.db"})
        self.assertEqual(self.git("status", "--porcelain"), "")
        adr = next((self.work / "specs/adr/methodology").glob("*.md")).read_text()
        self.assertIn("agentes del catálogo: revisor-fallos, revisor-seguridad, lector-estado", adr)

    def test_catalog_agents_that_cannot_be_installed_change_nothing(self):
        # verifies: SPEC-0012/AC-20
        test_mth._write(self.work / ".claude/agents/revisor-adr.md", "---\nname: revisor-adr\n---\nPropio.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "own agent")
        self.git("push", "-q", "origin", "main")
        cases = {"commands.test": ["diagnosticador"], "ya existe": ["revisor-adr"], "no es un agente": ["no-existe"]}
        for expected, chosen in cases.items():
            with self.subTest(expected=expected):
                path = self.answers({"revisores": {"option": "agentes", "agents": [], "catalog": chosen}})
                self.assertIn(expected, self.mth("init", "--answers", str(path), ok=False))
                self.assertEqual(self.git("branch", "--list"), "* main")
                self.assertEqual(self.git("status", "--porcelain"), "")
                self.assertFalse((self.work / ".claude/methodology.toml").exists())

    def test_init_preconditions(self):
        # verifies: SPEC-0004/AC-08
        path = self.answers()
        (self.work / "dirty.txt").write_text("x", encoding="utf-8")
        self.assertIn("cambios sin confirmar", self.mth("init", "--answers", str(path), ok=False).lower())
        (self.work / "dirty.txt").unlink()
        self.git("branch", "chore/adopt-methodology")
        self.assertIn("ya existe", self.mth("init", "--answers", str(path), ok=False))
        self.git("branch", "-D", "chore/adopt-methodology")
        self.git("init", "-q", "--bare", str(self.tmp / "empty.git"), cwd=self.tmp)
        self.git("remote", "set-url", "origin", str(self.tmp / "empty.git"))
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertIn("no tiene rama main", self.mth("init", "--answers", str(path), ok=False))
        self.assertFalse((self.work / ".claude/methodology.toml").exists())

    def test_adoption_of_a_new_repo_records_its_profile(self):
        # verifies: SPEC-0004/AC-10
        self.mth("init", "--answers", str(self.answers()))
        self.assertEqual(self.git("branch", "--show-current"), "chore/adopt-methodology")
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")
        adr = next((self.work / "specs/adr/methodology").glob("*.md")).read_text()
        self.assertIn("perfil **new**", adr)
        self.assertIn("| `autonomia` | `decision` | `until-pr` |", adr)
        self.assertNotIn("| `instrucciones` |", adr)

    def test_adoption_branch_with_config_and_adr(self):
        # verifies: SPEC-0004/AC-10
        test_mth._write(self.work / "src/app.py", "print('x')\n")
        test_mth._write(self.work / "CLAUDE.md", "Pregunta antes de hacer commit.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "app")
        self.git("push", "-q", "origin", "main")
        path = self.answers({"instrucciones": {"option": "repo", "exceptions": ["Pregunta antes de hacer commit."]}})
        self.mth("init", "--answers", str(path))
        self.assertEqual(self.git("branch", "--show-current"), "chore/adopt-methodology")
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")
        files = self.git("show", "--name-only", "--format=", "HEAD").splitlines()
        adr = "specs/adr/methodology/ADR-0001-adopcion-de-claude-methodology.md"
        self.assertIn(".claude/methodology.toml", files)
        self.assertIn(adr, files)
        text = (self.work / adr).read_text()
        self.assertIn("perfil **methodology**", text)
        self.assertIn("| `autonomia` | `decision` | `until-pr` | autonomy.level = until-pr | — |", text)
        self.assertIn("| `instrucciones` | `decision` | `repo` |", text)
        self.assertIn("Pregunta antes de hacer commit.", text)
        cfg = tomllib.loads((self.work / ".claude/methodology.toml").read_text())
        self.assertEqual(cfg["trace"]["legacy_base"], self.git("rev-parse", "origin/main"))
        self.assertIn("✓ Trazabilidad OK", self.mth("trace"))


class CatalogTests(unittest.TestCase):
    def test_catalog_covers_every_question_and_option(self):
        # verifies: SPEC-0004/AC-11
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill, r"(?m)^model: opus$")
        catalog = (SKILL / "preguntas.md").read_text(encoding="utf-8")
        sections = dict(re.findall(r"(?ms)^## `([a-z-]+)`\n(.*?)(?=^## |\Z)", catalog))
        self.assertEqual(list(sections), list(survey.QUESTIONS))
        for qid, body in sections.items():
            with self.subTest(question=qid):
                options = set(re.findall(r'\{"option": "([a-z-]+)"', body))
                self.assertEqual(options, set(adoption.OPTIONS[qid]))


if __name__ == "__main__":
    unittest.main()
