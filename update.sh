#!/usr/bin/env bash
# MR Token updater (pilot pipeline). Pulls the latest code and re-syncs the
# Claude Code skills/hooks. The Python backend is an editable install, so a pull
# makes code live immediately; `init` re-copies the /mr-* skills and confirms the
# hooks/statusLine. See docs/UPDATING.md.
set -euo pipefail
cd "$(dirname "$0")"

echo "▸ updating MR Token…"
git pull --ff-only

# only needed if dependencies or entry points changed (rare; deps are currently
# none). Harmless to run; keeps `--version` accurate after a version bump.
pip install -e backend/ -q

echo "▸ re-syncing skills + hooks…"
mrtoken-transcript init

echo "▸ now on: $(mrtoken-transcript --version)"
