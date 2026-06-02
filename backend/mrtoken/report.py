#!/usr/bin/env python3
"""MR Token MVP — CLI report.

Reads from SQLite ledger (populated by ingest.py, recommendations by rules.py).

Usage:
    python3 -m mrtoken.report [session_id_prefix] [--db mrtoken.db]
    python3 -m mrtoken.report --list [--db mrtoken.db]
"""
from __future__ import annotations
import argparse, json, os, sqlite3

SEV_PREFIX = {"high": "  [!]", "warn": "  [~]", "info": "  [i]"}


def fmt(n) -> str:
    return f"{n:,}"


def report(conn: sqlite3.Connection, prefix: str):
    row = conn.execute("""SELECT id,session_id,title,project_path,started_at,ended_at
        FROM trace WHERE session_id LIKE ? ORDER BY started_at DESC""",
        (prefix + "%",)).fetchone()
    if not row:
        print("no matching session"); return
    tid, sid, title, proj, started, ended = row

    mc = conn.execute("""SELECT COUNT(*),SUM(input_tokens),SUM(output_tokens),
        SUM(cache_read_input_tokens),SUM(cache_creation_input_tokens),SUM(est_cost_usd),
        SUM(is_sidechain),MIN(model),price_version FROM model_call WHERE trace_id=?""", (tid,)).fetchone()
    calls, inp, out, cr, cw, cost, side, model, pv = (x or 0 for x in mc)
    total_in = (inp or 0) + (cw or 0) + (cr or 0)
    cache_ratio = (cr / total_in) if total_in else 0

    print(f"\n{'─'*58}")
    print(f"  {sid[:8]}  {title or '(untitled)'}")
    print(f"  {proj or ''}")
    if started:
        print(f"  {started[:10]}  {model or ''}")
    print(f"{'─'*58}")
    print(f"  model calls         {fmt(calls):>12}   (subagent: {fmt(side)})")
    print(f"  input tokens        {fmt(inp):>12}")
    print(f"  output tokens       {fmt(out):>12}")
    print(f"  cache read          {fmt(cr):>12}")
    print(f"  cache write         {fmt(cw):>12}")
    print(f"  cache hit ratio     {cache_ratio:>11.1%}")
    if cost:
        print(f"  est cost (API-eq)   {'$'+f'{cost:,.4f}':>12}   ⚠ not your subscription bill  [{pv}]")
    total_tok = (inp or 0) + (out or 0)
    print(f"  total tokens        {fmt(total_tok):>12}")

    # largest tool outputs
    tools = conn.execute("""SELECT tool_name, output_chars, is_error FROM tool_call
        WHERE trace_id=? AND output_chars IS NOT NULL ORDER BY output_chars DESC LIMIT 5""",
        (tid,)).fetchall()
    if tools:
        print(f"\n  top tool outputs:")
        for name, oc, err in tools:
            tag = "  ERROR" if err else ""
            print(f"    {fmt(oc//4):>8} tok est   {name}{tag}")

    # recommendations from rule engine
    recs = conn.execute("""SELECT rule,severity,message,evidence_json,est_savings_tokens
        FROM recommendation WHERE trace_id=? ORDER BY
        CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, rule""",
        (tid,)).fetchall()
    if recs:
        print(f"\n  recommendations:")
        for rule, sev, msg, evj, savings in recs:
            pref = SEV_PREFIX.get(sev, "  [?]")
            label = f"{rule} ({sev})"
            print(f"\n{pref} {label}")
            # word-wrap message at 72 chars
            words = msg.split()
            line = "      "
            for w in words:
                if len(line) + len(w) > 72:
                    print(line); line = "      " + w + " "
                else:
                    line += w + " "
            if line.strip():
                print(line)
            if savings:
                print(f"      est savings: ~{fmt(savings)} tokens")
            if evj:
                ev = json.loads(evj)
                signals = ev.get("signals")
                if signals:
                    for s in signals:
                        print(f"      • {s}")
    else:
        print(f"\n  recommendations: none (run with --rules to analyse)")
    print(f"{'─'*58}\n")


def list_traces(conn: sqlite3.Connection):
    rows = conn.execute("""
        SELECT t.session_id, t.title, t.started_at,
            (SELECT SUM(input_tokens+output_tokens) FROM model_call m WHERE m.trace_id=t.id) tot,
            (SELECT COUNT(*) FROM recommendation r WHERE r.trace_id=t.id AND r.severity='high') highs
        FROM trace t ORDER BY t.started_at DESC LIMIT 40
    """).fetchall()
    print(f"\n  {'SESSION':8}  {'DATE':10}  {'TOKENS':>12}  {'HIGH':>4}  TITLE")
    print(f"  {'─'*8}  {'─'*10}  {'─'*12}  {'─'*4}  {'─'*28}")
    for sid, title, started, tot, highs in rows:
        date = (started or "")[:10]
        h = str(highs or "") if highs else ""
        label = sid[:8] if not sid.startswith("agent-") else sid[:14]
        print(f"  {label:8}  {date:10}  {fmt(tot or 0):>12}  {h:>4}  {title or ''}")
    print()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("session", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--db", default="mrtoken.db")
    a = ap.parse_args(argv)
    conn = sqlite3.connect(a.db)
    if a.list or not a.session:
        list_traces(conn)
    else:
        report(conn, a.session)


if __name__ == "__main__":
    main()
