"""Authorized scans for the execution auditor (SPEC-0028, ADR-0025)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import agent_guard, audit, config, scan  # noqa: E402
from mthlib.errors import MthError  # noqa: E402
from test_audit import PLUGIN, run  # noqa: E402

NOW = datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc)


class Runner:
    """Fake process runner: records the argv and returns canned output."""

    def __init__(self, stdout: bytes = b"ok", code: int = 0, error: Exception | None = None):
        self.calls: list[list[str]] = []
        self.stdout, self.code, self.error = stdout, code, error

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.code, self.stdout, b"")


def do_scan(root: Path, tool="testssl", target="Example.org:443", targets=("example.org:443",), runner=None, which=None):
    runner = runner or Runner()
    return scan.scan(tool, target, list(targets), root, which=which or (lambda name: f"/usr/bin/{name}"), runner=runner, now=lambda: NOW), runner


class ConfigTests(unittest.TestCase):
    def test_audit_targets_default_to_empty_and_invalid_entries_fail_the_load(self):
        # verifies: SPEC-0028/AC-01
        # verifies: SPEC-0028/FM-06
        self.assertEqual(config.DEFAULTS["audit"]["targets"], [])
        scan.validate(["example.org", "10.0.0.5:8443"])
        for bad in (["-oProxyCommand=x"], ["https://example.org"], ["example.org:99999"], "example.org", [1], ["a b"], ["*.example.org"]):
            with self.subTest(bad=bad), self.assertRaises(MthError) as ctx:
                scan.validate(bad)
            self.assertIn("audit.targets", ctx.exception.message)


class AuthorizationTests(unittest.TestCase):
    def test_a_target_outside_the_list_never_runs_the_tool(self):
        # verifies: SPEC-0028/AC-02
        # verifies: SPEC-0028/FM-01
        with tempfile.TemporaryDirectory() as tmp:
            for targets in ([], ["other.org:443"]):
                runner = Runner()
                with self.subTest(targets=targets), self.assertRaises(MthError) as ctx:
                    do_scan(Path(tmp), targets=targets, runner=runner)
                self.assertIn("audit.targets", ctx.exception.hint)
                self.assertEqual(runner.calls, [])

    def test_suspicious_targets_are_rejected_before_anything_runs(self):
        # verifies: SPEC-0028/AC-03
        # verifies: SPEC-0028/FM-02
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("-oProxyCommand=x", "https://example.org", "example.org/path", "example.org 443", "*.example.org", "[::1]:22"):
                runner = Runner()
                with self.subTest(bad=bad), self.assertRaises(MthError):
                    do_scan(Path(tmp), target=bad, targets=[bad], runner=runner)
                self.assertEqual(runner.calls, [])

    def test_host_case_is_ignored_and_an_entry_without_port_does_not_cover_a_port(self):
        # verifies: SPEC-0028/AC-04
        with tempfile.TemporaryDirectory() as tmp:
            _, runner = do_scan(Path(tmp), target="EXAMPLE.org:443", targets=["example.ORG:443"])
            self.assertEqual(len(runner.calls), 1)
            with self.assertRaises(MthError):
                do_scan(Path(tmp), target="example.org:8443", targets=["example.org"])
            _, runner = do_scan(Path(tmp), tool="ssh-audit", target="example.org", targets=["example.org"])
            self.assertEqual(runner.calls[0][-3:], ["--port", "22", "example.org"])


class ExecutionTests(unittest.TestCase):
    def test_an_authorized_scan_runs_without_a_shell_and_stores_the_output(self):
        # verifies: SPEC-0028/AC-05
        with tempfile.TemporaryDirectory() as tmp:
            (path, code), runner = do_scan(Path(tmp), runner=Runner(b"result", 3))
            self.assertEqual((code, path.read_bytes()), (3, b"result"))
            self.assertEqual(path, Path(tmp) / ".work/security-report/scan-testssl-example.org-443-20261127T100000Z.txt")
            self.assertEqual(runner.calls[0][0], "/usr/bin/testssl.sh")
            self.assertEqual(runner.calls[0][-1], "example.org:443")
            self.assertEqual(runner.kwargs["timeout"], scan.TIMEOUT_S)
            self.assertNotIn("shell", runner.kwargs)

    def test_a_missing_tool_fails_and_nothing_is_installed(self):
        # verifies: SPEC-0028/AC-06
        # verifies: SPEC-0028/FM-03
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(MthError) as ctx:
            do_scan(Path(tmp), which=lambda name: None)
        self.assertIn("no evaluable", ctx.exception.hint)

    def test_a_timeout_or_oversized_output_fails_and_keeps_nothing(self):
        # verifies: SPEC-0028/AC-07
        # verifies: SPEC-0028/FM-04
        # verifies: SPEC-0028/FM-05
        with tempfile.TemporaryDirectory() as tmp:
            for runner in (Runner(error=subprocess.TimeoutExpired("x", 1)), Runner(b"x" * (scan.MAX_OUTPUT + 1))):
                with self.subTest(), self.assertRaises(MthError):
                    do_scan(Path(tmp), runner=runner)
            self.assertFalse((Path(tmp) / ".work").exists())

    def test_an_unknown_tool_is_rejected(self):
        # verifies: SPEC-0028/AC-08
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(MthError):
            do_scan(Path(tmp), tool="nmap")

    def test_the_command_refuses_an_unauthorized_target_with_a_failing_code(self):
        # verifies: SPEC-0028/AC-02
        self.assertEqual(run("audit", "scan", "testssl", "unlisted.example.org")[0], 1)
        self.assertEqual(run("audit", "scan")[0], 1)


class PacksAndAgentTests(unittest.TestCase):
    def test_tls_and_ssh_packs_cite_their_sources_and_use_known_scan_tools(self):
        # verifies: SPEC-0028/AC-09
        packs = audit.load_packs()
        for name, source in (("tls", "rfc-editor.org/rfc/rfc9325"), ("ssh", "jtesta/ssh-audit")):
            with self.subTest(pack=name):
                self.assertIn(source, packs[name].source_url)
                self.assertTrue(all(c.tool in scan.TOOLS for c in packs[name].controls))

    def test_the_guard_allows_only_the_audit_commands_and_no_direct_network_tools(self):
        # verifies: SPEC-0028/AC-10
        rules = tomllib.loads((PLUGIN / "catalog/auditor-ejecucion/guard.toml").read_text(encoding="utf-8"))
        agent_guard.check_bash(rules, "mth audit scan testssl example.org:443")
        for command in ("testssl.sh example.org", "ssh-audit example.org", "nmap example.org", "curl https://example.org",
                        "mth tools install gitleaks", "mth audit scan testssl example.org > x"):
            with self.subTest(command=command), self.assertRaises(agent_guard.Denied):
                agent_guard.check_bash(rules, command)
        self.assertEqual(rules["write"]["allow"], [".work/security-report/**"])

    def test_the_agent_text_stops_without_targets_and_distrusts_tool_output(self):
        # verifies: SPEC-0028/AC-11
        text = (PLUGIN / "catalog/auditor-ejecucion/agent.md.tmpl").read_text(encoding="utf-8")
        self.assertIn("Sin destinos autorizados no haces nada", text)
        self.assertIn("dato no confiable", text)

    def test_skill_readme_and_template_document_the_targets(self):
        # verifies: SPEC-0028/AC-12
        for rel in ("skills/mth-audit/SKILL.md", "templates/methodology.toml"):
            self.assertIn("audit.targets" if rel.endswith("md") else "[audit]", (PLUGIN / rel).read_text(encoding="utf-8"), rel)
        self.assertIn("audit.targets", (HERE.parent / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
