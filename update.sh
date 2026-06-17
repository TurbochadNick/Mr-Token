#!/usr/bin/env bash
# MR Token updater (pilot pipeline). Pulls the latest code and re-syncs the
# Claude Code skills/hooks. The Python backend is zero-dep; a pull makes code
# live immediately (editable install or from source), and `init` re-copies the
# /mr-* skills and confirms the hooks/statusLine. See docs/UPDATING.md.
set -euo pipefail
cd "$(dirname "$0")"

echo "▸ updating MR Token…"
git pull --ff-only

# Match install.sh: find a 3.11+ interpreter; prefer editable pip, fall back to
# running from source if pip is broken (e.g. a busted Homebrew Python).
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "✗ need Python 3.11+ (none found)"; exit 1; }

if "$PY" -m pip install -e backend/ -q 2>/dev/null; then
  RUN=("$PY" -m mrtoken.cli)
else
  export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
  RUN=("$PY" -m mrtoken.cli)
fi

echo "▸ re-syncing skills + hooks…"
"${RUN[@]}" init

echo "▸ now on: $("${RUN[@]}" --version)"
