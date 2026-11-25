"""Tests of the agent catalog and its deterministic rendering (SPEC-0012)."""
from __future__ import annotations

import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

import catalog_support as support
from mthlib import catalog
from mthlib.config import parse
from mthlib.errors import MthError

CATALOG = support.CATALOG
FRONTMATTER_KEYS = {"name", "description", "tools", "isolation"}
WRITE_TOOLS = {"Write", "Edit"}
MODEL_ROLES = {"review", "task", "documenter", "none"}


def _evals(name: str) -> dict:
    return tomllib.loads((CATALOG / name / "evals.toml").read_text(encoding="utf-8"))


_INTERNAL_ID = re.compile(r"\b(?:SPEC|ADR)-\d{4}")


class CatalogStructureTests(unittest.TestCase):
    """The catalog content itself: what check_catalog.py validated in the delivery."""

    def setUp(self):
        self.names = catalog.names(CATALOG)

    def test_profiles_match_directories(self):
        # unit: catalog.profiles
        profiles = catalog.profiles(CATALOG)
        listed = [a for p in profiles.values() for a in p["agents"]]
        self.assertEqual(sorted(listed), self.names)
        self.assertEqual(len(set(listed)), len(listed))
        for name in self.names:
            for prof in catalog.load_meta(CATALOG, name)["profiles"]:
                self.assertIn(name, profiles[prof]["agents"], name)

    def test_meta_is_complete_and_review_orders_are_unique(self):
        # unit: catalog.load_meta
        orders = {}
        for name in self.names:
            meta = catalog.load_meta(CATALOG, name)
            with self.subTest(agent=name):
                self.assertEqual(meta["name"], name)
                self.assertRegex(meta["version"], r"^\d+\.\d+\.\d+$")
                self.assertIn(meta["kind"], catalog.KINDS)
                self.assertIn(meta["model_role"], MODEL_ROLES)
                for key in ("summary", "origin", "profiles"):
                    self.assertTrue(meta.get(key), key)
                if meta["kind"] == "revisor":
                    self.assertEqual(meta["model_role"], "review")
                    self.assertNotIn(meta["review"]["order"], orders)
                    orders[meta["review"]["order"]] = name
                else:
                    self.assertNotIn("review", meta)
        self.assertEqual([orders[k] for k in sorted(orders)],
                         ["revisor-seguridad", "revisor-fallos", "revisor-adr", "revisor-diseno", "revisor-parsimonia"])

    def test_frontmatter_has_neither_model_nor_hooks_and_every_agent_has_a_guard(self):
        # verifies: SPEC-0012/AC-15
        for name in self.names:
            meta = catalog.load_meta(CATALOG, name)
            text = (CATALOG / name / "agent.md.tmpl").read_text(encoding="utf-8")
            fm = catalog.frontmatter(text)
            guard = tomllib.loads((CATALOG / name / "guard.toml").read_text(encoding="utf-8"))
            with self.subTest(agent=name):
                self.assertLessEqual(set(fm), FRONTMATTER_KEYS)
                self.assertNotIn("model", fm)
                self.assertNotIn("hooks", fm)
                self.assertEqual(fm["name"], name)
                self.assertTrue(80 <= len(fm["description"]) <= 700, "description is the routing rule")
                if meta["kind"] == "principal":
                    self.assertEqual(guard.get("delegate"), "global")
                else:
                    self.assertNotIn("delegate", guard)

    def test_tools_and_guard_are_coherent(self):
        # unit: catalog.render
        for name in self.names:
            meta = catalog.load_meta(CATALOG, name)
            if meta["kind"] == "principal":
                continue
            text = (CATALOG / name / "agent.md.tmpl").read_text(encoding="utf-8")
            tools = catalog.tools_of(text)
            rules = tomllib.loads(catalog.render(CATALOG, name, support.fixture_config().data).guard_toml)
            worktree = catalog.frontmatter(text).get("isolation") == "worktree"
            with self.subTest(agent=name):
                self.assertTrue(tools, "a subagent declares its tools")
                bash_mode = (rules.get("bash") or {}).get("mode", "deny")
                self.assertEqual(bash_mode != "deny", "Bash" in tools)
                write = rules.get("write") or {}
                self.assertEqual(bool(write.get("allow")), bool(tools & WRITE_TOOLS))
                self.assertEqual(bool(write.get("in_worktree")), worktree and bool(tools & WRITE_TOOLS))

    def test_evals_meet_the_minimums(self):
        # unit: catalog.load_meta
        for name in self.names:
            meta, evals = catalog.load_meta(CATALOG, name), _evals(name)
            with self.subTest(agent=name):
                self.assertTrue(evals.get("guard"), "every agent has a guard, so [[guard]] cases")
                if meta["kind"] == "revisor":
                    self.assertGreaterEqual(len(evals.get("scope", [])), 2)
                elif meta["kind"] == "trabajador":
                    self.assertGreaterEqual(len(evals.get("routing", [])), 2)
                else:
                    self.assertTrue(evals.get("behavior"))
                for case in evals.get("routing", []):
                    self.assertIn(case.get("expect") or case.get("expect_not"), self.names)

    def test_shim_has_valid_syntax(self):
        # unit: mth-agent-guard.sh
        import subprocess
        shim = CATALOG / "_shared" / "mth-agent-guard.sh"
        self.assertEqual(subprocess.run(["sh", "-n", str(shim)]).returncode, 0)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.config = support.fixture_config().data

    def test_rendering_is_deterministic(self):
        # verifies: SPEC-0012/AC-01
        for name in catalog.names(CATALOG):
            with self.subTest(agent=name):
                first = catalog.render(CATALOG, name, self.config)
                self.assertEqual(first, catalog.render(CATALOG, name, self.config))
                self.assertNotIn("{{", first.agent_md + first.guard_toml)
                tomllib.loads(first.guard_toml)

    def test_rendering_is_deterministic_without_optional_variables(self):
        # verifies: SPEC-0012/AC-01
        bare = parse(Path("/nonexistent"), support.template_with_agents("")).data
        for name in catalog.names(CATALOG):
            if catalog.missing_requirements(catalog.load_meta(CATALOG, name), bare):
                continue
            first = catalog.render(CATALOG, name, bare)
            with self.subTest(agent=name):
                self.assertEqual(first, catalog.render(CATALOG, name, bare))

    def test_header_and_reviewer_output(self):
        # unit: catalog.render
        for name in catalog.names(CATALOG):
            r = catalog.render(CATALOG, name, self.config)
            with self.subTest(agent=name):
                body = r.agent_md.split("\n---\n", 1)[1]
                self.assertTrue(body.startswith(f"<!-- mth:template {name}@{r.version} sha256={r.digest} -->\n"))
                self.assertEqual(catalog.installed(r.agent_md, r.guard_toml),
                                 catalog.Installed(name, r.version, False))
                if r.review is not None:
                    self.assertIn("BLOQUEANTES: <n>", r.agent_md)

    def test_installed_files_carry_no_plugin_internal_ids(self):
        # verifies: SPEC-0012/AC-28
        for shared in (CATALOG / "_shared").glob("*"):
            with self.subTest(shared=shared.name):
                self.assertIsNone(_INTERNAL_ID.search(shared.read_text(encoding="utf-8")))
        for name in catalog.names(CATALOG):
            r = catalog.render(CATALOG, name, self.config)
            with self.subTest(agent=name):
                self.assertIsNone(_INTERNAL_ID.search(r.agent_md + (r.guard_toml or "")))

    def test_unknown_variable_aborts(self):
        # verifies: SPEC-0012/AC-02
        with tempfile.TemporaryDirectory() as tmp:
            cat = Path(tmp) / "catalog"
            shutil.copytree(CATALOG, cat)
            tmpl = cat / "revisor-diseno" / "agent.md.tmpl"
            tmpl.write_text(tmpl.read_text(encoding="utf-8") + "\n{{config.paths.no_existe}}\n", encoding="utf-8")
            with self.assertRaises(catalog.TemplateError) as ctx:
                catalog.render(cat, "revisor-diseno", self.config)
            self.assertIn("config.paths.no_existe", ctx.exception.message)

    def test_unmet_requirements_name_the_key(self):
        # verifies: SPEC-0012/AC-03
        bare = parse(Path("/nonexistent"), support.template_with_agents().replace(
            '[agents.lector-estado]\ndatabases = { estado = "data/state.db" }', "[agents.lector-estado]")).data
        with self.assertRaises(catalog.TemplateError) as ctx:
            catalog.render(CATALOG, "lector-estado", bare)
        self.assertIn("agents.lector-estado.databases", ctx.exception.message)
        no_tests = parse(Path("/nonexistent"), support.template_with_agents("")).data
        self.assertEqual(catalog.missing_requirements(catalog.load_meta(CATALOG, "diagnosticador"), no_tests),
                         ["commands.test"])

    def test_local_section_is_kept_and_not_counted_as_an_edit(self):
        # verifies: SPEC-0012/AC-05
        for name in catalog.names(CATALOG):
            if not catalog.load_meta(CATALOG, name).get("local_section"):
                continue
            r = catalog.render(CATALOG, name, self.config)
            edited = r.agent_md.replace(catalog.LOCAL_BEGIN, catalog.LOCAL_BEGIN + "\nAmenaza: X\n", 1)
            with self.subTest(agent=name):
                self.assertFalse(catalog.installed(edited, r.guard_toml).edited)
                again = catalog.render(CATALOG, name, self.config, installed_md=edited)
                self.assertIn("Amenaza: X", again.agent_md)
                self.assertEqual(again.digest, r.digest)

    def test_edits_to_the_generated_part_or_the_guard_are_detected(self):
        # verifies: SPEC-0012/AC-06
        for name in catalog.names(CATALOG):
            r = catalog.render(CATALOG, name, self.config)
            with self.subTest(agent=name):
                self.assertTrue(catalog.installed(r.agent_md.replace("## ", "## X", 1), r.guard_toml).edited)
                self.assertTrue(catalog.installed(r.agent_md, r.guard_toml + "\n# x\n").edited)

    def test_agent_without_header_is_not_from_the_catalog(self):
        # unit: catalog.installed
        self.assertIsNone(catalog.installed("---\nname: x\n---\nhola\n", None))

    def test_unknown_agent_is_rejected(self):
        # unit: catalog.load_meta
        for name in ("no-existe", "../revisor-adr", "_shared"):
            with self.subTest(name=name), self.assertRaises(MthError):
                catalog.load_meta(CATALOG, name)


class AgentsConfigTests(unittest.TestCase):
    def parse(self, extra: str):
        return parse(Path("/nonexistent"), 'version = 1\n[commands]\ntest = ""\n' + extra)

    def test_template_example_block_is_valid(self):
        # unit: config.parse
        cfg = support.fixture_config()
        self.assertEqual(cfg["agents"]["lector-estado"]["databases"], {"estado": "data/state.db"})

    def test_agents_table_is_optional(self):
        # unit: config.parse
        self.assertEqual(self.parse("")["agents"], {})

    def test_unknown_variable_is_an_error_naming_the_key(self):
        # verifies: SPEC-0012/AC-19
        with self.assertRaises(MthError) as ctx:
            self.parse('[agents.lector-estado]\ndatabase = { a = "a.db" }\n')
        self.assertIn("agents.lector-estado.database", ctx.exception.message)

    def test_unknown_variable_of_an_agent_without_variables_is_an_error_naming_the_key(self):
        # verifies: SPEC-0012/AC-19
        with self.assertRaises(MthError) as ctx:
            self.parse('[agents.diagnosticador]\nmax_rows = 5\n')
        self.assertIn("agents.diagnosticador.max_rows", ctx.exception.message)

    def test_unknown_agent_and_wrong_type_are_errors(self):
        # unit: config.parse
        with self.assertRaises(MthError):
            self.parse('[agents.no-existe]\nx = 1\n')
        with self.assertRaises(MthError) as ctx:
            self.parse('[agents.lector-estado]\nmax_rows = "200"\n')
        self.assertIn("agents.lector-estado.max_rows", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
