#!/usr/bin/env python3
"""MR Token — `roi`: quantify the addressable token waste MR Token can target.

HONESTY FIRST: this is a data-grounded ESTIMATE of *addressable* waste and the
*projected* saving from acting on it — NOT a measured outcome from a controlled
trial. We have not yet run an A/B where users follow vs ignore the advice. Every
number here is labeled as an estimate and uses conservative, separated categories
so they are not double-counted into an inflated headline.

Two things it reports:
  1. Addressable waste by category (per session or fleet-wide).
  2. Handoff before/after — the carry-cost a fresh start would avoid, per call.
"""
from __future__ import annotations
import sqlite3

HUGE_TOOL_CHARS = 40_000


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else f"{n:,.2f}"


def _waste_categories(conn: sqlite3.Connection, where: str, params: tuple) -> dict:
    # oversized tool output: tokens ABOVE the threshold (the avoidable excess)
    excess = conn.execute(f"""
        SELECT COALESCE(SUM((output_chars - {HUGE_TOOL_CHARS})/4), 0)
        FROM tool_call WHERE output_chars > {HUGE_TOOL_CHARS} AND {where}""", params).fetchone()[0]
    # retry waste: dead output from errored tool calls
    retry = conn.execute(f"""
        SELECT COALESCE(SUM(output_tokens_est),0) FROM tool_call
        WHERE is_error=1 AND {where}""", params).fetchone()[0]
    # uncached repeated context: from the (already cache-aware) recommendation
    repeat = conn.execute(f"""
        SELECT COALESCE(SUM(est_savings_tokens),0) FROM recommendation
        WHERE rule='repeated_context' AND {where}""", params).fetchone()[0]
    return {"oversized tool outputs (excess)": int(excess or 0),
            "retry / errored output": int(retry or 0),
            "uncached repeated context": int(repeat or 0)}


def _handoff_carry(conn: sqlite3.Connection, tid: int) -> dict | None:
    # context carried per call ≈ cache_read on a representative (max) call
    row = conn.execute("""
        SELECT MAX(cache_read_input_tokens), AVG(cache_read_input_tokens), COUNT(*)
        FROM model_call WHERE trace_id=?""", (tid,)).fetchone()
    carried_max, carried_avg, calls = row
    if not carried_max:
        return None
    handoff_size = 1500  # a compact handoff is ~1-2k tokens
    saving_per_call = max(0, int((carried_avg or 0) - handoff_size))
    return {"carried_per_call_avg": int(carried_avg or 0),
            "carried_per_call_peak": int(carried_max or 0),
            "handoff_size_est": handoff_size,
            "saving_per_future_call": saving_per_call, "calls": calls}


def roi_session(conn: sqlite3.Connection, tid: int) -> dict:
    spend = conn.execute("""
        SELECT COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(est_cost_usd),0)
        FROM model_call WHERE trace_id=?""", (tid,)).fetchone()
    total_tok, cost = spend
    cats = _waste_categories(conn, "trace_id=?", (tid,))
    addressable = sum(cats.values())
    return {"total_tokens": total_tok, "est_cost": cost, "categories": cats,
            "addressable_tokens": addressable,
            "addressable_pct": (addressable / total_tok) if total_tok else 0,
            "handoff": _handoff_carry(conn, tid)}


def roi_fleet(conn: sqlite3.Connection) -> dict:
    spend = conn.execute(
        "SELECT COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(est_cost_usd),0), "
        "COALESCE(SUM(cache_read_input_tokens),0) FROM model_call").fetchone()
    total_tok, cost, cache_read = spend
    cats = _waste_categories(conn, "1=1", ())
    addressable = sum(cats.values())
    sessions = conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0]
    # sessions deep enough that a mid-session reset would have helped
    deep = conn.execute("""
        SELECT COUNT(*) FROM (SELECT trace_id FROM model_call
        GROUP BY trace_id HAVING COUNT(*) >= 30)""").fetchone()[0]
    return {"sessions": sessions, "total_tokens": total_tok, "est_cost": cost,
            "cache_read_tokens": cache_read, "deep_sessions": deep,
            "categories": cats, "addressable_tokens": addressable,
            "addressable_pct": (addressable / total_tok) if total_tok else 0}


def print_roi(conn: sqlite3.Connection, prefix: str | None) -> None:
    print(f"\n  MR Token — ROI estimate  ⚠ data-grounded ESTIMATE, not a controlled-trial measurement")
    print(f"  {'─'*62}")
    if prefix:
        row = conn.execute("SELECT id, session_id FROM trace WHERE session_id LIKE ? "
                           "ORDER BY started_at DESC LIMIT 1", (prefix + "%",)).fetchone()
        if not row:
            print("  no matching session\n"); return
        tid, sid = row
        r = roi_session(conn, tid)
        print(f"  session {sid[:8]} · ~{_fmt(r['total_tokens'])} tok · est ${_fmt(r['est_cost'])}")
        h = r["handoff"]
    else:
        r = roi_fleet(conn)
        print(f"  fleet · {r['sessions']} sessions · ~{_fmt(r['total_tokens'])} tok · est ${_fmt(r['est_cost'])}")
        h = None

    # ── 1. STRUCTURAL: the big lever — carrying context across many calls ──
    print(f"\n  ① Structural opportunity — context carry (usually the biggest lever):")
    if h:
        print(f"    this session carried ~{_fmt(h['carried_per_call_avg'])} tok/call "
              f"(peak ~{_fmt(h['carried_per_call_peak'])}) across {h['calls']} calls")
        print(f"    a fresh start after a ~{_fmt(h['handoff_size_est'])}-tok handoff replaces that —")
        print(f"    est saving ~{_fmt(h['saving_per_future_call'])} tok on the NEXT calls")
        print(f"    (a fresh session re-accumulates, so total saving depends on how much")
        print(f"     longer you'd have continued — this is the marginal, not a forever, number)")
    else:
        cr = r.get("cache_read_tokens", 0)
        crx = cr / r["total_tokens"] if r["total_tokens"] else 0
        print(f"    ~{_fmt(cr)} tok were re-read context (cache reads) — {crx:.0f}× your in+out volume.")
        print(f"    {r['deep_sessions']} session(s) ran ≥30 calls deep, where a mid-session reset")
        print(f"    (/mr-handoff) would have cut the carry. This is where most spend hides.")

    # ── 2. TACTICAL: smaller rule-based waste ──
    print(f"\n  ② Tactical waste (smaller; conservative, categories may overlap):")
    for name, tok in r["categories"].items():
        pct = tok / r["total_tokens"] if r["total_tokens"] else 0
        print(f"    {name:34} ~{_fmt(tok):>12} tok  ({pct:.1%})")
    print(f"    {'─'*34} {'─'*12}")
    print(f"    {'tactical total (upper bound)':34} ~{_fmt(r['addressable_tokens']):>12} tok  "
          f"({r['addressable_pct']:.1%} of spend)")

    print(f"\n  Read together: on well-cached sessions the tactical categories are small —")
    print(f"  the real money is ① context carry, which the handoff/compaction wedge targets.")
    print(f"  All figures are ESTIMATES of opportunity; true ROI needs a controlled trial.\n")
