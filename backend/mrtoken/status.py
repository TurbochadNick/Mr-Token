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


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else f"{n:,.2f}"


def status_snapshot(conn: sqlite3.Connection, tid: int) -> dict:
    s = conn.execute(
        "SELECT profile, model_calls, total_tokens, est_cost_usd, cache_hit_ratio, "
        "tool_errors FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
    profile, calls, total_tok, cost, cache, errs = s or (None,)*6
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
    top = conn.execute(
        "SELECT rule, severity, message FROM recommendation WHERE trace_id=? "
        "ORDER BY CASE rule WHEN 'fresh_handoff' THEN 0 WHEN 'retry_loop' THEN 1 ELSE 2 END, "
        "CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END LIMIT 1", (tid,)).fetchone()
    return {"profile": profile, "calls": calls or 0, "total_tokens": total_tok or 0,
            "est_cost": cost or 0.0, "cache_ratio": cache, "tool_errors": errs or 0,
            "context_now": context_now, "context_large": context_large,
            "top": ({"rule": top[0], "severity": top[1], "message": top[2]} if top else None)}


def print_status(db_path: str | None, session_arg: str | None) -> int:
    path = resolve_path(session_arg)
    if not path:
        print("mrtoken status: no transcript found for this project"); return 1
    conn = connect(db_path or default_db_path())
    parent = path.split(os.sep)[-3] if "subagents" in path else None
    r = ingest_file(conn, path, load_prices(), parent_session_id=parent)
    tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (r["session_id"],)).fetchone()[0]
    analyse(conn, tid)
    s = status_snapshot(conn, tid)

    cache = f"{s['cache_ratio']:.0%}" if s["cache_ratio"] is not None else "n/a"
    print(f"\n  mr token status · {r['session_id'][:8]} · profile: {s['profile'] or '?'}")
    print(f"  {s['calls']} calls · ~{_fmt(s['total_tokens'])} tok · cache {cache} · "
          f"est ${_fmt(s['est_cost'])}"
          + (f" · {s['tool_errors']} tool errors" if s['tool_errors'] else ""))
    flag = "  ⚠ large" if s["context_large"] else ""
    print(f"  context now ~{_fmt(s['context_now'])} tok{flag}")
    print(f"  · est $ is an {COST_CAVEAT}")
    if s["top"]:
        print(f"\n  next: [{s['top']['rule']}] {s['top']['message']}")
        print(f"  feedback: mrtoken-transcript feedback {r['session_id'][:8]} "
              f"{s['top']['rule']} right|wrong|unsure")
    else:
        print(f"\n  next: nothing flagged — burning clean.")
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
