#!/usr/bin/env bash
set -euo pipefail

# Pricing release gate (mirrors check-recommendation-quality.sh). Fails the build
# on structural/coverage regressions in prices.json; freshness is a non-fatal
# warning until a hard cap, since calendar passage alone shouldn't break CI.

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
import os
import sys
from datetime import date

root = sys.argv[1]
sys.path.insert(0, os.path.join(root, "backend"))

from mrtoken.ingest import load_prices, matched_price_key
from mrtoken.pricing import price_staleness, STALE_DAYS

# Families that must ALWAYS resolve to their own row, never the default fallback.
REQUIRED = [
    "claude-fable-5", "claude-mythos-5", "claude-opus-4-8", "claude-sonnet-5",
    "claude-haiku-4-5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
]
FIELDS = ("input", "output", "cache_read", "cache_write")
HARD_STALE_DAYS = 90

prices = load_prices()
failures = []

print("MR Token pricing gate")
print(f"version: {prices.get('version')}")

# structural — every row carries all four numeric fields
for name, row in prices.get("models", {}).items():
    bad = [f for f in FIELDS if not isinstance(row.get(f), (int, float))]
    if bad:
        failures.append(f"row '{name}' missing/non-numeric field(s): {', '.join(bad)}")

# coverage — required families must not fall to default
for m in REQUIRED:
    if matched_price_key(prices, m) is None:
        failures.append(f"'{m}' resolves to default (no matching price row)")

# tier ordering — each GPT tier must match its own key, not the generic gpt-5.6
for tier in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
    k = matched_price_key(prices, tier)
    if k != tier:
        failures.append(
            f"'{tier}' matched '{k}', not '{tier}' — tier keys must precede generic 'gpt-5.6'")

# freshness — non-fatal warning, fatal only past the hard cap
st = price_staleness(prices, date.today())
if st is None:
    print("  ! version is not a parseable YYYY-MM-DD date")
else:
    age, stale = st
    if age > HARD_STALE_DAYS:
        failures.append(f"price table is {age} days old (> {HARD_STALE_DAYS}d hard cap) — re-verify rates")
    elif stale:
        print(f"  ! price table is {age} days old (> {STALE_DAYS}d) — re-verify soon (non-fatal)")
    else:
        print(f"  OK freshness: {age} days old")

if failures:
    print("\npricing gate failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("pricing gate passed")
PY
