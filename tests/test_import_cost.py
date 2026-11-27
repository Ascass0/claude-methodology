"""What the hooks import: they run on every Bash call and every session, so they must stay light (PLAN-0009)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "methodology" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mthlib import config, guard  # noqa: E402

_LOADED = "import sys, json; print(json.dumps(sorted(sys.modules)))"


def modules_after(code: str) -> set[str]:
    """Modules a fresh interpreter has loaded once ``code`` ran (``-I``: nothing from the caller's environment)."""
    prelude = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r})\n"
    out = subprocess.run([sys.executable, "-I", "-c", prelude + code + "\n" + _LOADED], capture_output=True, text=True, check=True)
    return set(json.loads(out.stdout.splitlines()[-1]))


class ImportCostTests(unittest.TestCase):
    def test_loading_the_configuration_does_not_load_the_network_stack(self):
        # regression: config pulled urllib.request into every command
        loaded = modules_after("import mthlib.config")
        self.assertNotIn("urllib.request", loaded)
        self.assertNotIn("http.client", loaded)

    def test_the_guard_entry_point_skips_the_cli_and_the_configuration_for_a_plain_command(self):
        # regression: the guard imported the whole CLI on every Bash call
        run = ("import io, runpy, sys\n"
               "sys.argv = ['mth.py', 'guard']\n"
               "sys.stdin = io.StringIO('{\"tool_name\": \"Bash\", \"tool_input\": {\"command\": \"ls -la\"}, \"cwd\": \".\"}')\n"
               f"try:\n    runpy.run_path({str(SCRIPTS / 'mth.py')!r}, run_name='__main__')\nexcept SystemExit as exc:\n"
               "    assert exc.code == 0, exc.code\n")
        loaded = modules_after(run)
        for heavy in ("mthlib.cli", "mthlib.config", "mthlib.git", "urllib.request"):
            self.assertNotIn(heavy, loaded)

    def test_the_guard_still_confirms_exactly_the_autonomy_levels_the_configuration_defines(self):
        # unit: guard.CONFIRM
        self.assertEqual(set(guard.CONFIRM), set(config.AUTONOMY_LEVELS))


if __name__ == "__main__":
    unittest.main()
