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
                   "instrucciones": {"option": "metodologia"}}


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

    def test_questions_follow_profile_and_signals(self):
        # verifies: SPEC-0004/AC-05
        self.write("README.md", "# demo\n")
        self.commit()
        new = self.inventory()
        self.assertTrue(set(new.asked()) <= {"autonomia", "idioma", "ci", "modelos"}, new.asked())
        self.assertEqual(new.asked(), ["autonomia", "idioma", "ci", "modelos"])
        self.write("src/app.py")
        self.write(".github/workflows/ci.yml", "on: push\n")
        self.write("docs/guia.md", "El proyecto es para la gente que trabaja con el código de la casa. " * 6)
        existing = self.inventory()
        self.assertEqual(existing.asked(), ["alcance", "ramas", "tests", "autonomia", "modelos"])
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
            instructions=["CLAUDE.md"], language="en")
        answers = {
            "alcance": {"option": "gradual"}, "ramas": {"option": "usar", "branch": "develop"},
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
        self.assertEqual(sorted(answers), sorted(inventory.asked()))
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
                   "modelos": {"option": "equilibrado"}}
        cfg = self.config(inventory, answers)
        self.assertEqual((cfg["commands"]["test"], cfg["ci"]["required"]), ("pytest", True))
        self.assertEqual(cfg["paths"]["claude_md"], ".claude/CLAUDE.md")
        self.assertEqual(cfg["commits"]["external_refs"], ["refs/remotes/upstream/main"])
        self.assertEqual((cfg["release"]["tag_prefix"], cfg["autonomy"]["level"]), ("fork-v", "until-pr"))
        self.assertEqual(cfg["trace"]["legacy_base"], "")

    def test_invalid_answers(self):
        # verifies: SPEC-0004/AC-08
        inventory = self.survey_of("existing")
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
        answers = {q["id"]: DEFAULT_ANSWERS[q["id"]] for q in questions}
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
        self.assertIn("| `autonomia` | `until-pr` | autonomy.level = until-pr | — |", text)
        self.assertIn("| `instrucciones` | `repo` |", text)
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
