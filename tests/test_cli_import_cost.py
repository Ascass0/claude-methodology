"""Each command imports only the modules it uses, and a deferred import cannot hide a broken one (PLAN-0010)."""
from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "methodology" / "scripts"
PACKAGE = SCRIPTS / "mthlib"
sys.path.insert(0, str(SCRIPTS))

# What the parser and the error boundary need; everything else belongs to the command that uses it.
OTHER_COMMANDS = ("mthlib.flow", "mthlib.review", "mthlib.update", "mthlib.updating", "mthlib.survey", "mthlib.audit",
                  "mthlib.db_query", "mthlib.setup", "mthlib.agents", "mthlib.smoke", "mthlib.tools", "mthlib.session",
                  "mthlib.config", "mthlib.guard", "mthlib.agent_guard")


def loaded_by(args: list[str], cwd: str) -> set[str]:
    """Modules of ``mthlib`` a fresh interpreter has loaded after ``mth <args>`` (the command may fail: it is not a repository)."""
    code = ("import runpy, sys\n"
            f"sys.argv = ['mth.py', *{args!r}]\n"
            f"try:\n    runpy.run_path({str(SCRIPTS / 'mth.py')!r}, run_name='__main__')\nexcept SystemExit:\n    pass\n"
            "import json; print(json.dumps(sorted(m for m in sys.modules if m.startswith('mthlib'))))")
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=cwd, check=True)
    return set(json.loads(done.stdout.splitlines()[-1]))


class CommandImportTests(unittest.TestCase):
    def test_a_command_does_not_load_the_modules_of_the_others(self):
        # regression: cli.py imported every module of the package before running any command
        cases = {("--version",): ("mthlib.flow", "mthlib.config", "mthlib.setup", "mthlib.review", "mthlib.agents"),
                 ("plan", "list"): ("mthlib.update", "mthlib.updating", "mthlib.survey", "mthlib.audit",
                                    "mthlib.db_query", "mthlib.setup", "mthlib.smoke", "mthlib.tools", "mthlib.guard"),
                 ("tools", "list"): ("mthlib.flow", "mthlib.review", "mthlib.update", "mthlib.survey", "mthlib.audit",
                                     "mthlib.db_query", "mthlib.setup", "mthlib.session")}
        with tempfile.TemporaryDirectory() as outside:
            for args, forbidden in cases.items():
                loaded = loaded_by(list(args), outside)
                for module in forbidden:
                    self.assertNotIn(module, loaded, f"mth {' '.join(args)} loads {module}")

    def test_the_version_flag_loads_nothing_beyond_the_parser_and_the_error_boundary(self):
        # regression: even `mth --version` paid for the whole package
        with tempfile.TemporaryDirectory() as outside:
            loaded = loaded_by(["--version"], outside)
        for module in OTHER_COMMANDS:
            self.assertNotIn(module, loaded)


class LocalImportTests(unittest.TestCase):
    def test_every_import_of_the_package_names_a_module_and_a_name_that_exist(self):
        # regression: a deferred import moves a wrong name from start-up to the moment a command runs
        broken = []
        for path in sorted(PACKAGE.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.ImportFrom) or node.level != 1:
                    continue
                module = importlib.import_module(f"mthlib.{node.module}" if node.module else "mthlib")
                for alias in node.names:
                    if not hasattr(module, alias.name) and not (PACKAGE / f"{alias.name}.py").exists():
                        broken.append(f"{path.name}:{node.lineno}: {node.module or '.'} has no {alias.name}")
        self.assertEqual(broken, [])

    def test_every_module_imports_on_its_own_so_no_import_cycle_is_hidden(self):
        # regression: a cycle only shows when the modules load in another order
        failures = []
        for path in sorted(PACKAGE.glob("*.py")):
            name = path.stem
            if name == "__init__":
                continue
            done = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import mthlib.{name}"],
                                  capture_output=True, text=True)
            if done.returncode != 0:
                failures.append(f"{name}: {done.stderr.strip().splitlines()[-1] if done.stderr.strip() else done.returncode}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
