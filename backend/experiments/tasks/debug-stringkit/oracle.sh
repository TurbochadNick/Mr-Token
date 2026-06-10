#!/usr/bin/env bash
# Oracle for debug-stringkit. Exit 0 iff the task is correctly complete:
#   (1) the test file is unchanged from the seed (no cheating by editing tests)
#   (2) the full suite passes.
# Usage: oracle.sh <working-dir> <seed-dir>
set -euo pipefail
WORK="${1:?working dir}"
SEED="${2:?seed dir}"

# (1) immutability: test file must match the seed exactly
if ! diff -q "$SEED/test_stringkit.py" "$WORK/test_stringkit.py" >/dev/null 2>&1; then
  echo "FAIL: test_stringkit.py was modified (immutable)"
  exit 1
fi

# (2) tests pass
cd "$WORK"
if python3 -m pytest -q >/dev/null 2>&1; then
  echo "PASS"
  exit 0
else
  echo "FAIL: tests not passing"
  exit 1
fi
