#!/usr/bin/env bash
# Oracle for codex-offload-noisy-log. Exit 0 iff:
#   (1) immutable diagnostic/test files are unchanged from seed
#   (2) the unittest suite passes.
# Usage: oracle.sh <working-dir> <seed-dir>
set -euo pipefail
WORK="${1:?working dir}"
SEED="${2:?seed dir}"

for f in test_processor.py build_check.py; do
  if ! diff -q "$SEED/$f" "$WORK/$f" >/dev/null 2>&1; then
    echo "FAIL: $f was modified (immutable)"
    exit 1
  fi
done

cd "$WORK"
if python3 -m unittest -q >/dev/null 2>&1; then
  echo "PASS"
  exit 0
else
  echo "FAIL: tests not passing"
  exit 1
fi
