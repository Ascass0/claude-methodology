"""Tests of the external tools manager (SPEC-0025, ADR-0023): manifest, resolver, install and prune. No network."""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

from mthlib import tools  # noqa: E402
from mthlib.errors import MthError  # noqa: E402

SCRIPT = b"#!/bin/sh\necho 'faketool 1.2.3'\n"
OLD_SCRIPT = b"#!/bin/sh\necho 'faketool 0.9.0'\n"


def tar_bytes(members: list[tuple[str, bytes | None, dict]]) -> bytes:
    """A tar.gz with (name, data, extra) members; ``data`` None means a directory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data, extra in members:
            info = tarfile.TarInfo(name)
            info.mode = 0o755
            for key, value in extra.items():
                setattr(info, key, value)
            if data is None and "type" not in extra:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif "type" in extra:
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zip_bytes(members: list[tuple[str, bytes, int]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for name, data, mode in members:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            bundle.writestr(info, data)
    return buf.getvalue()


def make_tool(data: bytes, fmt: str = "tar.gz", entry: str = "faketool", key: str = "linux_x64", version: str = "1.2.3") -> tools.Tool:
    digest = hashlib.sha256(data).hexdigest()
    text = (f'[faketool]\nversion = "{version}"\nversion_args = ["--version"]\n[faketool.platforms.{key}]\n'
            f'url = "https://example.test/faketool.{fmt}"\nsha256 = "{digest}"\nformat = "{fmt}"\nentry = "{entry}"\n')
    return tools.parse_manifest(text)["faketool"]


def serving(data: bytes):
    calls = []

    def fetch(url, dest, limit, timeout):
        calls.append(url)
        dest.write_bytes(data)
    fetch.calls = calls
    return fetch


GOOD = tar_bytes([("faketool", SCRIPT, {})])


class ToolsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "cache"
        self.empty_path = self.tmp / "emptybin"
        self.empty_path.mkdir()
        patcher = mock.patch.dict(os.environ, {"PATH": str(self.empty_path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def leftovers(self) -> list[str]:
        return sorted(p.name for p in (self.root / "faketool").glob("*")) if (self.root / "faketool").exists() else []

    def install_good(self, **kwargs) -> tools.Tool:
        tool = make_tool(GOOD)
        tools.install(tool, root=self.root, system="linux_x64", fetch=serving(GOOD), **kwargs)
        return tool

    def on_path(self, script: bytes) -> None:
        exe = self.empty_path / "faketool"
        exe.write_bytes(script)
        exe.chmod(0o755)


class ManifestTests(ToolsCase):
    def test_the_plugin_manifest_is_valid_and_has_gitleaks_for_five_platforms(self):
        # verifies: SPEC-0025/AC-01
        gitleaks = tools.load_manifest()["gitleaks"]
        self.assertEqual(set(gitleaks.platforms), {"linux_x64", "linux_arm64", "darwin_x64", "darwin_arm64", "windows_x64"})
        self.assertEqual(gitleaks.platforms["windows_x64"].format, "zip")
        self.assertEqual(gitleaks.platforms["windows_x64"].entry, "gitleaks.exe")

    def test_an_invalid_manifest_names_tool_platform_and_field(self):
        # verifies: SPEC-0025/AC-01
        # verifies: SPEC-0025/FM-01
        good = ('[t]\nversion = "1.0.0"\nversion_args = ["v"]\n[t.platforms.linux_x64]\nurl = "https://x.test/a.tar.gz"\n'
                f'sha256 = "{"a" * 64}"\nformat = "tar.gz"\nentry = "t"\n')
        tools.parse_manifest(good)
        cases = {
            "url": good.replace("https://", "http://"), "sha256": good.replace("a" * 64, "A" * 64),
            "format": good.replace('"tar.gz"\nentry', '"rar"\nentry'), "entry": good.replace('entry = "t"', 'entry = "../t"'),
            "version": good.replace('version = "1.0.0"', 'version = "1"'),
            "plataforma": good.replace("linux_x64", "plan9_x64"),
        }
        for field, text in cases.items():
            with self.subTest(field=field), self.assertRaises(MthError) as ctx:
                tools.parse_manifest(text)
            self.assertIn("'t'", ctx.exception.message)
            self.assertIn(field if field != "plataforma" else "plan9_x64", ctx.exception.message)
        with self.assertRaises(MthError):
            tools.parse_manifest(good.replace('entry = "t"\n', ""))

    def test_a_platform_without_an_entry_is_refused(self):
        # verifies: SPEC-0025/AC-02
        # verifies: SPEC-0025/FM-02
        tool = make_tool(GOOD)
        with self.assertRaises(MthError) as ctx:
            tools.install(tool, root=self.root, system="darwin_arm64", fetch=serving(GOOD))
        self.assertIn("darwin_arm64", ctx.exception.message)
        self.assertIn("linux_x64", ctx.exception.hint)
        self.assertRegex(tools.platform_key(), r"^(linux|darwin|windows)_\w+$")

    def test_the_manifest_and_the_ci_template_pin_the_same_gitleaks(self):
        # verifies: SPEC-0025/AC-15
        template = (HERE.parent / "plugins/methodology/templates/workflows/secrets.yml").read_text(encoding="utf-8")
        entry = tools.load_manifest()["gitleaks"]
        self.assertIn(f'VERSION: "{entry.version}"', template)
        self.assertIn(f'SHA256: "{entry.platforms["linux_x64"].sha256}"', template)


class ResolveTests(ToolsCase):
    MINIMUM = (1, 0, 0)

    def test_a_recent_enough_tool_on_the_path_wins_and_nothing_is_downloaded(self):
        # verifies: SPEC-0025/AC-03
        tool = make_tool(GOOD)
        self.on_path(SCRIPT)
        fetch = serving(GOOD)
        resolved = tools.resolve(tool, self.MINIMUM, self.root)
        self.assertEqual((resolved.origin, resolved.version, resolved.warning), ("PATH", (1, 2, 3), ""))
        self.assertEqual(fetch.calls, [])
        self.assertEqual(tools.resolve(tool, None, self.root).origin, "PATH")

    def test_an_old_or_unrecognised_path_tool_yields_to_a_valid_managed_copy(self):
        # verifies: SPEC-0025/AC-04
        # verifies: SPEC-0025/FM-09
        # verifies: SPEC-0025/FM-10
        tool = self.install_good()
        for script in (OLD_SCRIPT, b"#!/bin/sh\necho nothing here\n", b"#!/bin/sh\nexit 3\n"):
            self.on_path(script)
            resolved = tools.resolve(tool, self.MINIMUM, self.root)
            self.assertEqual(resolved.origin, "gestionada", script)
        self.assertTrue(resolved.path.is_file())

    def test_without_a_managed_copy_an_old_path_tool_is_used_with_a_warning(self):
        # verifies: SPEC-0025/AC-04
        # verifies: SPEC-0025/FM-09
        tool = make_tool(GOOD)
        self.on_path(OLD_SCRIPT)
        resolved = tools.resolve(tool, self.MINIMUM, self.root)
        self.assertEqual(resolved.origin, "PATH")
        self.assertIn("anterior", resolved.warning)

    def test_a_version_command_that_hangs_counts_as_unrecognised(self):
        # verifies: SPEC-0025/AC-04
        # verifies: SPEC-0025/FM-10
        tool = make_tool(GOOD)
        self.on_path(b"#!/bin/sh\nwhile :; do :; done\n")
        with mock.patch.object(tools, "VERSION_TIMEOUT", 1):
            self.assertIsNone(tools.tool_version(self.empty_path / "faketool", tool))

    def test_nothing_anywhere_fails_with_the_install_command_and_never_downloads(self):
        # verifies: SPEC-0025/AC-05
        tool = make_tool(GOOD)
        with mock.patch.object(tools, "download") as fetch, self.assertRaises(tools.NotFound) as ctx:
            tools.resolve(tool, self.MINIMUM, self.root)
        self.assertIn("mth tools install faketool", ctx.exception.hint)
        fetch.assert_not_called()
        self.assertFalse(self.root.exists())


class InstallTests(ToolsCase):
    def test_installs_verifies_and_resolves_the_managed_copy(self):
        # verifies: SPEC-0025/AC-06
        tool = make_tool(GOOD)
        fetch = serving(GOOD)
        self.assertEqual(tools.install(tool, root=self.root, system="linux_x64", fetch=fetch), "instalada")
        self.assertEqual(fetch.calls, ["https://example.test/faketool.tar.gz"])
        resolved = tools.resolve(tool, (1, 0, 0), self.root)
        self.assertEqual((resolved.origin, resolved.version), ("gestionada", (1, 2, 3)))
        self.assertTrue(os.access(resolved.path, os.X_OK))
        self.assertEqual(self.leftovers(), ["1.2.3"])

    def test_a_wrong_sum_installs_nothing_and_leaves_no_leftovers(self):
        # verifies: SPEC-0025/AC-06
        # verifies: SPEC-0025/FM-03
        tool = make_tool(GOOD)
        with self.assertRaises(MthError) as ctx:
            tools.install(tool, root=self.root, system="linux_x64", fetch=serving(GOOD + b"tampered"))
        self.assertIn("SHA-256", ctx.exception.message)
        self.assertEqual(self.leftovers(), [])

    def test_a_failing_download_is_retried_a_bounded_number_of_times_with_growing_waits(self):
        # verifies: SPEC-0025/AC-06
        # verifies: SPEC-0025/FM-04
        tool = make_tool(GOOD)
        attempts, waits = [], []

        def broken(url, dest, limit, timeout):
            attempts.append(timeout)
            raise TimeoutError("timed out")
        with self.assertRaises(MthError) as ctx:
            tools.install(tool, root=self.root, system="linux_x64", fetch=broken, sleep=waits.append)
        self.assertEqual(len(attempts), tools.ATTEMPTS)
        self.assertEqual(waits, [1, 2])
        self.assertIn("https://example.test/faketool.tar.gz", ctx.exception.message)
        self.assertIn("PATH", ctx.exception.hint)
        self.assertEqual(self.leftovers(), [])

    def test_an_oversized_download_is_refused_without_retrying(self):
        # verifies: SPEC-0025/AC-06
        # verifies: SPEC-0025/FM-04
        tool = make_tool(GOOD)
        calls = []

        def huge(url, dest, limit, timeout):
            calls.append(limit)
            raise MthError("La descarga supera el tamaño máximo")
        with self.assertRaises(MthError):
            tools.install(tool, root=self.root, system="linux_x64", fetch=huge, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.leftovers(), [])

    def test_the_real_downloader_stops_at_the_size_limit_and_refuses_http_redirects(self):
        # verifies: SPEC-0025/AC-06
        # verifies: SPEC-0025/FM-04
        class Body:
            headers = {"Content-Length": "10"}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, size):
                return b"x" * 10 if not getattr(self, "done", False) and not setattr(self, "done", True) else b""
        opener = mock.Mock()
        opener.open.return_value = Body()
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(MthError):
                tools.download("https://example.test/a", self.tmp / "out", 5, 1)
        redirect = tools._HttpsOnly()
        with self.assertRaises(OSError):
            redirect.redirect_request(mock.Mock(), None, 302, "Found", {}, "http://evil.test/x")

    def test_unsafe_archives_install_nothing(self):
        # verifies: SPEC-0025/AC-07
        # verifies: SPEC-0025/FM-05
        bad = {
            "parent": tar_bytes([("faketool", SCRIPT, {}), ("../evil", b"x", {})]),
            "absolute": tar_bytes([("faketool", SCRIPT, {}), ("/etc/evil", b"x", {})]),
            "symlink": tar_bytes([("faketool", SCRIPT, {}), ("link", None, {"type": tarfile.SYMTYPE, "linkname": "/etc/passwd"})]),
            "hardlink": tar_bytes([("faketool", SCRIPT, {}), ("link", None, {"type": tarfile.LNKTYPE, "linkname": "faketool"})]),
            "device": tar_bytes([("faketool", SCRIPT, {}), ("dev", None, {"type": tarfile.CHRTYPE})]),
            "no entry": tar_bytes([("other", SCRIPT, {})]),
            "not a tar": b"this is not an archive",
        }
        for label, data in bad.items():
            with self.subTest(label=label), self.assertRaises(MthError):
                tools.install(make_tool(data), root=self.root, system="linux_x64", fetch=serving(data))
            self.assertEqual(self.leftovers(), [], label)
        for limit, value in (("MAX_MEMBERS", 1), ("MAX_EXTRACTED", 5)):
            with self.subTest(limit=limit), mock.patch.object(tools, limit, value), self.assertRaises(MthError):
                tools.install(make_tool(GOOD if limit == "MAX_EXTRACTED" else tar_bytes([("faketool", SCRIPT, {}), ("b", b"b", {})])),
                              root=self.root, system="linux_x64",
                              fetch=serving(GOOD if limit == "MAX_EXTRACTED" else tar_bytes([("faketool", SCRIPT, {}), ("b", b"b", {})])))
            self.assertEqual(self.leftovers(), [], limit)

    def test_zip_archives_install_on_windows_and_unsafe_zips_install_nothing(self):
        # verifies: SPEC-0025/AC-07
        data = zip_bytes([("faketool.exe", SCRIPT, 0o100755), ("README.md", b"hi", 0o100644)])
        tool = make_tool(data, fmt="zip", entry="faketool.exe", key="windows_x64")
        tools.install(tool, root=self.root, system="windows_x64", fetch=serving(data))
        self.assertTrue(tools.managed_path(tool, self.root).is_file())
        shutil.rmtree(self.root)
        bad = {
            "parent": zip_bytes([("faketool.exe", SCRIPT, 0o100755), ("../evil", b"x", 0o100644)]),
            "symlink": zip_bytes([("faketool.exe", SCRIPT, 0o100755), ("link", b"/etc/passwd", stat.S_IFLNK | 0o777)]),
            "no entry": zip_bytes([("other.exe", SCRIPT, 0o100755)]),
        }
        for label, blob in bad.items():
            with self.subTest(label=label), self.assertRaises(MthError):
                tools.install(make_tool(blob, "zip", "faketool.exe", "windows_x64"), root=self.root,
                              system="windows_x64", fetch=serving(blob))
            self.assertEqual(self.leftovers(), [], label)

    def test_a_tree_with_an_entry_point_keeps_its_files(self):
        # verifies: SPEC-0025/AC-07
        data = tar_bytes([("pkg/", None, {}), ("pkg/bin/faketool", SCRIPT, {}), ("pkg/cfg/rules.yaml", b"a: 1\n", {})])
        tool = make_tool(data, entry="pkg/bin/faketool")
        tools.install(tool, root=self.root, system="linux_x64", fetch=serving(data))
        self.assertTrue((tools.managed_path(tool, self.root).parent.parent / "cfg" / "rules.yaml").is_file())

    def test_installing_twice_does_not_download_again_and_concurrent_installs_leave_one_copy(self):
        # verifies: SPEC-0025/AC-08
        # verifies: SPEC-0025/FM-07
        tool = make_tool(GOOD)
        fetch = serving(GOOD)
        tools.install(tool, root=self.root, system="linux_x64", fetch=fetch)
        self.assertEqual(tools.install(tool, root=self.root, system="linux_x64", fetch=fetch), "ya instalada")
        self.assertEqual(len(fetch.calls), 1)
        shutil.rmtree(self.root)

        def racing(url, dest, limit, timeout):  # another mth publishes the same version while this one downloads
            tools.install(tool, root=self.root, system="linux_x64", fetch=serving(GOOD))
            dest.write_bytes(GOOD)
        self.assertEqual(tools.install(tool, root=self.root, system="linux_x64", fetch=racing), "instalada")
        self.assertEqual(self.leftovers(), ["1.2.3"])
        self.assertTrue(tools.managed_path(tool, self.root).is_file())

    def test_the_cache_follows_the_override_and_the_system_default_and_is_private(self):
        # verifies: SPEC-0025/AC-09
        self.assertEqual(tools.cache_root({"MTH_TOOLS_DIR": "/x/y"}), Path("/x/y"))
        self.assertEqual(tools.cache_root({"XDG_CACHE_HOME": "/c"}), Path("/c/claude-methodology/tools"))
        self.install_good()
        self.assertEqual(stat.S_IMODE((self.root / "faketool").stat().st_mode), 0o700)

    def test_an_unwritable_cache_names_the_path_and_the_override(self):
        # verifies: SPEC-0025/AC-09
        # verifies: SPEC-0025/FM-06
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with self.assertRaises(MthError) as ctx:
            tools.install(make_tool(GOOD), root=blocker / "sub", system="linux_x64", fetch=serving(GOOD))
        self.assertIn(str(blocker), ctx.exception.message)
        self.assertIn("MTH_TOOLS_DIR", ctx.exception.hint)


class IntegrityAndPruneTests(ToolsCase):
    def test_an_altered_managed_copy_is_never_used_and_force_reinstalls_it(self):
        # verifies: SPEC-0025/AC-10
        # verifies: SPEC-0025/FM-08
        tool = self.install_good()
        executable = tools.managed_path(tool, self.root)
        executable.write_bytes(b"#!/bin/sh\necho evil\n")
        for call in (lambda: tools.resolve(tool, (1, 0, 0), self.root),
                     lambda: tools.install(tool, root=self.root, system="linux_x64", fetch=serving(GOOD))):
            with self.assertRaises(MthError) as ctx:
                call()
            self.assertIn("--force", ctx.exception.hint)
        self.assertEqual(tools.install(tool, root=self.root, system="linux_x64", fetch=serving(GOOD), force=True), "instalada")
        self.assertEqual(tools.managed_path(tool, self.root).read_bytes(), SCRIPT)
        self.assertEqual(self.leftovers(), ["1.2.3"])

    def test_status_lists_origin_and_version_without_the_network(self):
        # verifies: SPEC-0025/AC-11
        tool = make_tool(GOOD)
        with mock.patch.object(tools, "download") as fetch:
            self.assertEqual(tools.status(tool, self.root), ("ausente", "-"))
            self.install_good()
            self.assertEqual(tools.status(tool, self.root), ("gestionada", "1.2.3"))
            self.on_path(SCRIPT)
            self.assertEqual(tools.status(tool, self.root), ("PATH", "1.2.3"))
        fetch.assert_not_called()

    def test_prune_removes_only_stale_versions_and_leftovers_and_only_when_called(self):
        # verifies: SPEC-0025/AC-12
        tool = self.install_good()
        folder = self.root / "faketool"
        (folder / "0.1.0").mkdir()
        (folder / "1.2.3.tmp-abc").mkdir()
        (self.root / "gone").mkdir()
        (self.root / "gone" / "1.0.0").mkdir()
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["0.1.0", "1.2.3", "1.2.3.tmp-abc"])  # nothing pruned yet
        removed = tools.prune({"faketool": tool}, self.root)
        self.assertEqual(sorted(p.name for p in removed), ["0.1.0", "1.0.0", "1.2.3.tmp-abc"])
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["1.2.3"])
        self.assertFalse((self.root / "gone").exists())
        self.assertTrue(tools.managed_path(tool, self.root).is_file())
        self.assertEqual(tools.prune({"faketool": tool}, self.tmp / "missing"), [])


if __name__ == "__main__":
    unittest.main()
