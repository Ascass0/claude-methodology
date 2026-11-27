"""Expected failures. Anything else is a bug and is handled at the CLI boundary."""
import sys
import traceback
from collections.abc import Callable

EXIT_ERROR = 1
EXIT_BUG = 70


class MthError(Exception):
    """A controlled failure with an actionable hint for the operator.

    Args:
        message: What failed, in Spanish (user-facing).
        hint: How to fix it. Optional.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def report(self) -> None:
        """Print the failure and its hint on stderr, the way every command does."""
        print(f"✗ {self.message}", file=sys.stderr)
        if self.hint:
            print(f"  → {self.hint}", file=sys.stderr)


def run_guarded(action: Callable[[], int]) -> int:
    """Run ``action`` and turn its failures into an exit code: the boundary of ``mth`` and of its hook shortcuts."""
    try:
        return action()
    except MthError as exc:
        exc.report()
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130
    except Exception:  # noqa: BLE001 — boundary: unexpected errors are bugs, not user errors.
        print("✗ Error interno de claude-methodology (bug):", file=sys.stderr)
        traceback.print_exc()
        return EXIT_BUG
