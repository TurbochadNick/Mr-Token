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
from datetime import datetime, timedelta, timezone

from mrtoken.pricing import COST_CAVEAT

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


# ── before/after measurement (ROADMAP 2.1) ─────────────────────────────────────
# Design C (headline) + B (corroboration). We cannot run a controlled A/B on
# observed sessions, so neither number is causal proof. C is a counterfactual
# PROJECTION (no behaviour assumed, no selection bias); B is an OBSERVATIONAL
# split (subject to selection bias). See docs/ROI-EXPERIMENT.md.

def _corpus_lean_per_call(conn: sqlite3.Connection, k: int = 5) -> tuple[float, int]:
    """Mean est cost over the opening `k` calls of each session — a proxy for a
    lean, cache-cold restart. Returns (per_call_usd, n_sessions sampled)."""
    row = conn.execute(f"""
        WITH ranked AS (
          SELECT trace_id, est_cost_usd,
                 ROW_NUMBER() OVER (PARTITION BY trace_id ORDER BY timestamp) AS rn
          FROM model_call)
        SELECT COALESCE(AVG(est_cost_usd), 0), COUNT(DISTINCT trace_id)
        FROM ranked WHERE rn <= ?""", (k,)).fetchone()
    return float(row[0] or 0.0), int(row[1] or 0)


# B's "acted" signal: a separate fresh session started in the same project within
# this many minutes of the fired session's end. Judgement knob
# (GOALS/roi-cross-session-linkage.md): tight enough that the restart plausibly
# answers the nudge, loose enough to survive a coffee break.
LINKAGE_WINDOW_MIN = 30


def _ts(value: str | None):
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _acted_by_linkage(conn: sqlite3.Connection, tid: int) -> bool:
    """True when a separate top-level session (not a subagent transcript) started
    in the same project within LINKAGE_WINDOW_MIN of this session's end."""
    row = conn.execute(
        "SELECT session_id, project_path, ended_at FROM trace WHERE id=?", (tid,)).fetchone()
    if not row:
        return False
    sid, project, ended = row
    if not project:
        return False
    if not ended:  # older ingests may lack ended_at; fall back to the last call
        ended = conn.execute(
            "SELECT MAX(timestamp) FROM model_call WHERE trace_id=?", (tid,)).fetchone()[0]
    t_end = _ts(ended)
    if not t_end:
        return False
    t_max = t_end + timedelta(minutes=LINKAGE_WINDOW_MIN)
    for (started,) in conn.execute(
            "SELECT started_at FROM trace WHERE project_path=? AND session_id<>? "
            "AND parent_session_id IS NULL AND started_at IS NOT NULL", (project, sid)):
        t_start = _ts(started)
        if t_start and t_end < t_start <= t_max:
            return True
    return False


def _session_late_per_call(conn: sqlite3.Connection, tid: int):
    """Mean est cost/call over a session's 2nd half (proxy for post-fire burn).
    Returns (per_call_usd, calls_after_midpoint) or None if too few calls."""
    rows = conn.execute(
        "SELECT est_cost_usd FROM model_call WHERE trace_id=? ORDER BY timestamp", (tid,)
    ).fetchall()
    n = len(rows)
    if n < 4:
        return None
    mid = n // 2
    late = [(r[0] or 0) for r in rows[mid:]]
    return (sum(late) / len(late), n - mid)


def roi_measure(conn: sqlite3.Connection, horizon: int = 10, k: int = 5) -> dict:
    """C: project the saving of acting on a fresh_handoff over the next `horizon`
    calls (late-stage burn minus a lean-restart baseline). B: split fired sessions
    into acted (a separate fresh session started in the same project within
    LINKAGE_WINDOW_MIN of the fired session's end — cross-session linkage) vs
    ignored, and compare their late-stage per-call cost."""
    lean, lean_n = _corpus_lean_per_call(conn, k)
    fired = [r[0] for r in conn.execute(
        "SELECT DISTINCT trace_id FROM recommendation WHERE rule='fresh_handoff'")]
    proj = {"horizon": horizon, "lean_per_call_usd": round(lean, 6),
            "lean_baseline_sessions": lean_n, "n_sessions": 0,
            "projected_saving_usd": 0.0}
    acted = {"n": 0, "sum": 0.0}
    ignored = {"n": 0, "sum": 0.0}
    for tid in fired:
        lp = _session_late_per_call(conn, tid)
        if not lp:
            continue
        late_per_call, _after = lp
        proj["n_sessions"] += 1
        proj["projected_saving_usd"] += max(0.0, late_per_call - lean) * horizon
        bucket = acted if _acted_by_linkage(conn, tid) else ignored
        bucket["n"] += 1
        bucket["sum"] += late_per_call
    proj["projected_saving_usd"] = round(proj["projected_saving_usd"], 2)

    def mean(b):
        return round(b["sum"] / b["n"], 6) if b["n"] else None
    return {"projection": proj,
            "cohort": {"acted":   {"n": acted["n"],   "late_per_call_usd": mean(acted)},
                       "ignored": {"n": ignored["n"], "late_per_call_usd": mean(ignored)}}}


def print_roi_measure(conn: sqlite3.Connection, horizon: int = 10) -> None:
    m = roi_measure(conn, horizon)
    p, c = m["projection"], m["cohort"]
    print(f"\n  MR Token — fresh_handoff before/after  ⚠ ESTIMATE + OBSERVATIONAL, not a controlled trial")
    print(f"  {'─'*64}")
    if p["n_sessions"] == 0:
        print("  no fresh_handoff fired on a long-enough session yet — ingest/backfill more.\n")
        return
    print(f"  C · counterfactual projection (no behaviour assumed, no selection bias):")
    print(f"    lean-restart baseline ~${p['lean_per_call_usd']:,.4f}/call "
          f"(opening {5} calls across {p['lean_baseline_sessions']} sessions)")
    print(f"    over {p['n_sessions']} fired session(s), continuing ~{horizon} more calls at late-stage")
    print(f"    burn vs a lean restart projects ~${p['projected_saving_usd']:,.2f} saved (marginal, not forever)")
    print(f"\n  B · acted vs ignored (OBSERVATIONAL — selection bias, not causal):")
    a, ig = c["acted"], c["ignored"]
    def ppc(x): return f"${x:,.4f}/call" if x is not None else "—"
    print(f"    acted   (fresh same-project session ≤{LINKAGE_WINDOW_MIN}m after end): n={a['n']:<3} late cost {ppc(a['late_per_call_usd'])}")
    print(f"    ignored (no linked follow-on session):              n={ig['n']:<3} late cost {ppc(ig['late_per_call_usd'])}")
    if a["late_per_call_usd"] and ig["late_per_call_usd"]:
        delta = ig["late_per_call_usd"] - a["late_per_call_usd"]
        print(f"    → ignored sessions ran {ppc(abs(delta))} {'higher' if delta>0 else 'lower'} late-stage;")
        if delta > 0:
            print(f"      consistent with carry escalation, but confounded by task choice.")
        else:
            print(f"      i.e. users restarted exactly the costliest sessions — a selection")
            print(f"      effect, not evidence the restart didn't pay.")
    print(f"  {'─'*64}\n")


def print_roi(conn: sqlite3.Connection, prefix: str | None) -> None:
    print(f"\n  MR Token — ROI estimate  ⚠ data-grounded ESTIMATE, not a controlled-trial "
          f"measurement; $ is {COST_CAVEAT}")
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
