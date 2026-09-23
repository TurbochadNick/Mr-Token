#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PY=""
for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3; do
  [[ -n "$c" ]] || continue
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "need Python 3.11+ (set PYTHON=/path/to/python if needed)" >&2
  exit 1
fi

"$PY" - "$ROOT" <<'PY'
import json
import os
import subprocess
import sys
import tempfile

root = sys.argv[1]
hook = os.path.join(root, "backend", "hooks", "on_stop.py")
sid = "019f-accept-codex-hud"

with tempfile.TemporaryDirectory(prefix="mrtoken-codex-accept-") as tmp:
    codex_dir = os.path.join(tmp, ".codex", "sessions", "2026", "06", "30")
    os.makedirs(codex_dir, exist_ok=True)
    rollout = os.path.join(codex_dir, f"rollout-2026-06-30T00-00-00-{sid}.jsonl")
    rows = [
        {"timestamp": "2026-06-30T00:00:00Z", "type": "session_meta",
         "payload": {"session_id": sid, "cwd": root}},
        {"timestamp": "2026-06-30T00:00:01Z", "type": "turn_context",
         "payload": {"model": "gpt-5.5", "effort": "xhigh"}},
        {"timestamp": "2026-06-30T00:00:02Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {
             "model_context_window": 1_000_000,
             "last_token_usage": {
                 "input_tokens": 280_000,
                 "cached_input_tokens": 260_000,
                 "output_tokens": 1_000,
                 "total_tokens": 281_000,
             },
             # the provider's running session total, which the HUD shows as total expenditure
             "total_token_usage": {
                 "input_tokens": 280_000,
                 "cached_input_tokens": 260_000,
                 "output_tokens": 1_000,
                 "total_tokens": 281_000,
             }},
             "rate_limits": {"primary": {"used_percent": 42.0, "window_minutes": 10080,
                                         "resets_at": 1790000000}}}},
    ]
    with open(rollout, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    env = os.environ.copy()
    env["HOME"] = tmp
    env["MRTOKEN_DB"] = os.path.join(tmp, "codex.db")
    proc = subprocess.run(
        [sys.executable, hook],
        input=json.dumps({"session_id": sid, "cwd": root}),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)
    msg = json.loads(proc.stdout)["systemMessage"]
    # CHANGED EXPECTATION (fix/hud-parity), not a weakened check. This used to pin "~21k tok",
    # which was the fresh input + output SUBTOTAL; the HUD now shows the provider's running
    # TOTAL (281k). Cost is gone (no billing ground truth); the Codex CLI line already shows
    # model and effort, so the window rides on ctx; the version attributes the line.
    sys.path.insert(0, os.path.join(root, "backend"))
    from mrtoken.hud import attribution
    required = [f"{attribution()} · ", "ctx 28% used of 1M", "~281k tok", "cache hit 93%", "7d 42% used"]
    missing = [part for part in required if part not in msg]
    if "$" in msg:
        missing.append("no dollar figure")
    if missing:
        print(f"unexpected HUD: {msg}", file=sys.stderr)
        print(f"missing: {missing}", file=sys.stderr)
        sys.exit(1)
    print(msg)
PY
