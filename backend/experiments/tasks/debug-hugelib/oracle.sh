#!/usr/bin/env bash
# Oracle for debug-hugelib. Exit 0 iff the test file is unchanged AND the suite passes.
set -euo pipefail
WORK="${1:?working dir}"; SEED="${2:?seed dir}"
if ! diff -q "$SEED/test_hugelib.py" "$WORK/test_hugelib.py" >/dev/null 2>&1; then
  echo "FAIL: test_hugelib.py was modified (immutable)"; exit 1
fi
cd "$WORK"
if python3 -m pytest -q >/dev/null 2>&1; then echo "PASS"; exit 0; else echo "FAIL: tests not passing"; exit 1; fi
