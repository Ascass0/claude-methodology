"""Tests of the diagnosis of an adopted repository against the installed plugin (SPEC-0021)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import catalog_support as support  # noqa: E402
import test_mth  # noqa: E402
from mthlib import agents, setup, update  # noqa: E402
from mthlib.config import load  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from mthlib.git import Git  # noqa: E402

COMPACT = "# SPEC-0001 · T\n\n- Estado: aprobada\n- Formato: compacto\n"
LEGACY = "# SPEC-0002 · T\n\n- Estado: aprobada\n"


class UpdateTestCase(unittest.TestCase):
    config_text = support.template_with_agents()

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
        path.write_text(path.read_text().replace("revisor-fallos@1.1.0", "revisor-fallos@1.0.0"), encoding="utf-8")
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

    def test_registry_matches_the_spec(self):
        # verifies: SPEC-0021/AC-11
        spec = next((HERE.parent / "specs" / "features").glob("SPEC-0021-*.md")).read_text(encoding="utf-8")
        for kind in update.REGISTRY:
            self.assertIn(f"| `{kind.id}` |", spec)
            self.assertIn(f"`{kind.clase}`", spec)


if __name__ == "__main__":
    unittest.main()
