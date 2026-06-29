#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
else
  PY=""
  for c in python3.13 python3.12 python3.11 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PY="$c"
      break
    fi
  done
fi

if [[ -z "$PY" ]]; then
  echo "need Python 3.11+ (set PYTHON=/path/to/python if needed)" >&2
  exit 1
fi

if [[ -n "${MRTOKEN_TEST_HOME:-}" ]]; then
  TEST_HOME="$MRTOKEN_TEST_HOME"
  CLEANUP_HOME=0
  mkdir -p "$TEST_HOME"
else
  TEST_HOME="$(mktemp -d "${TMPDIR:-/tmp}/mrtoken-test-home.XXXXXX")"
  CLEANUP_HOME=1
fi

cleanup() {
  if [[ "$CLEANUP_HOME" == "1" ]]; then
    rm -rf "$TEST_HOME"
  fi
}
trap cleanup EXIT

if [[ "$#" -gt 0 ]]; then
  TARGETS=("$@")
else
  TARGETS=(tests.test_backend)
fi

cd "$ROOT/backend"
HOME="$TEST_HOME" "$PY" -m unittest "${TARGETS[@]}"
