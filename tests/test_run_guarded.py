"""The error boundary shared by the CLI and the hook shortcuts."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "methodology" / "scripts"))

from mthlib.errors import EXIT_BUG, EXIT_ERROR, MthError, run_guarded  # noqa: E402


def run(action):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = run_guarded(action)
    return code, err.getvalue()


class RunGuardedTests(unittest.TestCase):
    def test_a_controlled_failure_prints_its_message_and_hint_and_exits_with_the_error_code(self):
        # unit: errors.run_guarded
        def fail():
            raise MthError("Falla.", hint="Arréglalo.")
        code, err = run(fail)
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(err, "✗ Falla.\n  → Arréglalo.\n")

    def test_an_unexpected_exception_is_reported_as_a_bug_with_its_own_code(self):
        # unit: errors.run_guarded
        def bug():
            raise ValueError("boom")
        code, err = run(bug)
        self.assertEqual(code, EXIT_BUG)
        self.assertIn("(bug)", err)
        self.assertIn("ValueError: boom", err)

    def test_the_exit_code_of_the_action_passes_through(self):
        # unit: errors.run_guarded
        self.assertEqual(run(lambda: 0), (0, ""))
        self.assertEqual(run(lambda: 3)[0], 3)


if __name__ == "__main__":
    unittest.main()
