#!/bin/sh
# Runs the test suite with the first Python >= 3.11 available (same search as scripts/mth).
for py in ${MTH_PYTHON:-} python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    exec "$py" -m unittest discover -s "$(dirname -- "$0")" "$@"
  fi
done
echo "✗ tests need Python >= 3.11 (set MTH_PYTHON)." >&2
exit 1
