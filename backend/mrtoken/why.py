#!/usr/bin/env python3
"""MR Token — `why`: diagnose where a session's cost actually went.

Decomposes spend into its shape (generating output vs carrying cached context vs
writing new context vs fresh input), attributes avoidable drivers (oversized tool
outputs, retries, subagents, uncached repeats), and names the single biggest
"fuel leak" with the action to take. Deterministic, no AI.
"""
from __future__ import annotations
import sqlite3

from mrtoken.ingest import load_prices, price_for
from mrtoken.savings_card import card_for_session, render_savings_card


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else f"{n:,.2f}"


def diagnose(conn: sqlite3.Connection, tid: int) -> dict:
    prices = load_prices()
    mc = conn.execute("""
        SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),
               COALESCE(SUM(cache_read_input_tokens),0),
               COALESCE(SUM(cache_creation_input_tokens),0),
               COALESCE(SUM(est_cost_usd),0), COUNT(*)
        FROM model_call WHERE trace_id=?""", (tid,)).fetchone()
    inp, out, cr, cw, cost, calls = mc
    billing = conn.execute("SELECT billing_mode,cumulative_expenditure_tokens,cumulative_expenditure_provenance "
                           "FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
    billing_mode, cumulative_total, total_provenance = billing or ("unknown", None, "unknown")
    model = conn.execute(
        "SELECT model FROM model_call WHERE trace_id=? AND model IS NOT NULL "
        "GROUP BY model ORDER BY COUNT(*) DESC LIMIT 1", (tid,)).fetchone()
    model = model[0] if model else None
    p = price_for(prices, model)
    M = 1_000_000.0

    # cost shape (recomputed per component with the primary model's prices)
    comp = {
        "generating output":      out * p["output"] / M,
        "carrying cached context": cr * p["cache_read"] / M,
        "writing new context":    cw * p["cache_write"] / M,
        "fresh input":            inp * p["input"] / M,
    }
    comp_total = sum(comp.values()) or 1e-9

    # avoidable drivers — use the SAME profile-aware threshold as the rules engine
    # (not a hardcoded 40000, which disagreed with the huge_tool_output rule)
    from mrtoken.rules import _thresholds
    huge_limit = _thresholds(conn, tid)[0]["huge_tool_chars"]
    huge = conn.execute("""
        SELECT COALESCE(SUM(output_tokens_est),0), COUNT(*) FROM tool_call
        WHERE trace_id=? AND output_chars > ?""", (tid, huge_limit)).fetchone()
    huge_tok, huge_n = huge
    retry = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(output_tokens_est),0) FROM tool_call
        WHERE trace_id=? AND is_error=1""", (tid,)).fetchone()
    retry_n, retry_tok = retry
    sub = conn.execute("""
        SELECT COUNT(DISTINCT t.id), COALESCE(SUM(m.input_tokens+m.output_tokens),0)
        FROM trace t JOIN model_call m ON m.trace_id=t.id
        WHERE t.parent_session_id=(SELECT session_id FROM trace WHERE id=?)""", (tid,)).fetchone()
    sub_n, sub_tok = sub

    drivers = []
    if huge_tok:
        drivers.append(("oversized tool outputs",
                        f"{huge_n} result(s), ~{_fmt(huge_tok)} tok — re-paid via cache on every later call"))
    if retry_n:
        drivers.append(("retries / errors",
                        f"{retry_n} errored tool call(s), ~{_fmt(retry_tok)} tok of dead output"))
    if sub_n:
        drivers.append(("subagents", f"{sub_n} subagent(s), ~{_fmt(sub_tok)} tok consumed"))

    # headline: use the same unit and denominator as the table.  Cost shares are
    # meaningful only for positively API-metered sessions; all others use tokens.
    actions = {
        "carrying cached context": "context is large and re-read every call — a fresh handoff (/mr-handoff) cuts the carry",
        "generating output": "generation-heavy — consider lower reasoning effort or tighter asks",
        "writing new context": "lots of new context entering the window — trim what you add (huge reads/logs)",
        "fresh input": "uncached input dominates — ensure stable context sits in cache-eligible positions",
    }
    token_shape = {"generating output": out, "carrying cached context": cr,
                   "writing new context": cw, "fresh input": inp}
    shape = comp if billing_mode == "api" else token_shape
    headline_total = comp_total if billing_mode == "api" else sum(token_shape.values()) or 1
    top_shape, top_val = max(shape.items(), key=lambda kv: kv[1])
    unit = "cost" if billing_mode == "api" else "observed token activity"
    headline = f"{top_shape} is the main fuel leak ({top_val/headline_total:.0%} of {unit}) — {actions[top_shape]}"

    return {"calls": calls, "model": model, "tokens": inp+out,
            "cost": cost if billing_mode == "api" else None, "billing_mode": billing_mode,
            "cumulative_total": cumulative_total, "total_provenance": total_provenance,
            "shape": shape,
            "shape_total": comp_total if billing_mode == "api" else sum(token_shape.values()) or 1,
            "drivers": drivers, "headline": headline}


def print_diagnosis(conn: sqlite3.Connection, prefix: str, *, routing: dict | None = None) -> None:
    row = conn.execute(
        "SELECT id, session_id, profile FROM trace WHERE session_id LIKE ? "
        "ORDER BY started_at DESC LIMIT 1", (prefix + "%",)).fetchone()
    if not row:
        print("no matching session"); return
    tid, sid, profile = row
    d = diagnose(conn, tid)
    cost = f" · est API usage ${_fmt(d['cost'])}" if d["cost"] is not None else ""
    print(f"\n  why is {sid[:8]} expensive?  (profile: {profile or '?'} · "
          f"{d['calls']} calls · ~{_fmt(d['tokens'])} tok · usage type {d['billing_mode']}{cost})")
    total = (f"~{_fmt(d['cumulative_total'])} tok ({d['total_provenance']})"
             if d["cumulative_total"] is not None else "UNKNOWN tok")
    print(f"  cumulative token total: {total}")
    print(f"  {'─'*60}")
    print("  cost shape:" if d["billing_mode"] == "api" else "  observed token components (computed total uses documented disjoint provider components):")
    for name, val in sorted(d["shape"].items(), key=lambda kv: -kv[1]):
        pct = val / d["shape_total"]
        bar = "█" * round(pct * 24)
        amount = f"~${_fmt(val)}" if d["billing_mode"] == "api" else f"~{_fmt(val)} tok"
        print(f"    {name:24} {pct:5.0%}  {bar}  {amount}")
    if d["drivers"]:
        print("\n  avoidable drivers:")
        for name, detail in d["drivers"]:
            print(f"    • {name}: {detail}")
    print(f"\n  → {d['headline']}")
    print("\n  savings decision:")
    for line in render_savings_card(card_for_session(conn, tid, routing=routing), indent="    "):
        print(line)
    print()
