"""The parallel test runner: it must fail when any module fails, and show the output of the one that failed."""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_parallel  # noqa: E402

PASSING = "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        print('RUIDO-QUE-PASA')\n"
FAILING = "import unittest\nclass T(unittest.TestCase):\n    def test_bad(self):\n        print('SALIDA-DEL-FALLO')\n        self.fail('boom')\n"


class RunParallelTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text, encoding="utf-8")

    def run_all(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_parallel.main(self.dir)
        return code, out.getvalue()

    def test_all_modules_passing_exit_zero_and_hide_their_output(self):
        # unit: run_parallel.main
        self.write("test_a.py", PASSING)
        self.write("test_b.py", PASSING)
        code, out = self.run_all()
        self.assertEqual(code, 0)
        self.assertIn("Ran 2 tests", out)
        self.assertNotIn("RUIDO-QUE-PASA", out)

    def test_a_failing_module_exits_non_zero_names_itself_and_shows_its_output(self):
        # unit: run_parallel.main
        self.write("test_a.py", PASSING)
        self.write("test_b.py", FAILING)
        code, out = self.run_all()
        self.assertEqual(code, 1)
        self.assertIn("SALIDA-DEL-FALLO", out)
        self.assertIn("FAILED modules: test_b", out)
        self.assertNotIn("RUIDO-QUE-PASA", out)

    def test_the_biggest_files_run_first_and_the_job_count_is_configurable(self):
        # unit: run_parallel.modules
        self.write("test_small.py", "x = 1\n")
        self.write("test_big.py", "x = 1\n" * 100)
        self.assertEqual(run_parallel.modules(self.dir), ["test_big", "test_small"])
        with mock.patch.dict(os.environ, {"MTH_TEST_JOBS": "3"}):
            self.assertEqual(run_parallel.jobs(), 3)
        with mock.patch.dict(os.environ, {"MTH_TEST_JOBS": "abc"}):
            self.assertGreaterEqual(run_parallel.jobs(), 1)


if __name__ == "__main__":
    unittest.main()
