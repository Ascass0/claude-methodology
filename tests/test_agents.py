"""Tests of ``mth agents`` and the doctor warnings about catalog agents (SPEC-0012)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import catalog_support as support
import test_mth
from mthlib import agents, catalog, cli, setup
from mthlib.config import load
from mthlib.errors import MthError

CATALOG = support.CATALOG
BASE_REVIEWERS = ["verificador", "revisor-seguridad", "revisor-fallos", "revisor-adr", "revisor-diseno",
                  "revisor-parsimonia"]


class AgentsTestCase(unittest.TestCase):
    config_text = support.template_with_agents()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env={**os.environ, **test_mth.GIT_ENV})
        self.write(".claude/methodology.toml", self.config_text)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def manager(self, catalog_dir: Path = CATALOG) -> agents.Manager:
        return agents.Manager(load(self.root), catalog_dir)

    def quiet(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = fn(*args)
        self.output = out.getvalue()
        return result

    def add(self, *names: str, profile: str | None = None, replace: bool = False) -> int:
        return self.quiet(self.manager().add, list(names), profile, replace)

    def mth(self, *argv: str) -> int:
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            return self.quiet(cli.main, list(argv))
        finally:
            os.chdir(cwd)

    def review(self) -> tuple[list[str], dict]:
        cfg = load(self.root)
        return cfg["review"]["agents"], cfg["review"]["paths"]

    def snapshot(self) -> dict[str, str]:
        return {str(p.relative_to(self.root)): p.read_text(encoding="utf-8")
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts}


class AddTests(AgentsTestCase):
    def test_unmet_requirements_block_the_install_and_name_the_key(self):
        # verifies: SPEC-0012/AC-03
        self.write(".claude/methodology.toml", self.config_text.replace(
            '[agents.lector-estado]\ndatabases = { estado = "data/state.db" }', "[agents.lector-estado]"))
        before = self.snapshot()
        self.assertEqual(self.mth("agents", "add", "lector-estado"), 1)
        self.assertIn("agents.lector-estado.databases", self.output)
        self.assertEqual(self.snapshot(), before)

    def test_profile_skips_agents_with_unmet_requirements(self):
        self.write(".claude/methodology.toml", self.config_text.replace('test = "pytest -q"', 'test = ""'))
        self.assertEqual(self.add(profile="base"), 0)
        self.assertIn("diagnosticador: no se instala; requisitos sin configurar: commands.test", self.output)
        self.assertFalse((self.root / ".claude/agents/diagnosticador.md").exists())
        self.assertTrue((self.root / ".claude/agents/revisor-seguridad.md").exists())

    def test_reviewers_follow_review_order_and_bring_their_paths(self):
        # verifies: SPEC-0012/AC-04
        self.assertEqual(self.mth("agents", "add", "--profile", "base"), 0)
        reviewers, paths = self.review()
        self.assertEqual(reviewers, BASE_REVIEWERS)
        self.assertIn("specs/adr/**", paths["revisor-adr"])
        self.assertEqual(set(paths), {"revisor-adr"})
        text = self.read(".claude/methodology.toml")
        self.assertIn("# Revisores en orden de precedencia", text)  # comments survive
        self.assertIn("# revisor-contratos =", text)

    def test_order_does_not_depend_on_the_install_sequence_and_keeps_repo_reviewers(self):
        # verifies: SPEC-0012/AC-04
        self.write(".claude/methodology.toml", self.config_text.replace(
            'agents = ["verificador"]', 'agents = ["verificador", "revisor-contratos"]').replace(
            '# revisor-contratos = ["subagents/**", "schemas/**"]', 'revisor-contratos = ["schemas/**"]'))
        for name in reversed(BASE_REVIEWERS[1:]):
            self.add(name)
        reviewers, paths = self.review()
        # repo reviewers have no review.order: they keep their place; catalog ones sort among themselves
        self.assertEqual(reviewers, ["verificador", "revisor-contratos", "revisor-seguridad", "revisor-fallos",
                                     "revisor-adr", "revisor-diseno", "revisor-parsimonia"])
        self.assertEqual(paths["revisor-contratos"], ["schemas/**"])

    def test_ordering_rule(self):
        orders = {"revisor-seguridad": 10, "revisor-fallos": 20, "revisor-adr": 25}
        self.assertEqual(agents.ordered_reviewers([], "revisor-fallos", 20, orders), ["revisor-fallos"])
        self.assertEqual(agents.ordered_reviewers(["revisor-adr", "verificador"], "revisor-seguridad", 10, orders),
                         ["revisor-adr", "verificador", "revisor-seguridad"])
        self.assertEqual(agents.ordered_reviewers(["verificador", "propio", "revisor-adr"], "revisor-fallos", 20, orders),
                         ["verificador", "propio", "revisor-fallos", "revisor-adr"])

    def test_widened_review_paths_are_kept(self):
        self.add("revisor-adr")
        text = self.read(".claude/methodology.toml").replace('revisor-adr = [', 'revisor-adr = ["contracts/**", ', 1)
        self.write(".claude/methodology.toml", text)
        self.quiet(self.manager().sync, [], False)
        self.assertEqual(self.review()[1]["revisor-adr"][0], "contracts/**")

    def test_foreign_agent_with_the_same_name_needs_replace(self):
        # verifies: SPEC-0012/AC-07
        own = self.write(".claude/agents/revisor-seguridad.md", "---\nname: revisor-seguridad\n---\nPropio.\n")
        self.assertEqual(self.add("revisor-seguridad"), 1)
        self.assertEqual(own.read_text(encoding="utf-8"), "---\nname: revisor-seguridad\n---\nPropio.\n")
        self.assertIn("--replace", self.output)
        self.assertEqual(self.add("revisor-seguridad", replace=True), 0)
        self.assertIsNotNone(catalog.installed(own.read_text(encoding="utf-8"), None))

    def test_installs_files_shim_and_one_settings_entry_keeping_other_keys(self):
        # verifies: SPEC-0012/AC-17
        self.write(".claude/settings.json", json.dumps({"enabledPlugins": {"x@y": True},
                                                        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}))
        self.add("revisor-fallos")
        self.add("revisor-diseno")
        self.quiet(self.manager().sync, [], False)
        settings = json.loads(self.read(".claude/settings.json"))
        self.assertEqual(settings["enabledPlugins"], {"x@y": True})
        ours = [e for e in settings["hooks"]["PreToolUse"] if agents._is_ours(e)]
        self.assertEqual(len(ours), 1)
        self.assertEqual(ours[0]["matcher"], agents.HOOK_MATCHER)
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
        shim = self.root / agents.SHIM
        self.assertEqual(shim.read_text(encoding="utf-8"),
                         (CATALOG / "_shared/mth-agent-guard.sh").read_text(encoding="utf-8"))
        self.assertTrue(os.access(shim, os.X_OK))
        self.assertTrue((self.root / ".claude/mth/agents/revisor-fallos.guard.toml").is_file())

    def test_hook_command_blocks_subagents_when_the_shim_is_missing(self):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        run = lambda payload: subprocess.run(["sh", "-c", agents.HOOK_COMMAND], input=json.dumps(payload),
                                             env=env, capture_output=True, text=True)
        main = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        self.assertEqual(run(main).returncode, 0)
        proc = run({**main, "agent_id": "a", "agent_type": "revisor-fallos"})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("mth agents sync", proc.stderr)

    def test_hook_entry_has_a_timeout_and_removal_keeps_foreign_hooks_in_a_shared_entry(self):
        self.add("revisor-fallos")
        settings = json.loads(self.read(".claude/settings.json"))
        ours = settings["hooks"]["PreToolUse"][-1]
        self.assertEqual(ours["hooks"][0]["timeout"], agents.HOOK_TIMEOUT)
        ours["hooks"].append({"type": "command", "command": "echo propio"})
        self.write(".claude/settings.json", json.dumps(settings))
        self.mth("agents", "remove", "revisor-fallos")
        left = json.loads(self.read(".claude/settings.json"))["hooks"]["PreToolUse"]
        self.assertEqual(left, [{"matcher": agents.HOOK_MATCHER, "hooks": [{"type": "command", "command": "echo propio"}]}])

    def test_settings_with_an_unexpected_shape_are_rejected(self):
        self.write(".claude/settings.json", json.dumps({"hooks": {"PreToolUse": {"x": 1}}}))
        with self.assertRaises(MthError) as ctx:
            self.add("revisor-fallos")
        self.assertIn("forma esperada", ctx.exception.message)

    def test_a_failure_halfway_never_leaves_an_agent_without_its_hook(self):
        real = agents.atomic_write

        def failing(path, text, mode=None):
            if path.suffix == ".md":
                raise OSError("disco lleno")
            real(path, text, mode)
        with mock.patch.object(agents, "atomic_write", side_effect=failing), self.assertRaises(OSError):
            self.add("revisor-fallos")
        self.assertTrue(agents.has_hook(agents.read_settings(self.root)))
        self.assertTrue((self.root / agents.SHIM).is_file())
        self.assertFalse((self.root / ".claude/agents/revisor-fallos.md").exists())
        self.assertEqual(self.add("revisor-fallos"), 0)  # a re-run completes the install

    def test_unreadable_settings_abort_without_writing(self):
        # verifies: SPEC-0012/AC-17
        self.write(".claude/settings.json", "{roto")
        before = self.snapshot()
        with self.assertRaises(MthError):
            self.add("revisor-fallos")
        self.assertEqual(self.snapshot(), before)

    def test_template_error_aborts_without_writing(self):
        # verifies: SPEC-0012/AC-02
        broken = Path(tempfile.mkdtemp()) / "catalog"
        self.addCleanup(shutil.rmtree, broken.parent)
        shutil.copytree(CATALOG, broken)
        tmpl = broken / "revisor-parsimonia" / "agent.md.tmpl"
        tmpl.write_text(tmpl.read_text(encoding="utf-8") + "{{vars.no_existe}}\n", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(catalog.TemplateError):
            self.quiet(self.manager(broken).add, ["revisor-fallos", "revisor-parsimonia"], None, False)
        self.assertEqual(self.snapshot(), before)

    def test_worktree_agents_ignore_claude_worktrees(self):
        self.write(".gitignore", "__pycache__/")
        self.add("diagnosticador")
        self.add("ingeniero-rendimiento")
        self.assertEqual(self.read(".gitignore").count(".claude/worktrees/"), 1)
        self.assertTrue(self.read(".gitignore").startswith("__pycache__/\n"))

    def test_english_docs_get_a_notice(self):
        self.write(".claude/methodology.toml", self.config_text.replace('docs = "es"', 'docs = "en"'))
        self.add("revisor-fallos")
        self.assertIn("en español", self.output)


class SyncTests(AgentsTestCase):
    def test_sync_keeps_the_local_section(self):
        # verifies: SPEC-0012/AC-05
        self.add("revisor-seguridad")
        path = self.root / ".claude/agents/revisor-seguridad.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            catalog.LOCAL_BEGIN, catalog.LOCAL_BEGIN + "\nActivos: tokens de despliegue.\n"), encoding="utf-8")
        old = Path(tempfile.mkdtemp()) / "catalog"
        self.addCleanup(shutil.rmtree, old.parent)
        shutil.copytree(CATALOG, old)
        meta = old / "revisor-seguridad" / "meta.toml"
        meta.write_text(meta.read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "1.1.0"'),
                        encoding="utf-8")
        self.assertEqual(self.quiet(self.manager(old).sync, ["revisor-seguridad"], False), 0)
        text = path.read_text(encoding="utf-8")
        self.assertIn("Activos: tokens de despliegue.", text)
        self.assertIn("revisor-seguridad@1.1.0", text)

    def test_sync_refuses_hand_edits_without_force(self):
        # verifies: SPEC-0012/AC-06
        self.add("revisor-diseno")
        path = self.root / ".claude/agents/revisor-diseno.md"
        edited = path.read_text(encoding="utf-8").replace("## ", "## Editado ", 1)
        path.write_text(edited, encoding="utf-8")
        self.assertEqual(self.mth("agents", "sync", "revisor-diseno"), 1)
        self.assertIn("--force", self.output)
        self.assertIn("-## Editado", self.output)  # the diff is shown
        self.assertEqual(path.read_text(encoding="utf-8"), edited)
        self.assertEqual(self.mth("agents", "sync", "--force", "revisor-diseno"), 0)
        self.assertNotIn("## Editado", path.read_text(encoding="utf-8"))

    def test_diff_and_list(self):
        self.add("revisor-diseno")
        self.assertEqual(self.mth("agents", "diff", "revisor-diseno"), 0)
        self.assertEqual(self.output, "")
        self.assertEqual(self.mth("agents", "list"), 0)
        self.assertIn("revisor-diseno v1.0.0", self.output)
        self.assertIn("instalado (v1.0.0)", self.output)
        self.assertIn("modelo sugerido: opus", self.output)

    def test_sync_rejects_agents_not_from_the_catalog(self):
        self.write(".claude/agents/propio.md", "---\nname: propio\n---\n")
        with self.assertRaises(MthError):
            self.quiet(self.manager().sync, ["propio"], False)


class RemoveTests(AgentsTestCase):
    def test_remove_deletes_files_and_review_entries(self):
        # verifies: SPEC-0012/AC-14
        self.add("revisor-adr", "revisor-fallos")
        self.assertEqual(self.mth("agents", "remove", "revisor-adr"), 0)
        self.assertFalse((self.root / ".claude/agents/revisor-adr.md").exists())
        self.assertFalse((self.root / ".claude/mth/agents/revisor-adr.guard.toml").exists())
        self.assertEqual(self.review(), (["verificador", "revisor-fallos"], {}))
        self.assertTrue((self.root / agents.SHIM).exists())

    def test_removing_the_last_agent_drops_the_hook_and_the_shim(self):
        # verifies: SPEC-0012/AC-14
        self.write(".claude/settings.json", json.dumps({"enabledPlugins": {"x@y": True}}))
        self.add("revisor-fallos")
        self.mth("agents", "remove", "revisor-fallos")
        self.assertFalse((self.root / agents.SHIM).exists())
        self.assertEqual(json.loads(self.read(".claude/settings.json")), {"enabledPlugins": {"x@y": True}})
        self.assertEqual(self.review(), (["verificador"], {}))

    def test_foreign_agents_are_not_removed(self):
        self.write(".claude/agents/propio.md", "---\nname: propio\n---\n")
        self.assertEqual(self.mth("agents", "remove", "propio"), 1)
        self.assertTrue((self.root / ".claude/agents/propio.md").exists())


class DoctorTests(AgentsTestCase):
    def findings(self, catalog_dir: Path = CATALOG) -> list[str]:
        launcher = setup.register_launcher(setup.Git(self.root))
        return agents.doctor_findings(self.root, load(self.root), launcher, catalog_dir)

    def test_warns_about_outdated_edited_empty_local_and_missing_hook(self):
        # verifies: SPEC-0012/AC-13
        self.add("revisor-seguridad", "revisor-fallos", "revisor-diseno")
        path = self.root / ".claude/agents/revisor-seguridad.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            catalog.LOCAL_BEGIN, catalog.LOCAL_BEGIN + "\nAtacante: usuario anónimo.\n"), encoding="utf-8")
        self.assertEqual(self.findings(), [])
        newer = Path(tempfile.mkdtemp()) / "catalog"
        self.addCleanup(shutil.rmtree, newer.parent)
        shutil.copytree(CATALOG, newer)
        meta = newer / "revisor-fallos" / "meta.toml"
        meta.write_text(meta.read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "1.2.0"'),
                        encoding="utf-8")
        diseno = self.root / ".claude/agents/revisor-diseno.md"
        diseno.write_text(diseno.read_text(encoding="utf-8").replace("## ", "## X", 1), encoding="utf-8")
        path.write_text(path.read_text(encoding="utf-8").replace("\nAtacante: usuario anónimo.\n", ""), encoding="utf-8")
        self.write(".claude/settings.json", "{}")
        found = "\n".join(self.findings(newer))
        self.assertIn("revisor-fallos: desactualizado (catálogo v1.2.0)", found)
        self.assertIn("revisor-diseno: editado a mano", found)
        self.assertIn("revisor-seguridad: su sección local obligatoria está vacía", found)
        self.assertIn("Falta la entrada PreToolUse", found)

    def test_warns_about_missing_guard_shim_launcher_and_disabled_hooks(self):
        self.add("revisor-fallos")
        (self.root / ".claude/mth/agents/revisor-fallos.guard.toml").unlink()
        (self.root / agents.SHIM).unlink()
        self.write(".claude/settings.local.json", json.dumps({"disableAllHooks": True}))
        found = "\n".join(self.findings())
        self.assertIn("falta .claude/mth/agents/revisor-fallos.guard.toml", found)
        self.assertIn("Falta .claude/hooks/mth-agent-guard", found)
        self.assertIn("disableAllHooks", found)
        (self.root / ".git/mth/launcher").write_text("/no/existe\n/no/existe\n", encoding="utf-8")
        found = "\n".join(agents.doctor_findings(self.root, load(self.root), self.root / ".git/mth/launcher"))
        self.assertIn("No hay lanzador registrado", found)

    def test_doctor_reports_them_as_warnings(self):
        self.add("revisor-fallos")
        self.write(".claude/settings.json", "{}")
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                setup.doctor(self.root)
        finally:
            os.chdir(cwd)
        self.assertIn("⚠ Falta la entrada PreToolUse", out.getvalue())

    def test_guard_without_header_is_reported_and_can_be_synced_or_removed(self):
        # verifies: SPEC-0012/AC-21
        self.add("revisor-fallos", "revisor-diseno")
        (self.root / ".claude/agents/revisor-fallos.md").write_text("---\nname: revisor-fallos\n---\nAdaptado.\n",
                                                                    encoding="utf-8")
        found = "\n".join(self.findings())
        self.assertIn("revisor-fallos: tiene guard pero su .md no tiene cabecera", found)
        self.assertEqual(self.mth("agents", "sync", "revisor-fallos"), 1)
        self.assertEqual(self.mth("agents", "sync", "--force", "revisor-fallos"), 0)
        self.assertEqual(self.findings(), [])
        (self.root / ".claude/agents/revisor-diseno.md").write_text("---\nname: revisor-diseno\n---\n", encoding="utf-8")
        self.assertEqual(self.mth("agents", "remove", "revisor-diseno"), 0)
        self.assertFalse((self.root / ".claude/mth/agents/revisor-diseno.guard.toml").exists())

    def test_unreadable_settings_files_are_reported(self):
        self.add("revisor-fallos")
        self.write(".claude/settings.local.json", "{roto")
        self.assertIn("No se puede leer .claude/settings.local.json", "\n".join(self.findings()))

    def test_no_catalog_agents_no_findings(self):
        self.assertEqual(self.findings(), [])


if __name__ == "__main__":
    unittest.main()
