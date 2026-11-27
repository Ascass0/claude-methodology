#!/bin/sh
# Runs the test suite with the first Python >= 3.11 available (same search as scripts/mth).
# Without arguments every test module runs in its own process, MTH_TEST_JOBS at a time (default: one per core).
# With arguments (a module, -v, -k ...) they go straight to unittest, serially.
for py in ${MTH_PYTHON:-} python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    here=$(dirname -- "$0")
    if [ "$#" -eq 0 ]; then
      exec "$py" "$here/run_parallel.py"
    fi
    # -b: the output of a passing test is discarded; a failing test still shows it.
    exec "$py" -m unittest discover -b -s "$here" "$@"
  fi
done
echo "✗ tests need Python >= 3.11 (set MTH_PYTHON)." >&2
exit 1
