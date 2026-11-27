"""Expected failures. Anything else is a bug and is handled at the CLI boundary."""
import sys


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
