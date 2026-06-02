#!/usr/bin/env python3
"""MR Token — fleet summary across all ingested sessions."""
from __future__ import annotations
import sqlite3


def fmt(n) -> str:
    return f"{n:,}" if n is not None else "?"


def fleet_summary(conn: sqlite3.Connection):
    r = conn.execute("""
        SELECT
          COUNT(DISTINCT CASE WHEN source='claude_code' THEN id END)          sessions,
          COUNT(DISTINCT CASE WHEN source='claude_code_subagent' THEN id END)  subagent_sessions,
          (SELECT COUNT(*) FROM model_call)                                    model_calls,
          (SELECT COUNT(*) FROM tool_call)                                     tool_calls,
          (SELECT COUNT(*) FROM tool_call WHERE is_error=1)                    tool_errors,
          (SELECT SUM(input_tokens+output_tokens) FROM model_call)             total_tokens,
          (SELECT SUM(input_tokens) FROM model_call)                           input_tokens,
          (SELECT SUM(output_tokens) FROM model_call)                          output_tokens,
          (SELECT SUM(cache_read_input_tokens) FROM model_call)                cache_read,
          (SELECT SUM(cache_creation_input_tokens) FROM model_call)            cache_write,
          (SELECT SUM(input_tokens+cache_read_input_tokens
                      +cache_creation_input_tokens) FROM model_call)           total_input_side,
          (SELECT SUM(est_cost_usd) FROM model_call)                           est_cost
        FROM trace
    """).fetchone()
    (sessions, sub_sess, mc, tc, te, total_tok, inp, out, cr, cw, total_in, cost) = r
    cache_pct = (cr or 0) / (total_in or 1)

    print(f"\n{'─'*54}")
    print(f"  MR Token — Fleet Summary")
    print(f"{'─'*54}")
    print(f"  sessions          {fmt(sessions):>14}  ({fmt(sub_sess)} subagent)")
    print(f"  model calls       {fmt(mc):>14}")
    print(f"  tool calls        {fmt(tc):>14}  (errors: {fmt(te)})")
    print(f"{'─'*54}")
    print(f"  input tokens      {fmt(inp):>14}")
    print(f"  output tokens     {fmt(out):>14}")
    print(f"  cache read        {fmt(cr):>14}")
    print(f"  cache write       {fmt(cw):>14}")
    print(f"  total tokens      {fmt(total_tok):>14}")
    print(f"  cache hit ratio   {cache_pct:>13.1%}")
    print(f"  est cost (API-eq) {'$'+f'{cost:,.2f}':>14}  ⚠ not a real bill")
    print(f"{'─'*54}")

    # recommendation breakdown
    rec_rows = conn.execute("""
        SELECT rule, severity, COUNT(*) n FROM recommendation
        GROUP BY rule, severity
        ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, rule
    """).fetchall()
    if rec_rows:
        print(f"\n  recommendations across all sessions:")
        for rule, sev, n in rec_rows:
            prefix = "[!]" if sev == "high" else "[~]" if sev == "warn" else "[i]"
            print(f"    {prefix} {rule:28} ×{n}")

    # top sessions by total tokens (main sessions only)
    print(f"\n  top 5 sessions by token usage:")
    top = conn.execute("""
        SELECT t.session_id, t.title, t.started_at,
               SUM(mc.input_tokens+mc.output_tokens) total,
               (SELECT COUNT(*) FROM recommendation r WHERE r.trace_id=t.id AND r.severity='high') highs
        FROM trace t JOIN model_call mc ON mc.trace_id=t.id
        WHERE t.source='claude_code'
        GROUP BY t.id ORDER BY total DESC LIMIT 5
    """).fetchall()
    for sid, title, ts, total, highs in top:
        date = (ts or "")[:10]
        h = f"  {highs}✗" if highs else ""
        print(f"    {sid[:8]}  {date}  {fmt(total):>12}  {title or ''}{h}")

    # subagent summary
    sub_count = conn.execute(
        "SELECT COUNT(*) FROM trace WHERE source='claude_code_subagent'"
    ).fetchone()[0]
    if sub_count:
        sub_tok = conn.execute("""
            SELECT SUM(mc.input_tokens+mc.output_tokens)
            FROM model_call mc JOIN trace t ON t.id=mc.trace_id
            WHERE t.source='claude_code_subagent'
        """).fetchone()[0] or 0
        print(f"\n  subagent sessions: {sub_count}  •  {fmt(sub_tok)} tokens total")
        print(f"  run: mrtoken-transcript subagents  for per-parent breakdown")

    print(f"{'─'*54}\n")
