"""Structured trace of every mth operation (JSON Lines in .git/mth/trace.jsonl)."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Tracer:
    """Append-only event log correlated by ``run_id``.

    Tracing must never break the operation it observes: write errors are
    reported once on stderr and then ignored (deliberate fail-open).
    """

    def __init__(self, git_dir: Path | None, command: str, name: str = "trace.jsonl",
                 max_bytes: int | None = None) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self.command = command
        self.path = git_dir / "mth" / name if git_dir else None
        self.max_bytes = max_bytes  # rotate to <name>.1 beyond this size (None: never)
        self._warned = False

    def event(self, name: str, **data: object) -> None:
        """Record one event with arbitrary JSON-serialisable data."""
        if self.path is None:
            return
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "run": self.run_id, "cmd": self.command, "event": name, **data}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.max_bytes is not None and self.path.is_file() and self.path.stat().st_size > self.max_bytes:
                self.path.replace(self.path.with_name(self.path.name + ".1"))
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)  # local and private
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            if not self._warned:
                print(f"⚠ No se pudo escribir la traza: {exc}", file=sys.stderr)
                self._warned = True


def say(msg: str) -> None:
    """Progress line for the operator (stdout, read by Claude)."""
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"⚠ {msg}", flush=True)
