#!/usr/bin/env python3
"""MR Token — pricing metadata guardrails.

Rates in prices.json are hand-maintained and manually verified; nothing here can
prove a rate is *correct*. What these helpers DO is make pricing's two silent
failure modes loud:

  1. Coverage — a model id seen in transcripts that no price row matches, so it is
     billed at the Sonnet-shaped `default` (see ingest.matched_price_key).
  2. Freshness — the price table's `version` date drifting far into the past,
     signalling the rates should be re-verified against published pricing.

Callers (doctor / status / validate / the CI gate) decide how to present these.
Pure functions + one small DB query; no AI, no network.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from mrtoken.ingest import matched_price_key

# Re-verify cadence: warn once the table's version date is older than this.
STALE_DAYS = 45

# One canonical cost caveat so no surface drifts or omits it. est_cost_usd is an
# API-equivalent estimate (measured tokens × table rates); it is NOT what a
# Claude Code Max/Pro or ChatGPT subscription actually bills.
COST_CAVEAT = "API-equivalent estimate, not a subscription bill"


def uncovered_models(conn: sqlite3.Connection, prices: dict) -> list[tuple[str, int]]:
    """Distinct non-empty model ids in model_call that NO price row covers (so they
    are priced at `default`), paired with call counts, worst-offender first."""
    rows = conn.execute(
        "SELECT model, COUNT(*) FROM model_call "
        "WHERE model IS NOT NULL AND model != '' GROUP BY model"
    ).fetchall()
    out = [(m, c) for (m, c) in rows if matched_price_key(prices, m) is None]
    out.sort(key=lambda mc: -mc[1])
    return out


def _version_date(prices: dict) -> date | None:
    try:
        return datetime.strptime(str((prices or {}).get("version")), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def price_staleness(prices: dict, today: date | None = None) -> tuple[int, bool] | None:
    """(age_days, is_stale) for the table's version date, or None if `version` is
    not a parseable YYYY-MM-DD. is_stale = age_days > STALE_DAYS."""
    d = _version_date(prices)
    if d is None:
        return None
    age = ((today or date.today()) - d).days
    return age, age > STALE_DAYS


def freshness_warning(prices: dict, today: date | None = None) -> str | None:
    """A one-line nudge when the price table is stale, else None."""
    st = price_staleness(prices, today)
    if st is None or not st[1]:
        return None
    age, _ = st
    return (f"⚠ price table is {age} days old (version {prices.get('version')}) — "
            f"re-verify rates vs published pricing and bump prices.json.")
