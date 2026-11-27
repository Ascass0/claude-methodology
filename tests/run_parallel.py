"""Run every test module in its own process, several at a time, and report like ``unittest`` would.

``sh tests/run.sh`` uses it when it gets no arguments. The slowest modules start first so that the last
ones do not hold the whole run back. A module that fails shows its output; the exit code is 0 only if
every module passed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
_RAN = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)


def modules(directory: Path) -> list[str]:
    """Test modules of ``directory``, the biggest files first (they are the slowest)."""
    files = sorted(directory.glob("test_*.py"), key=lambda p: (-p.stat().st_size, p.name))
    return [p.stem for p in files]


def run_module(directory: Path, name: str) -> tuple[str, int, str]:
    """(module, exit code, output) of one module run on its own with its output buffered."""
    done = subprocess.run([sys.executable, "-m", "unittest", "-b", name], cwd=directory, capture_output=True, text=True)
    return name, done.returncode, done.stdout + done.stderr


def jobs() -> int:
    """Processes at a time: ``MTH_TEST_JOBS``, else one per core."""
    raw = os.environ.get("MTH_TEST_JOBS", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else (os.cpu_count() or 2)


def main(directory: Path = HERE) -> int:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=jobs()) as pool:
        results = list(pool.map(lambda name: run_module(directory, name), modules(directory)))
    failed = [(name, output) for name, code, output in results if code != 0]
    for name, output in failed:
        print(f"{'=' * 70}\n{name}\n{'=' * 70}\n{output}")
    total = sum(int(m.group(1)) for _, _, output in results if (m := _RAN.search(output)))
    print(f"Ran {total} tests in {time.perf_counter() - started:.1f}s ({len(results)} modules, {jobs()} at a time)")
    if failed:
        print(f"FAILED modules: {', '.join(name for name, _ in failed)}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
