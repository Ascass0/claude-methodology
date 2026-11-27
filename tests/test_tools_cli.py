"""Tests of `mth tools` (SPEC-0025): list, install and prune through the CLI with a fake downloader."""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import cli, tools  # noqa: E402
from test_tools import GOOD, SCRIPT, make_tool, serving  # noqa: E402


class ToolsCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.empty = self.tmp / "bin"
        self.empty.mkdir()
        self.tool = make_tool(GOOD)
        self.fetch = serving(GOOD)
        for patcher in (mock.patch.dict(os.environ, {"PATH": str(self.empty), "MTH_TOOLS_DIR": str(self.tmp / "cache")}),
                        mock.patch.object(tools, "load_manifest", return_value={"faketool": self.tool}),
                        mock.patch.object(tools, "platform_key", return_value="linux_x64"),
                        mock.patch.object(tools, "download", self.fetch)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def mth(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["tools", *args])
        return code, out.getvalue(), err.getvalue()

    def test_listing_shows_version_origin_and_found_version_and_never_downloads(self):
        # verifies: SPEC-0025/AC-11
        code, out, _ = self.mth()
        self.assertEqual((code, out.strip()), (0, "faketool 1.2.3 · ausente · -"))
        self.assertEqual(self.fetch.calls, [])
        self.mth("install", "faketool")
        self.assertIn("faketool 1.2.3 · gestionada · 1.2.3", self.mth("list")[1])
        exe = self.empty / "faketool"
        exe.write_bytes(SCRIPT)
        exe.chmod(0o755)
        self.assertIn("faketool 1.2.3 · PATH · 1.2.3", self.mth()[1])

    def test_install_downloads_only_on_the_explicit_command_and_force_reinstalls(self):
        # verifies: SPEC-0025/AC-06
        # verifies: SPEC-0025/AC-08
        self.assertEqual(self.fetch.calls, [])
        code, out, _ = self.mth("install", "faketool")
        self.assertEqual(code, 0)
        self.assertIn("instalada", out)
        self.assertEqual(len(self.fetch.calls), 1)
        self.assertIn("ya instalada", self.mth("install", "faketool")[1])
        self.assertEqual(len(self.fetch.calls), 1)
        self.assertIn("instalada", self.mth("install", "faketool", "--force")[1])
        self.assertEqual(len(self.fetch.calls), 2)

    def test_install_needs_a_known_tool_and_other_actions_refuse_extra_arguments(self):
        # verifies: SPEC-0025/AC-06
        for args in (("install",), ("install", "nothing"), ("prune", "faketool"), ("list", "--force")):
            code, _, err = self.mth(*args)
            self.assertEqual(code, 1, args)
            self.assertIn("✗", err)
        self.assertEqual(self.fetch.calls, [])

    def test_prune_needs_the_command_and_reports_what_it_removed(self):
        # verifies: SPEC-0025/AC-12
        self.mth("install", "faketool")
        stale = self.tmp / "cache" / "faketool" / "0.0.1"
        stale.mkdir()
        self.assertTrue(stale.exists())
        code, out, _ = self.mth("prune")
        self.assertEqual(code, 0)
        self.assertIn("0.0.1", out)
        self.assertFalse(stale.exists())
        self.assertIn("nada que borrar", self.mth("prune")[1])


if __name__ == "__main__":
    unittest.main()
