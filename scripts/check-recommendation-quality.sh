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

"$PY" - "$ROOT" "$@" <<'PY'
import argparse
import os
import sys

root = sys.argv[1]
sys.path.insert(0, os.path.join(root, "backend"))

from mrtoken.datadir import codex_db_path
from mrtoken.ingest import connect, default_db_path
from mrtoken.validate import validate_db

parser = argparse.ArgumentParser(
    prog="check-recommendation-quality.sh",
    description="Fail if recommendation precision proxies fall below release gates.",
)
parser.add_argument("--db", help="SQLite DB to validate")
parser.add_argument("--codex", action="store_true", help="validate the central Codex DB")
parser.add_argument(
    "--rule",
    action="append",
    default=[],
    metavar="RULE:MIN_FIRES:MIN_PROXY",
    help="override/add a per-rule gate, e.g. fresh_handoff:10:0.85",
)
parser.add_argument(
    "--refresh-rules",
    action="store_true",
    help="re-run the rule engine before validation; use this on a disposable DB copy",
)
args = parser.parse_args(sys.argv[2:])

db = args.db or (codex_db_path() if args.codex else default_db_path(root))
default_gates = {
    "fresh_handoff": (10, 0.85),
    "retry_loop": (10, 0.90),
    "huge_tool_output": (5, 0.85),
    "step_runaway": (5, 0.85),
}
gates = dict(default_gates)
for raw in args.rule:
    try:
        name, min_fires, min_proxy = raw.split(":", 2)
        gates[name] = (int(min_fires), float(min_proxy))
    except ValueError:
        print(f"bad --rule value {raw!r}; expected RULE:MIN_FIRES:MIN_PROXY", file=sys.stderr)
        sys.exit(2)

conn = connect(db)
if args.refresh_rules:
    from mrtoken.rules import analyse

    tids = [row[0] for row in conn.execute("SELECT id FROM trace").fetchall()]
    for tid in tids:
        analyse(conn, tid)

report = validate_db(conn)
rules = report["rules"]
failures = []

print("MR Token recommendation quality gate")
print(f"db: {db}")
for name, (min_fires, min_proxy) in gates.items():
    data = rules.get(name)
    if not data:
        failures.append(f"{name}: missing")
        print(f"  FAIL {name:18} missing")
        continue
    proxy = data.get("precision_proxy")
    fired = data.get("fired", 0)
    strong = data.get("strong", 0)
    weak = data.get("weak", 0)
    moot = data.get("moot", 0)
    ok = fired >= min_fires and proxy is not None and proxy >= min_proxy
    status = "OK" if ok else "FAIL"
    proxy_s = "n/a" if proxy is None else f"{proxy:.0%}"
    print(
        f"  {status:4} {name:18} fired={fired:>3} strong={strong:>3} "
        f"weak={weak:>3} moot={moot:>3} proxy={proxy_s:>4} "
        f"gate=>={min_fires} fires, >={min_proxy:.0%}"
    )
    if fired < min_fires:
        failures.append(f"{name}: fired {fired} < {min_fires}")
    if proxy is None or proxy < min_proxy:
        failures.append(f"{name}: proxy {proxy_s} < {min_proxy:.0%}")

if failures:
    print("\nquality gate failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("quality gate passed")
PY
