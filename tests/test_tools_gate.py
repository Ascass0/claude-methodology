"""The secrets gate and `mth doctor` use the tools resolver (SPEC-0025/AC-13, AC-14) with a fake managed gitleaks."""
from __future__ import annotations

import json
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

from mthlib import secretgate, setup, tools  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_secrets import SECTION  # noqa: E402
from test_tools import make_tool, serving, tar_bytes  # noqa: E402

FAKE = f"#!/bin/sh\nexec {sys.executable} {HERE / 'fake_gitleaks.py'} \"$@\"\n".encode()


class ResolverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.log = self.tmp / "calls.log"
        archive = tar_bytes([("gitleaks", FAKE, {})])
        manifest_tool = make_tool(archive, entry="gitleaks", version="8.30.1")
        self.tool = tools.Tool("gitleaks", "8.30.1", ("version",), manifest_tool.platforms)
        for patcher in (mock.patch.dict(os.environ, {"PATH": str(self.tmp / "nobin"), "MTH_TOOLS_DIR": str(self.tmp / "cache"),
                                                      "FAKE_GITLEAKS_LOG": str(self.log), "FAKE_GITLEAKS_MODE": "clean"}),
                        mock.patch.object(tools, "load_manifest", return_value={"gitleaks": self.tool}),
                        mock.patch.object(tools, "platform_key", return_value="linux_x64")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.archive = archive

    def install(self) -> None:
        tools.install(self.tool, fetch=serving(self.archive))


class GateWithResolverTests(ResolverCase):
    def test_the_gate_runs_the_managed_copy_when_there_is_none_on_the_path(self):
        # verifies: SPEC-0025/AC-13
        self.install()
        secretgate.enforce(self.root, SECTION, "a..b")
        secretgate.enforce_staged(self.root, SECTION)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([c[0] for c in calls], ["git", "git"])
        self.assertTrue(secretgate.is_installed())

    def test_without_any_gitleaks_it_fails_closed_naming_the_install_command(self):
        # verifies: SPEC-0025/AC-13
        for call in (lambda: secretgate.enforce(self.root, SECTION, "a..b"), lambda: secretgate.enforce_staged(self.root, SECTION)):
            with self.assertRaises(MthError) as ctx:
                call()
            self.assertIn("mth tools install gitleaks", ctx.exception.hint)
        self.assertFalse(secretgate.is_installed())
        self.assertFalse(self.log.exists())

    def test_an_altered_managed_copy_stops_the_gate_instead_of_running_it(self):
        # verifies: SPEC-0025/AC-10
        # verifies: SPEC-0025/AC-13
        self.install()
        tools.managed_path(self.tool, tools.cache_root()).write_bytes(b"#!/bin/sh\necho evil\n")
        with self.assertRaises(MthError) as ctx:
            secretgate.enforce(self.root, SECTION, "a..b")
        self.assertIn("--force", ctx.exception.hint)
        self.assertFalse(self.log.exists())


class DoctorLinesTests(ResolverCase):
    def lines(self) -> list[tuple[bool, str, bool]]:
        out: list[tuple[bool, str, bool]] = []
        setup._doctor_gitleaks(lambda ok, msg, blocking=True: out.append((ok, msg, blocking)))
        return out

    def test_doctor_blocks_without_the_tool_and_shows_origin_and_version_with_the_managed_copy(self):
        # verifies: SPEC-0025/AC-14
        missing = self.lines()
        self.assertFalse(missing[0][0])
        self.assertTrue(missing[0][2])
        self.assertIn("gitleaks instalado", missing[0][1])
        self.install()
        found = self.lines()
        self.assertEqual([ok for ok, _, _ in found], [True, True])
        self.assertIn("gitleaks 8.30.1 · gestionada (mínima 8.19.0)", found[1][1])
        self.assertFalse(found[1][2])

    def test_doctor_warns_about_another_managed_version_and_an_old_path_tool(self):
        # verifies: SPEC-0025/AC-14
        self.install()
        (Path(os.environ["MTH_TOOLS_DIR"]) / "gitleaks" / "8.0.0").mkdir()
        (Path(os.environ["MTH_TOOLS_DIR"]) / "gitleaks" / "8.0.0" / tools.META).write_text("{}")
        warnings = [msg for ok, msg, blocking in self.lines() if not ok and not blocking]
        self.assertTrue(any("otra versión (8.0.0)" in w and "mth tools prune" in w for w in warnings))
        old = self.tmp / "nobin"
        old.mkdir()
        (old / "gitleaks").write_bytes(b"#!/bin/sh\necho 8.18.4\n")
        (old / "gitleaks").chmod(0o755)
        # an old PATH tool yields to the valid managed copy, so no old-version warning remains
        self.assertIn("gestionada", [msg for _, msg, _ in self.lines()][1])


if __name__ == "__main__":
    unittest.main()
