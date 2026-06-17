#!/usr/bin/env bash
# MR Token one-command install for testers. After cloning:
#   git clone <repo> && cd Mr-Token && ./install.sh
# Installs the Python backend, then sets up the Claude Code hooks + /mr-* skills.
# Update later with ./update.sh. See docs/QUICKSTART.md.
set -euo pipefail
cd "$(dirname "$0")"

echo "▸ MR Token install"

# 1. Python 3.11+
python3 - <<'PY' || { echo "✗ Python 3.11+ required (got $(python3 -V 2>&1))"; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY

# 2. backend (editable, so git pull / ./update.sh picks up changes with no reinstall)
echo "▸ installing backend…"
python3 -m pip install -e backend/ -q

# 3. Claude Code hooks + global /mr-* skills + statusLine HUD
echo "▸ setting up Claude Code hooks + skills…"
python3 -m mrtoken.cli init

echo ""
echo "✓ MR Token $(python3 -m mrtoken.cli --version) is set up."
echo ""
echo "Next:"
echo "  • Use Claude Code in a TERMINAL and watch the bottom status bar (the live HUD)."
echo "  • /mr-status, /mr-why, /mr-handoff work in any session."
echo "  • For retrospective reports on a specific project, run 'mrtoken-transcript init' in it."
echo "  • Update anytime:        ./update.sh"
echo "  • Share a beta log:      mrtoken-transcript export --redact > mrtoken-beta.json"
