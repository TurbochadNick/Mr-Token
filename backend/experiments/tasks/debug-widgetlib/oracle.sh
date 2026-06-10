#!/usr/bin/env bash
# Oracle for debug-widgetlib. Exit 0 iff test file unchanged AND the suite passes.
# Usage: oracle.sh <working-dir> <seed-dir>
set -euo pipefail
WORK="${1:?working dir}"; SEED="${2:?seed dir}"
if ! diff -q "$SEED/test_widgetlib.py" "$WORK/test_widgetlib.py" >/dev/null 2>&1; then
  echo "FAIL: test_widgetlib.py was modified (immutable)"; exit 1
fi
cd "$WORK"
if python3 -m pytest -q >/dev/null 2>&1; then echo "PASS"; exit 0; else echo "FAIL: tests not passing"; exit 1; fi
