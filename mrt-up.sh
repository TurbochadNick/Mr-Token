#!/usr/bin/env bash
# mrt-up — start MR Token UI dashboard on :4317. Idempotent (frees the port first).
# Port owner per ~/Projects/PORTS.md.
set -uo pipefail
PORT="${MRT_PORT:-4317}"
DIR="/Users/zacharynielsen/Projects/gate-pending/mr_token"
LOG="/tmp/mr_token.log"

pid="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
[ -n "$pid" ] && { echo "freeing :$PORT (pid $pid)"; kill $pid 2>/dev/null; sleep 1; }

cd "$DIR" || { echo "✗ no dir $DIR"; exit 1; }
echo "starting mr_token ui on :$PORT (log: $LOG)…"
( npm run dev -- ui --port "$PORT" >"$LOG" 2>&1 & )

for _ in $(seq 1 60); do
  lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && { echo "✓ mr_token ui up → http://localhost:$PORT"; exit 0; }
  sleep 1
done
echo "✗ mr_token ui did not come up within 60s — see $LOG"; tail -15 "$LOG"; exit 1
