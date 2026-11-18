"""Tests of the guided reconfiguration of an adopted repository (SPEC-0011)."""
from __future__ import annotations

import json
import os
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
from mthlib import guard, survey  # noqa: E402
from mthlib.config import parse  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

SKILLS = HERE.parent / "plugins" / "methodology" / "skills"
CONFIG = 'version = 1\n[commands]\ntest = ""\n'
BRANCH = "chore/reconfigure-methodology"
ADOPTION_ADR = "specs/adr/methodology/ADR-0001-adopcion-de-claude-methodology.md"


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        self.repo = Git.discover(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def adopt(self, text: str = CONFIG):
        test_mth._write(self.root / ".claude/methodology.toml", text)
        return parse(self.root, text)

    def test_only_adopted_repos_are_reconfigured(self):
        # verifies: SPEC-0011/AC-01
        with self.assertRaises(MthError) as ctx:
            survey.reconfigure(self.repo, parse(self.root, CONFIG))
        self.assertIn("mth-init", ctx.exception.hint)
        self.adopt()
        with self.assertRaises(MthError):
            survey.run(self.repo)

    def test_full_form_with_current_values(self):
        # verifies: SPEC-0011/AC-02
        cfg = self.adopt(CONFIG + '[autonomy]\nlevel = "until-pr"\n')
        inventory = survey.reconfigure(self.repo, cfg)
        self.assertEqual(inventory.profile, "reconfigure")
        self.assertEqual(inventory.asked(), [q for q in survey.QUESTIONS if q != "colision"])
        self.assertTrue(all(q["current"] for q in inventory.questions))
        current = {q["id"]: q["current"] for q in inventory.questions}
        self.assertEqual(current["autonomia"], "autonomy.level = until-pr")
        test_mth._write(self.root / ".claude/agents/verificador.md", "---\nname: verificador\n---\n")
        self.assertIn("colision", survey.reconfigure(self.repo, cfg).asked())

    def test_only_selects_blocks_and_questions(self):
        # verifies: SPEC-0011/AC-03
        cfg = self.adopt()
        self.assertEqual(sorted(q for block in survey.GROUPS.values() for q in block), sorted(survey.QUESTIONS))
        self.assertEqual(survey.reconfigure(self.repo, cfg, "agente,tests").asked(), ["tests", "autonomia", "modelos"])
        self.assertEqual(survey.reconfigure(self.repo, cfg, "flujo").asked(), ["ramas", "commits", "versiones", "ci"])
        with self.assertRaises(MthError) as ctx:
            survey.reconfigure(self.repo, cfg, "agente,nada")
        self.assertIn("'nada' no es una pregunta ni un bloque", ctx.exception.message)
        with self.assertRaises(MthError) as ctx:
            survey.reconfigure(self.repo, cfg, "colision")  # no collisions: nothing applicable
        self.assertIn("ninguna pregunta aplicable", ctx.exception.message)


class ReconfigureTests(unittest.TestCase):
    setUp_e2e = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    EXTRA = '\n[work]\ndirs = ["bench"]\n\n[ids.RFC]\npattern = \'RFC-\\d{3}\'\ndefined_in = ["rfcs/**/*.md"]\n'

    def setUp(self):
        self.setUp_e2e()
        self.mth("init")
        cfg = self.work / ".claude/methodology.toml"
        self.base = self.git("rev-parse", "HEAD")  # an existing commit for trace.legacy_base
        cfg.write_text(cfg.read_text().replace('test = ""', 'test = "true"')
                       .replace('legacy_base = ""', f'legacy_base = "{self.base}"')
                       .replace("[review.paths]\n", '[review.paths]\nverificador = ["src/**"]\n') + self.EXTRA)
        test_mth._write(self.work / ADOPTION_ADR, "# ADR-0001 · Adopción de claude-methodology\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "configure repo",
                 "--body", "Test command, reviewer and work dirs.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")
        self.config_before = self.config_text()

    def config_text(self, ref: str | None = None) -> str:
        if ref:
            return self.git("show", f"{ref}:.claude/methodology.toml")
        return (self.work / ".claude/methodology.toml").read_text(encoding="utf-8")

    def answers(self, data: dict) -> str:
        path = self.tmp / f"answers-{len(list(self.tmp.glob('answers-*.json')))}.json"  # one file per call
        path.write_text(json.dumps({"answers": data}), encoding="utf-8")
        return str(path)

    def unchanged(self):
        self.assertEqual(self.git("branch", "--show-current"), "development")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.config_text(), self.config_before)
        self.assertEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")

    def test_applies_answers_on_top_of_the_current_configuration(self):
        # verifies: SPEC-0011/AC-04
        out = self.mth("reconfigure", "--answers", self.answers({"autonomia": {"option": "supervised"},
                                                                 "modelos": {"option": "calidad"}}),
                       "--only", "agente")
        self.assertIn("autonomy.level: 'full' → 'supervised'", out)
        self.assertEqual(self.git("branch", "--show-current"), BRANCH)
        self.git("fetch", "-q")
        self.assertEqual(self.git("rev-list", "--count", f"origin/development..origin/{BRANCH}"), "1")
        data = tomllib.loads(self.config_text(f"origin/{BRANCH}"))
        self.assertEqual(data["autonomy"]["level"], "supervised")
        self.assertEqual(data["models"]["review"], "opus")
        self.assertEqual(data["work"]["dirs"], ["bench"])
        self.assertEqual(data["review"]["paths"], {"verificador": ["src/**"]})
        self.assertEqual(data["commands"]["test"], "true")
        self.assertEqual(data["ids"]["RFC"], {"pattern": r"RFC-\d{3}", "defined_in": ["rfcs/**/*.md"]})
        self.assertEqual(data["ids"]["SPEC"]["pattern"], r"SPEC-\d{4}")
        files = self.git("show", "--name-only", "--format=", f"origin/{BRANCH}").splitlines()
        adr = next(f for f in files if "reestructuracion-de-claude-methodology" in f)
        text = self.git("show", f"origin/{BRANCH}:{adr}")
        self.assertIn("Modifica las decisiones registradas en ADR-0001.", text)
        self.assertIn("| `autonomia` | `supervised` |", text)
        self.assertIn('| `autonomy.level` | `"full"` | `"supervised"` |', text)
        self.assertIn("Refs: " + adr.rsplit("/", 1)[1].split("-reest")[0],
                      self.git("log", "-1", "--format=%B", f"origin/{BRANCH}"))

    def test_invalid_requests_change_nothing(self):
        # verifies: SPEC-0011/AC-05
        cases = [
            ({"autonomia": {"option": "a-ratos"}}, "agente", "opción desconocida"),
            ({"autonomia": {"option": "full"}}, "agente", "modelos: falta la respuesta"),
            ({"autonomia": {"option": "full"}, "modelos": {"option": "calidad"}, "idioma": {"option": "en"}},
             "agente", "idioma: la pregunta no está en el inventario"),
            ({"revisores": {"option": "agentes", "agents": []}, "tests": {"option": "ninguno"}},
             "calidad", "review.paths.verificador"),
            ({"ramas": {"option": "usar", "branch": "develop"}, "commits": {"option": "sustituir"},
              "versiones": {"option": "continuar"}, "ci": {"option": "sin-ci"}}, "flujo", "no existe en el remoto"),
            ({"commits": {"option": "encadenar"}}, "commits", "no hay ninguno"),
        ]
        for data, only, expected in cases:
            with self.subTest(expected=expected):
                out = self.mth("reconfigure", "--answers", self.answers(data), "--only", only, ok=False)
                self.assertIn(expected, out)
                self.unchanged()
        (self.work / "README.md").write_text("dirty\n")
        self.assertIn("cambios sin confirmar",
                      self.mth("reconfigure", "--answers", self.answers({"autonomia": {"option": "supervised"}}),
                               "--only", "autonomia", ok=False))
        self.git("checkout", "-q", "README.md")
        self.git("branch", BRANCH)
        self.assertIn("ya existe", self.mth("reconfigure", "--answers",
                                            self.answers({"autonomia": {"option": "supervised"}}),
                                            "--only", "autonomia", ok=False))
        self.git("push", "-q", "origin", BRANCH)
        self.git("branch", "-D", BRANCH)
        self.assertIn("ya existe", self.mth("reconfigure", "--answers",
                                            self.answers({"autonomia": {"option": "supervised"}}),
                                            "--only", "autonomia", ok=False))  # only on the remote
        self.git("push", "-q", "origin", "--delete", BRANCH)
        self.unchanged()
        (self.work / ".claude/methodology.toml").rename(self.tmp / "saved.toml")
        out = self.mth("reconfigure", "--answers", self.answers({"autonomia": {"option": "supervised"}}), ok=False)
        self.assertIn("no ha adoptado la metodología", out)
        self.assertIn("mth-init", out)
        (self.tmp / "saved.toml").rename(self.work / ".claude/methodology.toml")

    def test_nothing_to_change_unless_a_migration_is_requested(self):
        # verifies: SPEC-0011/AC-06
        out = self.mth("reconfigure", "--answers", self.answers({"autonomia": {"option": "full"}}),
                       "--only", "autonomia", ok=False)
        self.assertIn("nada que cambiar", out)
        self.unchanged()
        out = self.mth("reconfigure", "--answers", self.answers({"ci": {"option": "crear"}}), "--only", "ci")
        self.assertIn("Migración pendiente", out)
        adr = next(p for p in (self.work / "specs/adr/methodology").glob("*reestructuracion*"))
        self.assertIn("- `ci: crear`", adr.read_text(encoding="utf-8"))

    def test_scope_and_reviewers(self):
        # verifies: SPEC-0011/AC-07
        gradual = self.answers({"alcance": {"option": "gradual"}})
        out = self.mth("reconfigure", "--answers", gradual, "--only", "alcance", ok=False)
        self.assertIn("nada que cambiar", out)  # an existing base is kept
        self.assertEqual(tomllib.loads(self.config_text())["trace"]["legacy_base"], self.base)
        self.mth("reconfigure", "--answers", self.answers({"alcance": {"option": "completa"}}), "--only", "alcance")
        self.assertEqual(tomllib.loads(self.config_text())["trace"]["legacy_base"], "")
        self.mth("integrate", "--title", "chore(methodology): reconfigure claude-methodology", "--summary", "Alcance.")
        development = self.git("rev-parse", "origin/development")
        self.mth("reconfigure", "--answers", gradual, "--only", "alcance")  # no base: the development commit
        self.assertEqual(tomllib.loads(self.config_text())["trace"]["legacy_base"], development)
        self.mth("integrate", "--title", "chore(methodology): reconfigure claude-methodology", "--summary", "Alcance.")
        self.mth("branch", "chore", "agent")
        test_mth._write(self.work / ".claude/agents/seguridad.md", "---\nname: seguridad\n---\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--summary", "add a security reviewer", "--body", "Agent.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore: add a security reviewer", "--summary", "Agente.")
        self.mth("reconfigure", "--answers", self.answers({"revisores": {"option": "agentes",
                                                                         "agents": ["verificador", "seguridad"]},
                                                           "tests": {"option": "comando", "command": "true"}}),
                 "--only", "calidad")
        self.assertEqual(tomllib.loads(self.config_text())["review"]["agents"], ["verificador", "seguridad"])

    def test_hook_mode_change_is_installed(self):
        # verifies: SPEC-0011/AC-08
        hooks = self.work / ".git/hooks"
        mth_hook = (hooks / "commit-msg").read_text()
        (hooks / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
        (hooks / "commit-msg").chmod(0o755)
        self.mth("reconfigure", "--answers", self.answers({"commits": {"option": "encadenar"}}), "--only", "commits")
        self.assertEqual((hooks / "commit-msg.local").read_text(), "#!/bin/sh\nexit 0\n")
        self.assertIn("commit-msg.local", (hooks / "commit-msg").read_text())
        self.assertNotEqual((hooks / "commit-msg").read_text(), mth_hook)
        self.assertEqual(tomllib.loads(self.config_text())["hooks"]["commit_msg"], "chain")


class GuardAndSkillTests(unittest.TestCase):
    def test_supervised_asks_before_reconfiguring(self):
        # verifies: SPEC-0011/AC-09
        self.assertIn("`mth reconfigure` requiere confirmación",
                      guard.confirmation('sh "/x/scripts/mth" reconfigure --answers a.json', "supervised") or "")
        self.assertIsNone(guard.confirmation("mth reconfigure --answers a.json", "until-pr"))

    def test_skill_documents_the_blocks_and_commands(self):
        # verifies: SPEC-0011/AC-10
        text = (SKILLS / "mth-reconfigure/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: mth-reconfigure", text)
        for block, questions in survey.GROUPS.items():
            self.assertIn(f"| `{block}` | " + ", ".join(f"`{q}`" for q in questions) + " |", text)
        self.assertIn("mth survey --reconfigure", text)
        self.assertIn("mth reconfigure --answers", text)
        self.assertIn("mth-reconfigure", (SKILLS / "mth-init/SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
