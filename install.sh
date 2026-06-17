#!/usr/bin/env bash
# MR Token one-command install for testers. After cloning:
#   git clone <repo> && cd Mr-Token && ./install.sh
# Installs the Python backend, then sets up the Claude Code hooks + /mr-* skills.
# Update later with ./update.sh. See docs/QUICKSTART.md.
set -euo pipefail
cd "$(dirname "$0")"

echo "▸ MR Token install"

# 1. Find a Python 3.11+ interpreter (your `python3` may be older — e.g. macOS
#    ships 3.9). Try the common explicit names, then bare python3.
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "✗ need Python 3.11+ (none found). Try: brew install python@3.12"; exit 1; }
echo "▸ using $("$PY" -V)"

# 2. Install the backend. Editable pip is preferred (git pull picks up changes),
#    but the backend is pure-stdlib with zero deps, so if pip is broken (e.g. a
#    busted Homebrew Python), fall back to running straight from source.
if "$PY" -m pip install -e backend/ -q 2>/dev/null; then
  echo "▸ installed backend (editable)"
  RUN=("$PY" -m mrtoken.cli)
else
  echo "▸ pip unavailable — running from source (no install needed)"
  export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
  RUN=("$PY" -m mrtoken.cli)
fi

# 3. Claude Code hooks + global /mr-* skills + statusLine HUD
echo "▸ setting up Claude Code hooks + skills…"
"${RUN[@]}" init

echo ""
echo "✓ MR Token $("${RUN[@]}" --version) is set up."
echo ""
echo "Next:"
echo "  • Use Claude Code in a TERMINAL and watch the bottom status bar (the live HUD)."
echo "  • /mr-status, /mr-why, /mr-handoff work in any session."
echo "  • For retrospective reports on a specific project, run 'mrtoken-transcript init' in it."
echo "  • Update anytime:        ./update.sh"
echo "  • Turn it all off:       mrtoken-transcript uninstall"
echo "  • Share a beta log:      mrtoken-transcript export --redact > mrtoken-beta.json"
