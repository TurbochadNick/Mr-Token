#!/usr/bin/env bash
# mrt-down — stop MR Token UI dashboard (frees :4317). See ~/Projects/PORTS.md.
set -uo pipefail
PORT="${MRT_PORT:-4317}"
pid="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$pid" ]; then kill $pid 2>/dev/null; sleep 1; echo "🛑 mr_token ui stopped (:$PORT)"; else echo "mr_token ui not running (:$PORT)"; fi
