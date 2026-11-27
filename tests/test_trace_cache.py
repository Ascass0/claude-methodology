"""mth trace reads each file once per run, however many checks go through the checker."""
from __future__ import annotations

import collections
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "plugins" / "methodology" / "scripts"))

import test_mth  # noqa: E402
from mthlib import ids, trace  # noqa: E402
from mthlib.config import parse  # noqa: E402

CONFIG = 'version = 1\n[commands]\ntest = ""\n'
# Fixture IDs are built here so that this file holds no ID of its own to trace.
SPEC_ID = "SPEC-" + "9001"
SPEC = f"# {SPEC_ID} · A\n\n- Estado: aprobada\n- **AC-01**: uno\n- **AC-02**: dos\n"
TEST = f"def test_a():\n    # verifies: {SPEC_ID}/AC-01\n    pass\n"


class ReadOnceTests(unittest.TestCase):
    def test_every_file_is_read_once_by_the_checks_the_registry_and_the_single_test_warning(self):
        # regression: trace read each spec four times (two checkers, each with its own registry)
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for rel, text in {"specs/features/SPEC-9001-a.md": SPEC, "tests/test_a.py": TEST}.items():
            test_mth._write(root / rel, text)
        names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
        reads: collections.Counter[Path] = collections.Counter()

        def counting(path: Path):
            reads[path] += 1
            return ids.read_text(path)

        with mock.patch.object(trace, "read_text", counting):
            checker = trace.Tracer(parse(root, CONFIG), names)
            self.assertEqual(checker.run(), [])
            self.assertEqual(len(checker.single_test()), 1)  # AC-01 has one test; AC-02 none: the warning still works
        self.assertEqual(set(reads.values()), {1}, dict(reads))
        self.assertEqual(len(reads), len(names))


if __name__ == "__main__":
    unittest.main()
