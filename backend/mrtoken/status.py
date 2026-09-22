#!/usr/bin/env python3
"""MR Token — `status`: a one-glance "where am I right now" for the current session.

A lighter, one-shot cousin of `watch`: ingests the current session, runs the
rules, and prints a compact snapshot (profile, calls, tokens, cache, est cost,
current context size) plus the single most important next action. Deterministic.
"""
from __future__ import annotations
import os, sqlite3

from mrtoken.ingest import connect, load_prices, ingest_file, default_db_path
from mrtoken.rules import analyse
from mrtoken.watch import resolve_path
from mrtoken.statusline import context_window, CONTEXT_WARN_PCT
from mrtoken.pricing import COST_CAVEAT
from mrtoken.savings_card import card_for_session, render_savings_card


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else f"{n:,.2f}"


def status_snapshot(conn: sqlite3.Connection, tid: int, *, routing: dict | None = None) -> dict:
    s = conn.execute(
        "SELECT profile, model_calls, cumulative_expenditure_tokens, cumulative_expenditure_provenance, api_est_cost_usd, billing_mode, cache_hit_ratio, "
        "tool_errors FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
    profile, calls, total_tok, total_provenance, cost, billing, cache, errs = s or (None,)*8
    # current context window ≈ the latest call's whole input side
    cur = conn.execute(
        "SELECT input_tokens + cache_read_input_tokens + cache_creation_input_tokens "
        "FROM model_call WHERE trace_id=? ORDER BY timestamp DESC LIMIT 1", (tid,)).fetchone()
    context_now = (cur[0] if cur else 0) or 0
    # window from the session MAX (sticky/ratchet), not the latest call, so the
    # "large" flag and inferred window don't flip when a call dips below a tier
    mx = conn.execute(
        "SELECT MAX(input_tokens + cache_read_input_tokens + cache_creation_input_tokens) "
        "FROM model_call WHERE trace_id=?", (tid,)).fetchone()
    window = context_window(max(context_now, (mx[0] if mx else 0) or 0))
    context_large = context_now >= window * CONTEXT_WARN_PCT / 100
    return {"profile": profile, "calls": calls or 0, "total_tokens": total_tok,
            "total_provenance": total_provenance or "unknown", "est_cost": cost, "billing_mode": billing or "unknown", "cache_ratio": cache, "tool_errors": errs or 0,
            "context_now": context_now, "context_large": context_large,
            "card": card_for_session(conn, tid, routing=routing)}


def print_status(db_path: str | None, session_arg: str | None, *, routing: dict | None = None) -> int:
    path = resolve_path(session_arg)
    if not path:
        print("mrtoken status: no transcript found for this project"); return 1
    conn = connect(db_path or default_db_path())
    parent = path.split(os.sep)[-3] if "subagents" in path else None
    r = ingest_file(conn, path, load_prices(), parent_session_id=parent)
    tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (r["session_id"],)).fetchone()[0]
    analyse(conn, tid)
    s = status_snapshot(conn, tid, routing=routing)

    cache = f"{s['cache_ratio']:.0%}" if s["cache_ratio"] is not None else "n/a"
    print(f"\n  mr token status · {r['session_id'][:8]} · profile: {s['profile'] or '?'}")
    expenditure = (f"~{_fmt(s['total_tokens'])} tok ({s['total_provenance']})"
                   if s["total_tokens"] is not None else "UNKNOWN tok")
    line = f"  {s['calls']} calls · cumulative token total {expenditure} · usage type {s['billing_mode']} · cache {cache}"
    if s["billing_mode"] == "api" and s["est_cost"] is not None:
        line += f" · est API usage ${_fmt(s['est_cost'])}"
    print(line + (f" · {s['tool_errors']} tool errors" if s['tool_errors'] else ""))
    flag = "  ⚠ large" if s["context_large"] else ""
    print(f"  context now ~{_fmt(s['context_now'])} tok{flag}")
    print("  · billing evidence: session-owned provider records only; absent evidence is UNKNOWN")
    print()
    for line in render_savings_card(s["card"]):
        print(line)
    if s["card"]["rule"]:
        print(f"  feedback: mrtoken-transcript feedback {r['session_id'][:8]} "
              f"{s['card']['rule']} right|wrong|unsure")
    try:
        from mrtoken.update_check import check_for_update, release_tag_warning
        nudge = check_for_update()
        if nudge:
            print(f"\n  {nudge}")
        gap = release_tag_warning()  # maintainer-facing; silent on non-git installs
        if gap:
            print(f"\n  {gap}")
        from mrtoken.pricing import freshness_warning
        stale = freshness_warning(load_prices())  # nudge to re-verify old rates
        if stale:
            print(f"\n  {stale}")
    except Exception:
        pass  # never let an update check break status
    print()
    return 0
