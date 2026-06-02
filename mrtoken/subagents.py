#!/usr/bin/env python3
"""MR Token — subagent ROI accounting.

For each subagent transcript linked to a parent session, compute:
  - tokens consumed by the subagent itself
  - size of the result returned to the parent (the tool_result payload)
  - compression ratio: result_tokens / subagent_total_tokens
    → < 0.1  = focused (subagent digested a lot, returned compact summary) ✓
    → 0.1-0.3 = acceptable
    → > 0.3  = bloated (subagent returned a large chunk; parent carries it all)
  - verdict: SAVED | NEUTRAL | MULTIPLIED

Prints a per-session breakdown and fleet verdict.
"""
from __future__ import annotations
import json, sqlite3


BLOAT_RATIO_WARN = 0.30    # result > 30% of subagent cost → warn
BLOAT_RATIO_HIGH = 0.60    # result > 60% → high


def fmt(n) -> str:
    return f"{n:,}" if n is not None else "?"


def compression_label(ratio) -> str:
    if ratio is None:
        return "unknown"
    if ratio < 0.10:
        return "focused ✓"
    if ratio < BLOAT_RATIO_WARN:
        return "acceptable"
    if ratio < BLOAT_RATIO_HIGH:
        return "bloated ⚠"
    return "very bloated ✗"


def get_subagent_data(conn: sqlite3.Connection, parent_sid_prefix: str) -> list[dict]:
    """Return list of subagent dicts for a given parent session prefix."""
    parent = conn.execute(
        "SELECT id, session_id FROM trace WHERE session_id LIKE ? AND source='claude_code' "
        "ORDER BY started_at DESC LIMIT 1",
        (parent_sid_prefix + "%",)
    ).fetchone()
    if not parent:
        return []
    parent_tid, parent_sid = parent

    # find subagent traces parented to this session
    sub_traces = conn.execute(
        "SELECT id, session_id, started_at FROM trace "
        "WHERE parent_session_id=? AND source='claude_code_subagent' "
        "ORDER BY started_at ASC",
        (parent_sid,)
    ).fetchall()

    results = []
    for sub_tid, sub_sid, sub_start in sub_traces:
        # subagent's own token cost
        mc = conn.execute("""
            SELECT COUNT(*),
                   SUM(input_tokens), SUM(output_tokens),
                   SUM(cache_read_input_tokens), SUM(cache_creation_input_tokens),
                   SUM(est_cost_usd)
            FROM model_call WHERE trace_id=?
        """, (sub_tid,)).fetchone()
        calls, inp, out, cr, cw, cost = (x or 0 for x in mc)
        sub_total = (inp or 0) + (out or 0)

        # find the tool_result in the PARENT that corresponds to this subagent.
        # Subagents are launched via Task tool calls; the result is the tool_result output.
        # Heuristic: find a Task / agent-like tool_call in the parent whose ended_at
        # is closest to the subagent's last timestamp.
        sub_end = conn.execute(
            "SELECT MAX(timestamp) FROM model_call WHERE trace_id=?", (sub_tid,)
        ).fetchone()[0]
        result_chars = conn.execute("""
            SELECT tc.output_chars FROM tool_call tc
            WHERE tc.trace_id=?
              AND tc.tool_name IN ('Task','TodoWrite','mcp__Agent')
              AND tc.output_chars IS NOT NULL
            ORDER BY ABS(JULIANDAY(COALESCE(tc.ended_at, tc.started_at)) - JULIANDAY(?))
            LIMIT 1
        """, (parent_tid, sub_end or sub_start or "")).fetchone()
        # fallback: any large tool_result that ended around the subagent's end time
        if not result_chars:
            result_chars = conn.execute("""
                SELECT tc.output_chars FROM tool_call tc
                WHERE tc.trace_id=? AND tc.output_chars > 200
                ORDER BY ABS(JULIANDAY(COALESCE(tc.ended_at, tc.started_at)) - JULIANDAY(?))
                LIMIT 1
            """, (parent_tid, sub_end or sub_start or "")).fetchone()
        result_tok = (result_chars[0] // 4) if result_chars and result_chars[0] else None

        ratio = (result_tok / sub_total) if (result_tok and sub_total) else None
        largest_tool = conn.execute("""
            SELECT tool_name, output_chars FROM tool_call
            WHERE trace_id=? AND output_chars IS NOT NULL
            ORDER BY output_chars DESC LIMIT 1
        """, (sub_tid,)).fetchone()

        results.append({
            "sub_sid": sub_sid,
            "started_at": sub_start,
            "model_calls": calls,
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read": cr,
            "sub_total_tokens": sub_total,
            "est_cost_usd": cost,
            "result_tokens_est": result_tok,
            "compression_ratio": ratio,
            "label": compression_label(ratio),
            "largest_tool": largest_tool,
        })
    return results


def verdict(subs: list[dict]) -> str:
    if not subs:
        return "no subagents"
    bloated = sum(1 for s in subs if s["compression_ratio"] and s["compression_ratio"] >= BLOAT_RATIO_WARN)
    focused = sum(1 for s in subs if s["compression_ratio"] and s["compression_ratio"] < 0.10)
    if bloated == 0:
        return "SAVED  — subagents were focused; net token benefit likely"
    if bloated > len(subs) // 2:
        return "MULTIPLIED  — majority of subagents returned bloated results; parent carried the cost"
    return "NEUTRAL  — mixed; some subagents focused, some bloated"


def subagent_report(conn: sqlite3.Connection, prefix: str):
    if not prefix:
        # fleet view: all parent sessions that have subagents
        parents = conn.execute("""
            SELECT DISTINCT t_parent.session_id, t_parent.title,
                   COUNT(t_sub.id) n_subs,
                   SUM(mc_sub.total) sub_tokens
            FROM trace t_parent
            JOIN trace t_sub ON t_sub.parent_session_id = t_parent.session_id
            LEFT JOIN (
                SELECT trace_id, SUM(input_tokens+output_tokens) total
                FROM model_call GROUP BY trace_id
            ) mc_sub ON mc_sub.trace_id = t_sub.id
            WHERE t_parent.source='claude_code'
            GROUP BY t_parent.id ORDER BY t_parent.started_at DESC
        """).fetchall()
        if not parents:
            print("  no sessions with subagents found"); return
        print(f"\n  {'SESSION':8}  {'SUBS':>4}  {'SUB TOKENS':>12}  TITLE")
        print(f"  {'─'*8}  {'─'*4}  {'─'*12}  {'─'*28}")
        for sid, title, n, toks in parents:
            print(f"  {sid[:8]}  {n:>4}  {fmt(toks):>12}  {title or ''}")
        print(f"\n  run: mrtoken subagents <session-prefix>  for per-subagent detail\n")
        return

    subs = get_subagent_data(conn, prefix)
    parent = conn.execute(
        "SELECT session_id, title FROM trace WHERE session_id LIKE ? AND source='claude_code' LIMIT 1",
        (prefix + "%",)
    ).fetchone()
    if not parent:
        print(f"  no parent session matching '{prefix}'"); return
    psid, ptitle = parent

    print(f"\n{'─'*60}")
    print(f"  subagents of {psid[:8]}  {ptitle or ''}")
    print(f"{'─'*60}")

    if not subs:
        print("  no subagent transcripts linked to this session\n"); return

    total_sub_tokens = sum(s["sub_total_tokens"] for s in subs)
    print(f"  {len(subs)} subagent(s)  •  {fmt(total_sub_tokens)} total tokens consumed\n")
    print(f"  {'AGENT':14}  {'CALLS':>5}  {'TOKENS':>10}  {'RESULT':>8}  {'RATIO':>6}  VERDICT")
    print(f"  {'─'*14}  {'─'*5}  {'─'*10}  {'─'*8}  {'─'*6}  {'─'*20}")

    for s in subs:
        r = f"{s['compression_ratio']:.2f}" if s["compression_ratio"] is not None else "  ?"
        res = fmt(s["result_tokens_est"]) if s["result_tokens_est"] else "?"
        print(f"  {s['sub_sid'][:14]}  {s['model_calls']:>5}  "
              f"{fmt(s['sub_total_tokens']):>10}  {res:>8}  {r:>6}  {s['label']}")
        if s["largest_tool"]:
            tname, toc = s["largest_tool"]
            print(f"  {'':14}  largest tool: {tname} ~{fmt(toc//4)} tok")

    print(f"\n  verdict: {verdict(subs)}")

    bloated = [s for s in subs if s["compression_ratio"] and s["compression_ratio"] >= BLOAT_RATIO_WARN]
    if bloated:
        print(f"\n  bloated subagents returned large results that the parent had to carry.")
        print(f"  consider: instruct subagents to return structured summaries, not raw content.")

    print(f"{'─'*60}\n")
