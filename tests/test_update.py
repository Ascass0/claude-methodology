"""Tests of the diagnosis of an adopted repository against the installed plugin (SPEC-0021)."""
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
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import catalog_support as support  # noqa: E402
import test_mth  # noqa: E402
from mthlib import agents, catalog, compact, lang, setup, update, updating  # noqa: E402
from mthlib.config import load  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

FALLOS = catalog.load_meta(catalog.CATALOG_DIR, "revisor-fallos")["version"]
SEGURIDAD = catalog.load_meta(catalog.CATALOG_DIR, "revisor-seguridad")["version"]

COMPACT = "# SPEC-0001 · T\n\n- Estado: aprobada\n- Formato: compacto\n"
LEGACY = "# SPEC-0002 · T\n\n- Estado: aprobada\n"


class UpdateTestCase(unittest.TestCase):
    config_text = (support.template_with_agents().replace('mode = ""', 'mode = "off"', 1)  # SPEC-0022: decided
                   .replace('\nhook = ""', '\nhook = "off"', 1).replace('\nci = ""', '\nci = "off"', 1))  # SPEC-0024

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env={**os.environ, **test_mth.GIT_ENV})
        self.write(".claude/methodology.toml", self.config_text)
        # The smoke notice depends on the Claude Code installed on the machine running the tests.
        patcher = mock.patch.object(update.smoke, "warnings", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def repo(self) -> update.Repo:
        cfg = load(self.root)
        git = Git.discover(self.root)
        git.remote = cfg.remote
        return update.Repo(git, cfg)

    def up_to_date(self) -> update.Repo:
        """A repo with the block, the hook and the base agents in place and nothing else to catch up with."""
        repo = self.repo()
        setup.upsert_claude_md(self.root, repo.cfg["paths"], repo.cfg.vocab)
        setup.install_hook(repo.git, repo.cfg["hooks"]["commit_msg"])
        with contextlib.redirect_stdout(io.StringIO()):
            agents.Manager(repo.cfg).add([], "base", False)
        return self.repo()

    def ids(self, repo: update.Repo | None = None) -> dict[str, update.Gap]:
        return {g.id: g for g in update.diagnose(repo or self.repo())}

    def snapshot(self) -> dict[str, str]:
        return {str(p.relative_to(self.root)): p.read_text(errors="replace")
                for p in sorted(self.root.rglob("*")) if p.is_file() and ".git/" not in str(p)}

    def run_plan(self, as_json: bool = False) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            update.plan(self.root, as_json)
        return out.getvalue()


class ConfinementTests(UpdateTestCase):
    def test_a_configured_path_outside_the_repo_is_refused(self):
        # verifies: SPEC-0021/AC-07
        for key, value in (("claude_md", "../x.md"), ("adr", "../../adr"), ("specs", "/etc"), ("claude_md", "."), ("adr", "")):
            with self.subTest(key=key):
                text = self.config_text.replace(f'{key} = ', f'{key} = "{value}"\n# was ', 1)
                self.write(".claude/methodology.toml", text)
                with self.assertRaises(MthError) as ctx:
                    update.open_repo(self.root)
                self.assertIn(f"paths.{key}", ctx.exception.message)

    def test_a_generated_adr_folder_that_links_outside_is_refused(self):
        # verifies: SPEC-0021/AC-07
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)
        (self.root / "specs/adr").mkdir(parents=True)
        os.symlink(outside, self.root / "specs/adr/methodology")
        with self.assertRaises(MthError) as ctx:
            update.open_repo(self.root)
        self.assertIn("fuera del repositorio", ctx.exception.message)
        self.assertEqual(list(outside.iterdir()), [])

    def test_paths_inside_the_repo_are_accepted(self):
        # verifies: SPEC-0021/AC-07
        self.write(".claude/methodology.toml", self.config_text.replace('claude_md = "CLAUDE.md"', 'claude_md = ".claude/CLAUDE.md"'))
        self.assertEqual(update.open_repo(self.root).cfg["paths"]["claude_md"], ".claude/CLAUDE.md")


class PlanTests(UpdateTestCase):
    def test_only_adopted_repos_are_updated(self):
        # verifies: SPEC-0021/AC-01
        (self.root / ".claude/methodology.toml").unlink()
        with self.assertRaises(MthError) as ctx:
            update.plan(self.root, False)
        self.assertIn("mth-init", ctx.exception.hint)

    def test_plan_lists_each_gap_without_writing(self):
        # verifies: SPEC-0021/AC-02
        self.write(".claude/methodology.toml", 'version = 1\n[commands]\ntest = ""\n')
        before = self.snapshot()
        text = self.run_plan()
        self.assertIn("[automatica]", text)
        self.assertIn("config:", text)
        data = json.loads(self.run_plan(as_json=True))
        gap = next(g for g in data["gaps"] if g["id"] == "config")
        self.assertEqual(set(gap), {"id", "clase", "evidence", "action"})
        self.assertEqual(gap["clase"], update.AUTOMATIC)
        self.assertEqual(self.snapshot(), before)

    def test_plan_without_gaps_is_up_to_date(self):
        # verifies: SPEC-0021/AC-02
        self.up_to_date()
        self.assertEqual([g.id for g in update.diagnose(self.repo())], [])
        self.assertIn("al día", self.run_plan())

    def test_missing_config_keys_are_gaps(self):
        # verifies: SPEC-0021/AC-03
        self.write(".claude/methodology.toml", 'version = 1\n[commands]\ntest = ""\n[limits]\nmax_file_lines = 500\n')
        evidence = self.ids()["config"].evidence
        self.assertIn("autonomy", evidence)
        self.assertIn("limits.exclude", evidence)
        self.assertNotIn("limits.max_file_lines", evidence)

    def test_owned_tables_are_never_gaps(self):
        # verifies: SPEC-0021/AC-03
        template = {"ids": {"SPEC": {"pattern": "x"}}, "review": {"agents": [], "paths": {}},
                    "release": {"version_files": [], "tag_prefix": "v"}}
        raw = {"review": {"agents": []}, "release": {"tag_prefix": "v"}}
        self.assertEqual(update.missing_config(template, raw), [])
        self.assertEqual(update.missing_config({"hooks": {"commit_msg": "own"}}, {"hooks": {}}), [("hooks", "commit_msg")])

    def test_outdated_agent_is_automatic_and_edited_is_a_decision(self):
        # verifies: SPEC-0021/AC-04
        manager = agents.Manager(load(self.root))
        with contextlib.redirect_stdout(io.StringIO()):
            manager.add(["revisor-fallos", "revisor-seguridad"], None, False)
        self.assertNotIn("agentes-desactualizados", self.ids())
        path = self.root / ".claude/agents/revisor-fallos.md"
        path.write_text(path.read_text().replace(f"revisor-fallos@{FALLOS}", "revisor-fallos@0.0.1"), encoding="utf-8")
        gaps = self.ids()
        self.assertEqual(gaps["agentes-desactualizados"].evidence, "revisor-fallos")
        self.assertEqual(gaps["agentes-desactualizados"].clase, update.AUTOMATIC)
        other = self.root / ".claude/agents/revisor-seguridad.md"
        other.write_text(other.read_text() + "\nedición a mano\n", encoding="utf-8")
        gaps = self.ids()
        self.assertEqual(gaps["agentes-editados"].evidence, "revisor-seguridad")
        self.assertEqual(gaps["agentes-editados"].clase, update.DECISION)

    def test_base_profile_agents_not_installed_are_a_decision(self):
        # verifies: SPEC-0021/AC-04
        gap = self.ids()["agentes-perfil"]
        self.assertEqual(gap.clase, update.DECISION)
        self.assertIn("revisor-adr", gap.evidence)
        with contextlib.redirect_stdout(io.StringIO()):
            agents.Manager(load(self.root)).add([], "base", False)
        self.assertNotIn("agentes-perfil", self.ids())

    def test_documents_without_compact_format_are_a_decision(self):
        # verifies: SPEC-0021/AC-05
        self.write("specs/features/SPEC-0001-a.md", COMPACT)
        self.write("specs/features/SPEC-0002-b.md", LEGACY)
        self.write("specs/adr/methodology/ADR-0001-adopcion-de-claude-methodology.md", LEGACY)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        gap = self.ids()["formato"]
        self.assertEqual(gap.clase, update.DECISION)
        self.assertTrue(gap.evidence.startswith("1 de 2 documentos"), gap.evidence)

    def test_compact_documents_leave_no_gap(self):
        # verifies: SPEC-0021/AC-05
        self.write("specs/features/SPEC-0001-a.md", COMPACT)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        self.assertNotIn("formato", self.ids())

    def test_stale_block_and_hook_are_automatic(self):
        # verifies: SPEC-0021/AC-06
        repo = self.up_to_date()
        block = self.root / "CLAUDE.md"
        block.write_text(block.read_text().replace("Metodología", "Otra cosa"), encoding="utf-8")
        hook = repo.git.hooks_dir() / "commit-msg"
        hook.write_text(hook.read_text() + "# viejo\n", encoding="utf-8")
        gaps = self.ids()
        self.assertEqual((gaps["bloque"].clase, gaps["hook"].clase), (update.AUTOMATIC, update.AUTOMATIC))
        self.assertIn("stale", gaps["bloque"].evidence)

    def test_absent_block_and_hook_are_gaps_and_a_foreign_hook_is_not(self):
        # verifies: SPEC-0021/AC-06
        gaps = self.ids()
        self.assertIn("absent", gaps["bloque"].evidence)
        self.assertIn("absent", gaps["hook"].evidence)
        repo = self.up_to_date()
        (repo.git.hooks_dir() / "commit-msg").write_text("#!/bin/sh\necho propio\n", encoding="utf-8")
        self.assertNotIn("hook", self.ids())


class RegistryTests(unittest.TestCase):
    def test_every_gap_defines_id_class_evidence_and_action(self):
        # verifies: SPEC-0021/AC-11
        ids = [k.id for k in update.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))
        for kind in update.REGISTRY:
            self.assertIn(kind.clase, update.CLASSES, kind.id)
            self.assertTrue(kind.action.strip(), kind.id)
            self.assertTrue(callable(kind.detect), kind.id)

    def test_smoke_and_triangulation_never_block(self):
        # verifies: SPEC-0021/AC-10
        classes = {k.id: k.clase for k in update.REGISTRY}
        self.assertEqual((classes["humo"], classes["triangulacion"]), (update.INFORMATIVE, update.INFORMATIVE))

    def test_registry_matches_the_spec(self):
        # verifies: SPEC-0021/AC-11
        spec = next((HERE.parent / "specs" / "features").glob("SPEC-0021-*.md")).read_text(encoding="utf-8")
        for kind in update.REGISTRY:
            self.assertIn(f"| `{kind.id}` |", spec)
            self.assertIn(f"`{kind.clase}`", spec)


BRANCH = "chore/update-methodology"
UPDATE_ADR = "-actualizacion-de-claude-methodology.md"


class ApplyTests(unittest.TestCase):
    setUp_e2e = test_mth.EndToEndTests.setUp
    tearDown = test_mth.EndToEndTests.tearDown
    git = test_mth.EndToEndTests.git
    mth = test_mth.EndToEndTests.mth

    def setUp(self):
        self.setUp_e2e()
        self.mth("init")
        cfg = self.work / ".claude/methodology.toml"
        text = cfg.read_text().replace('test = ""', 'test = "true"').replace('review = "sonnet"', 'review = "opus"')
        text = re.sub(r"\n\[limits\].*?(?=\n\[|\Z)", "", text, flags=re.S)  # gaps: [limits] and [autonomy] are missing
        text = re.sub(r"\n\[autonomy\].*?(?=\n\[|\Z)", "", text, flags=re.S)
        # Installed catalog agents carry plugin-internal SPEC/ADR IDs that an adopter does not define.
        text = text.replace("exclude = []", 'exclude = [".claude/agents/**", ".claude/hooks/**"]', 1)
        cfg.write_text(text)
        self.mth("agents", "add", "revisor-fallos")
        agent = self.work / ".claude/agents/revisor-fallos.md"
        agent.write_text(agent.read_text().replace(f"revisor-fallos@{FALLOS}", "revisor-fallos@0.0.1"))
        claude = self.work / "CLAUDE.md"
        claude.write_text(claude.read_text().replace("Metodología", "Otra cosa"))
        test_mth._write(self.work / "specs/features/SPEC-0001-a.md", "# SPEC-0001 · A\n\n- Estado: aprobada\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "adopt with gaps",
                 "--body", "Config without two tables, outdated agent and block.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): adopt claude-methodology", "--summary", "Adopción.")
        hook = self.work / ".git/hooks/commit-msg"
        hook.write_text(hook.read_text() + "# viejo\n")
        self.before = (self.work / ".claude/methodology.toml").read_text()

    def on_branch(self, path: str) -> str:
        return self.git("show", f"origin/{BRANCH}:{path}")

    def untouched(self):
        self.assertEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")
        self.assertEqual(self.git("branch", "--show-current"), "development")
        self.assertEqual((self.work / ".claude/methodology.toml").read_text(), self.before)

    def test_a_pre_commit_hook_that_cannot_be_installed_stops_the_update_before_touching_anything(self):
        # verifies: SPEC-0024/FM-04
        self.mth("branch", "chore", "secrets-hook")
        cfg = self.work / ".claude/methodology.toml"
        text = cfg.read_text().replace('\nhook = ""', '\nhook = "on"', 1).replace('pre_commit = "own"', 'pre_commit = "chain"', 1)
        cfg.write_text(text)
        test_mth._write(self.work / ".husky/pre-commit", "#!/bin/sh\nexit 0\n")
        self.git("add", "-A")
        self.mth("commit", "--type", "chore", "--scope", "methodology", "--summary", "enable the secrets hook",
                 "--body", "Chain a versioned pre-commit hook.", "--refs", "n/a")
        self.mth("integrate", "--title", "chore(methodology): enable the secrets hook", "--summary", "Hook.")
        self.before = cfg.read_text()
        self.git("config", "core.hooksPath", ".husky")
        out = self.mth("update", ok=False)
        self.assertIn("versionado", out)
        self.untouched()

    def test_applies_the_automatic_gaps_in_one_commit(self):
        # verifies: SPEC-0021/AC-03
        # verifies: SPEC-0021/AC-04
        # verifies: SPEC-0021/AC-06
        # verifies: SPEC-0021/AC-08
        out = self.mth("update")
        self.assertEqual(self.git("branch", "--show-current"), BRANCH)
        self.git("fetch", "-q")
        self.assertEqual(self.git("rev-list", "--count", f"origin/development..origin/{BRANCH}"), "1")
        data = tomllib.loads(self.on_branch(".claude/methodology.toml"))
        self.assertEqual(data["autonomy"], {"level": "full"})
        self.assertEqual(data["limits"]["max_file_lines"], 1000)
        self.assertEqual(data["models"]["review"], "opus")  # a decided value is never touched
        self.assertEqual(data["commands"]["test"], "true")
        self.assertIn("claude-methodology · configuración del repositorio", self.on_branch(".claude/methodology.toml"))
        self.assertIn(f"revisor-fallos@{FALLOS}", self.on_branch(".claude/agents/revisor-fallos.md"))
        self.assertIn("Metodología", self.on_branch("CLAUDE.md"))
        self.assertEqual(self.mth("update", "--plan", ok=True).count("[automatica]"), 0)
        files = self.git("show", "--name-only", "--format=", f"origin/{BRANCH}").splitlines()
        adr = next(f for f in files if f.endswith(UPDATE_ADR))
        text = self.on_branch(adr)
        self.assertIn("- Formato: compacto", text)
        for needle in ("`config`", "`agentes-desactualizados`", "`bloque`", "`hook`", "claude-methodology 0.", "ADR-0"):
            self.assertIn(needle, text)
        ident = adr.rsplit("/", 1)[1].split("-actual")[0]
        self.assertIn(f"Refs: {ident}", self.git("log", "-1", "--format=%B", f"origin/{BRANCH}"))
        self.assertIn("chore(methodology): update claude-methodology", out + self.git("log", "-1", "--format=%s"))
        self.assertEqual(compact.adr_problems(text, lang.ES), [])
        self.assertEqual(self.mth("trace").count("✗"), 0)
        self.assertNotIn("# viejo", (self.work / ".git/hooks/commit-msg").read_text())  # the clone's hook is refreshed

    def test_decisions_and_informative_gaps_are_listed_not_applied(self):
        # verifies: SPEC-0021/AC-05
        # verifies: SPEC-0021/AC-10
        out = self.mth("update")
        self.assertIn("Pendiente (decision) formato", out)
        self.assertIn("Pendiente (decision) agentes-perfil", out)
        self.assertIn("SPEC-0001", self.git("show", f"HEAD:specs/features/SPEC-0001-a.md"))
        self.assertNotIn("Formato: compacto", self.on_branch("specs/features/SPEC-0001-a.md"))
        self.assertFalse((self.work / ".claude/agents/revisor-adr.md").exists())
        adr = next(f for f in self.git("show", "--name-only", "--format=", "HEAD").splitlines() if f.endswith(UPDATE_ADR))
        self.assertIn("`formato` (decision)", (self.work / adr).read_text())

    def test_running_it_again_has_nothing_left_to_apply(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        out = self.mth("update", ok=False)
        self.assertIn("Nada que aplicar", out)
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")
        self.assertNotIn("[automatica]", self.mth("update", "--plan"))

    def test_resumes_on_the_update_branch(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        hook = self.work / ".git/hooks/commit-msg"
        hook.write_text(hook.read_text() + "# otra vez\n")
        (self.work / ".env").write_text("SECRETO=1\n")  # not owned by mth update: it must never be committed
        self.mth("update")  # on chore/update-methodology: applies only what is left, no second branch
        self.assertEqual(self.git("branch", "--show-current"), BRANCH)
        self.assertNotIn("# otra vez", hook.read_text())
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")  # the hook is not versioned
        self.assertNotIn(".env", self.git("ls-tree", "-r", "--name-only", "HEAD"))
        self.assertIn(".env", self.git("status", "--porcelain"))
        self.git("fetch", "-q")
        adrs = [f for f in self.git("ls-tree", "-r", "--name-only", f"origin/{BRANCH}").splitlines() if f.endswith(UPDATE_ADR)]
        self.assertEqual(len(adrs), 1)  # the resumed run extends the ADR of the branch
        text = self.on_branch(adrs[0])
        for gap in ("`config`", "`bloque`", "`hook`"):
            self.assertIn(gap, text)

    def test_resume_extends_the_adr_with_a_new_gap(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        self.mth("agents", "add", "revisor-seguridad")  # a second agent, outdated after the first run
        agent = self.work / ".claude/agents/revisor-seguridad.md"
        agent.write_text(agent.read_text().replace(f"revisor-seguridad@{SEGURIDAD}", "revisor-seguridad@0.9.0"))
        self.mth("update")
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "2")
        adrs = [f for f in self.git("ls-tree", "-r", "--name-only", "HEAD").splitlines() if f.endswith(UPDATE_ADR)]
        self.assertEqual(len(adrs), 1)
        text = (self.work / adrs[0]).read_text()
        for gap in ("`config`", "`bloque`", "`hook`", "`agentes-desactualizados`: revisor-fallos",
                    "`agentes-desactualizados`: revisor-seguridad"):
            self.assertIn(gap, text)
        self.assertEqual(text.count("`config`"), 1)  # earlier gaps are kept once, not repeated

    def test_resume_finishes_an_interrupted_run_with_only_its_own_paths(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        self.git("push", "-q", "origin", f":{BRANCH}")
        self.git("reset", "-q", "--soft", "HEAD~1")  # everything applied, nothing committed or pushed
        (self.work / ".env").write_text("SECRETO=1\n")
        self.mth("update")
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")
        self.git("fetch", "-q")
        files = self.git("ls-tree", "-r", "--name-only", f"origin/{BRANCH}")
        self.assertNotIn(".env", files)
        self.assertTrue(any(f.endswith(UPDATE_ADR) for f in files.splitlines()))
        self.assertIn(".env", self.git("status", "--porcelain"))

    def test_resume_with_only_foreign_changes_has_nothing_to_finish(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        (self.work / "x.txt").write_text("ajeno\n")
        self.assertIn("Nada que aplicar", self.mth("update", ok=False))
        self.assertEqual(self.git("rev-list", "--count", "origin/development..HEAD"), "1")

    def test_resume_pushes_a_commit_that_was_never_pushed(self):
        # verifies: SPEC-0021/AC-09
        self.mth("update")
        self.git("push", "-q", "origin", f":{BRANCH}")  # the push of the first run is lost
        self.assertEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")
        self.mth("update")
        self.assertNotEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")

    def test_refuses_without_creating_anything(self):
        # verifies: SPEC-0021/AC-07
        (self.work / "x.txt").write_text("sin confirmar\n")
        self.mth("update", ok=False)
        (self.work / "x.txt").unlink()
        self.untouched()
        self.git("push", "-q", "origin", "development:" + BRANCH)  # the branch already exists
        self.mth("update", ok=False)
        self.git("push", "-q", "origin", f":{BRANCH}")
        cfg = self.work / ".claude/methodology.toml"
        cfg.write_text(cfg.read_text() + "\n[intruso]\nx = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "wip: bad config")
        self.assertIn("intruso", self.mth("update", ok=False))
        self.assertEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")

    def test_not_adopted_fails(self):
        # verifies: SPEC-0021/AC-01
        (self.work / ".claude/methodology.toml").unlink()
        self.assertIn("mth-init", self.mth("update", ok=False))

    def test_nothing_to_apply_creates_nothing(self):
        # verifies: SPEC-0021/AC-08
        self.mth("update")
        self.mth("integrate", "--title", "chore(methodology): update claude-methodology", "--summary", "Actualización.")
        self.git("checkout", "-q", "development")
        self.git("pull", "-q")
        self.assertIn("Nada que aplicar", self.mth("update", ok=False))
        self.assertEqual(self.git("ls-remote", "--heads", "origin", BRANCH), "")


class AdrTextTests(unittest.TestCase):
    gaps = [update.Gap("config", update.AUTOMATIC, "limits", "añadir")]

    def test_adr_follows_the_compact_format_in_both_languages(self):
        # verifies: SPEC-0021/AC-08
        for vocab in (lang.ES, lang.EN):
            text = updating.adr_text("ADR-0002", "ADR-0001", self.gaps, [update.Gap("formato", update.DECISION, "3 docs", "x")],
                                     vocab, date(2026, 11, 25))
            self.assertTrue(compact.is_compact(text, vocab), vocab.code)
            self.assertEqual(compact.adr_problems(text, vocab), [], vocab.code)
            self.assertIn("ADR-0001", text)

    def test_missing_keys_are_added_without_touching_existing_lines(self):
        # verifies: SPEC-0021/AC-03
        template = tomllib.loads('forge = "github"\n[limits]\nmax_file_lines = 1000\nexclude = []\n[hooks]\ncommit_msg = "own"\n')
        text = '# mi config\nversion = 1\n[limits]\nmax_file_lines = 500  # mío\n'
        out = updating.with_keys(text, template, [("forge",), ("limits", "exclude"), ("hooks",)])
        data = tomllib.loads(out)
        self.assertEqual((data["forge"], data["limits"], data["hooks"]),
                         ("github", {"max_file_lines": 500, "exclude": ["**/*.lock", "**/package-lock.json",
                                                                         "**/migrations/**", "**/generated/**"]},
                          {"commit_msg": "own"}))
        self.assertIn("# mi config", out)
        self.assertIn("max_file_lines = 500  # mío", out)


class SkillTests(unittest.TestCase):
    plugin = HERE.parent / "plugins" / "methodology"
    skill = (plugin / "skills" / "mth-update" / "SKILL.md").read_text(encoding="utf-8")

    def frontmatter(self) -> dict[str, str]:
        head = self.skill.split("---")[1]
        return {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in head.strip().splitlines())}

    def test_only_the_person_launches_it_with_opus(self):
        # verifies: SPEC-0021/AC-12
        meta = self.frontmatter()
        self.assertEqual(meta["name"], "mth-update")
        self.assertEqual(meta["model"], "opus")
        self.assertEqual(meta["disable-model-invocation"], "true")

    def test_session_context_never_proposes_it(self):
        # verifies: SPEC-0021/AC-12
        for path in ("context/core.md", "context/unadopted.md", "hooks/hooks.json"):
            self.assertNotIn("mth-update", (self.plugin / path).read_text(encoding="utf-8"), path)

    def test_documents_the_flow_and_the_three_closing_lists(self):
        # verifies: SPEC-0021/AC-12
        for needle in ("mth update --plan", "`mth update`", "AskUserQuestion", "mth doctor", "mth trace",
                       "mth-integrate", "**aplicado**", "**decidido**", "**pendiente**"):
            self.assertIn(needle, self.skill)


if __name__ == "__main__":
    unittest.main()
