#!/usr/bin/env python3
"""MR Token MVP — Layer 2 rule engine.

Pure functions: each rule takes SQLite data, returns list of recommendation dicts.
Nothing here calls an LLM. Writes to the recommendation table.

Rules (MVP):
  repeated_context   — duplicate context blocks re-sent across calls
  huge_tool_output   — single tool result dwarfing useful output
  retry_loop         — temporally clustered tool errors (NOT session-wide count)
  fresh_handoff      — headline recommendation: start fresh with a handoff summary
  low_cache          — cache hit ratio low despite enough calls to build a cache
"""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone


HUGE_TOOL_CHARS = 40_000      # ~10k tokens at 4 chars/tok (default / NULL profile)
REPEATED_WASTE_WARN = 2_000   # tokens wasted by duplicate blocks → warn
REPEATED_WASTE_HIGH = 20_000  # → high
LOW_CACHE_RATIO = 0.40        # below this after N calls → flag
LOW_CACHE_MIN_CALLS = 5       # need at least this many calls before flagging
RETRY_CLUSTER_ERRORS = 3      # ≥ this many errors within window → retry_loop
RETRY_CLUSTER_WINDOW = 8      # consecutive model_calls in which errors cluster
HANDOFF_INPUT_GROWTH = 1.5    # final-quarter avg input_tokens vs first-quarter → signal
HANDOFF_MIN_CALLS = 8         # don't recommend handoff on tiny sessions

# Profile-aware thresholds (TTO Eco Mode methodology): a 20k-token Read is
# normal in `research` but wasteful in `benchmark`. NULL/unknown profile → default.
PROFILE_THRESHOLDS = {
    "research":  {"huge_tool_chars": 80_000, "low_cache_ratio": 0.25},
    "code":      {"huge_tool_chars": 40_000, "low_cache_ratio": 0.40},
    "agent":     {"huge_tool_chars": 40_000, "low_cache_ratio": 0.35},
    "benchmark": {"huge_tool_chars": 24_000, "low_cache_ratio": 0.40},
}
DEFAULT_THRESHOLDS = {"huge_tool_chars": HUGE_TOOL_CHARS, "low_cache_ratio": LOW_CACHE_RATIO}


def _thresholds(conn, tid: int) -> tuple[dict, "str | None"]:
    """Return (thresholds, profile) for a trace. NULL profile → defaults."""
    try:
        row = conn.execute("SELECT profile FROM trace WHERE id=?", (tid,)).fetchone()
        profile = row[0] if row else None
    except sqlite3.OperationalError:
        profile = None  # pre-migration DB without profile column
    t = dict(DEFAULT_THRESHOLDS)
    t.update(PROFILE_THRESHOLDS.get(profile, {}))
    return t, profile
HANDOFF_CACHE_DECAY = 0.20    # cache_ratio drop across halves → signal


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rec(rule, severity, message, evidence=None, savings=None) -> dict:
    return {"rule": rule, "severity": severity, "message": message,
            "evidence_json": json.dumps(evidence) if evidence else None,
            "est_savings_tokens": savings}


# ── individual rules (each returns list[dict]) ────────────────────────────────

def rule_repeated_context(conn, tid: int) -> list:
    rows = conn.execute("""
        SELECT block_type, repeat_count, token_count FROM context_block
        WHERE trace_id=? AND repeat_count>1
    """, (tid,)).fetchall()
    if not rows:
        return []
    waste = sum((r - 1) * (t or 0) for _, r, t in rows)
    if waste < REPEATED_WASTE_WARN:
        return []
    sev = "high" if waste >= REPEATED_WASTE_HIGH else "warn"
    ev = {"wasted_tokens_est": waste, "duplicate_blocks": len(rows),
          "worst": [{"type": bt, "repeat": r, "tok": t}
                    for bt, r, t in sorted(rows, key=lambda x: -(x[1]-1)*(x[2] or 0))[:3]]}
    return [_rec("repeated_context", sev,
                 f"~{waste:,} tokens re-sent in duplicate context blocks. "
                 "Consider compacting or summarising repeated sections before each call.",
                 ev, waste)]


def rule_huge_tool_output(conn, tid: int) -> list:
    thresholds, profile = _thresholds(conn, tid)
    limit = thresholds["huge_tool_chars"]
    rows = conn.execute("""
        SELECT tool_name, output_chars, tool_use_id FROM tool_call
        WHERE trace_id=? AND output_chars>? ORDER BY output_chars DESC
    """, (tid, limit)).fetchall()
    if not rows:
        return []
    prof_note = f" (threshold for '{profile}' profile)" if profile else ""
    recs = []
    for name, oc, tuid in rows:
        tok = oc // 4
        recs.append(_rec("huge_tool_output", "warn",
                         f"Tool '{name}' returned ~{tok:,} tok{prof_note}. "
                         "Write large outputs to disk and pass only a compact summary to the model.",
                         {"tool_use_id": tuid, "output_chars": oc, "output_tokens_est": tok,
                          "profile": profile, "threshold_chars": limit},
                         max(0, tok - 2000)))
    return recs


def rule_retry_loop(conn, tid: int) -> list:
    """Temporal cluster: find model_call windows with ≥ RETRY_CLUSTER_ERRORS tool errors."""
    # Pull all tool calls ordered by started_at (or rowid as proxy)
    rows = conn.execute("""
        SELECT tc.tool_name, tc.is_error, tc.model_call_id, mc.timestamp
        FROM tool_call tc
        LEFT JOIN model_call mc ON mc.id = tc.model_call_id
        WHERE tc.trace_id=?
        ORDER BY COALESCE(tc.started_at, mc.timestamp) ASC, tc.id ASC
    """, (tid,)).fetchall()
    if not rows:
        return []
    # sliding window over model_call_ids (cluster per window)
    window_size = RETRY_CLUSTER_WINDOW
    # group by model_call_id sequence
    mc_ids = []
    mc_map: dict = {}   # mc_id -> list of (tool_name, is_error)
    for tname, is_err, mc_id, ts in rows:
        if mc_id not in mc_map:
            mc_ids.append(mc_id)
            mc_map[mc_id] = []
        mc_map[mc_id].append((tname, is_err))
    recs = []
    seen_mc_ids = set()   # entire window marked seen after firing → no overlapping re-detection
    for i in range(len(mc_ids)):
        window = mc_ids[i:i + window_size]
        if window[0] in seen_mc_ids:
            continue
        errors = [(tname, mcid) for mcid in window for tname, is_err in mc_map[mcid] if is_err]
        if len(errors) >= RETRY_CLUSTER_ERRORS:
            seen_mc_ids.update(window)  # skip the whole window forward
            tools = list({t for t, _ in errors})
            distinct_calls = len({mcid for _, mcid in errors})
            if distinct_calls == 1:
                msg = (f"{len(errors)} tool errors all within one model call "
                       f"({', '.join(tools)}). Mass tool failure — likely a bad "
                       "context state or permission error causing all tools to fail at once.")
            else:
                msg = (f"{len(errors)} tool errors across {distinct_calls} consecutive model calls "
                       f"({', '.join(tools)}). Likely a retry loop — check error handling or "
                       "reduce context before retrying.")
            recs.append(_rec("retry_loop", "high", msg,
                             {"error_count": len(errors), "distinct_calls": distinct_calls,
                              "tools": tools, "first_mc_id": errors[0][1] if errors else window[0]}))
    return recs


def rule_low_cache(conn, tid: int) -> list:
    mc = conn.execute("""
        SELECT COUNT(*), SUM(input_tokens), SUM(cache_read_input_tokens),
               SUM(cache_creation_input_tokens)
        FROM model_call WHERE trace_id=?
    """, (tid,)).fetchone()
    calls, inp, cr, cw = (x or 0 for x in mc)
    if calls < LOW_CACHE_MIN_CALLS:
        return []
    total_in = (inp or 0) + (cw or 0) + (cr or 0)
    if not total_in:
        return []
    thresholds, profile = _thresholds(conn, tid)
    floor = thresholds["low_cache_ratio"]
    ratio = (cr or 0) / total_in
    if ratio >= floor:
        return []
    prof_note = f" (expected ≥{floor:.0%} for '{profile}' profile)" if profile else ""
    return [_rec("low_cache", "info",
                 f"Cache hit ratio is {ratio:.0%} across {calls} calls{prof_note}. "
                 "Ensure large, stable context (system prompt, tool schemas, retrieved docs) "
                 "is in cache-eligible positions.",
                 {"cache_hit_ratio": round(ratio, 3), "calls": calls, "cache_read": cr,
                  "total_input_side": total_in, "profile": profile})]


def rule_fresh_handoff(conn, tid: int) -> list:
    """Headline recommendation: evidence-based, fires only when multiple signals agree."""
    mc_rows = conn.execute("""
        SELECT input_tokens, cache_read_input_tokens, cache_creation_input_tokens,
               output_tokens, is_sidechain, stop_reason, timestamp
        FROM model_call WHERE trace_id=? ORDER BY timestamp ASC
    """, (tid,)).fetchall()
    if len(mc_rows) < HANDOFF_MIN_CALLS:
        return []

    def totals(rows):
        inp = sum(r[0] or 0 for r in rows)
        cr  = sum(r[1] or 0 for r in rows)
        cw  = sum(r[2] or 0 for r in rows)
        total_in = inp + cr + cw
        ratio = cr / total_in if total_in else 0
        return inp, ratio

    n = len(mc_rows)
    q = max(1, n // 4)
    inp_first, ratio_first = totals(mc_rows[:q])
    inp_last,  ratio_last  = totals(mc_rows[-q:])

    signals = []
    # 1. input token growth (context expanding)
    if inp_first and inp_last / inp_first >= HANDOFF_INPUT_GROWTH:
        signals.append(f"input tokens grew {inp_last/inp_first:.1f}× from first to last quarter")
    # 2. cache ratio decay (fresh tokens dominating)
    if ratio_first - ratio_last >= HANDOFF_CACHE_DECAY:
        signals.append(f"cache hit fell {ratio_first:.0%} → {ratio_last:.0%} (context churning)")
    # 3. retry errors in the second half
    late_cutoff = mc_rows[n // 2][6]
    errs_late = conn.execute("""
        SELECT COUNT(*) FROM tool_call tc
        LEFT JOIN model_call mc ON mc.id=tc.model_call_id
        WHERE tc.trace_id=? AND tc.is_error=1 AND mc.timestamp >= ?
    """, (tid, late_cutoff)).fetchone()[0] or 0
    if errs_late >= 3:
        signals.append(f"{errs_late} tool errors in second half — stale context may be compounding")
    # 4. raw conversation depth
    if n >= 30:
        signals.append(f"{n} model calls — conversation depth is high")

    if len(signals) < 2:
        return []   # require at least 2 signals before firing

    # estimate savings: drop the repeated/stale portion of cached input
    waste_row = conn.execute("""
        SELECT SUM((repeat_count-1)*token_count) FROM context_block
        WHERE trace_id=? AND repeat_count>1
    """, (tid,)).fetchone()[0] or 0

    return [_rec("fresh_handoff", "high",
                 "Starting a fresh session with a compact handoff summary is likely more efficient "
                 "than continuing this conversation. Summarise: current goal, key decisions, last "
                 "known state, and any files that changed.",
                 {"signals": signals, "conversation_depth": n,
                  "input_growth_ratio": round(inp_last / inp_first, 2) if inp_first else None,
                  "cache_ratio_first_quarter": round(ratio_first, 3),
                  "cache_ratio_last_quarter": round(ratio_last, 3),
                  "late_errors": errs_late},
                 waste_row or None)]


# ── engine ────────────────────────────────────────────────────────────────────

ALL_RULES = [
    rule_repeated_context,
    rule_huge_tool_output,
    rule_retry_loop,
    rule_low_cache,
    rule_fresh_handoff,
]


def run_rules(conn: sqlite3.Connection, tid: int) -> list[dict]:
    """Run all rules for trace_id tid. Returns fired recommendations."""
    fired = []
    for rule_fn in ALL_RULES:
        try:
            fired.extend(rule_fn(conn, tid))
        except Exception as e:
            name = rule_fn.__name__.replace("rule_", "")
            fired.append(_rec(name, "info", f"Rule error (skipped): {e}"))
    return fired


def write_recommendations(conn: sqlite3.Connection, tid: int, recs: list[dict]):
    conn.execute("DELETE FROM recommendation WHERE trace_id=?", (tid,))
    ts = now_iso()
    for r in recs:
        conn.execute("""INSERT INTO recommendation(trace_id,rule,severity,message,evidence_json,
            est_savings_tokens,created_at) VALUES(?,?,?,?,?,?,?)""",
            (tid, r["rule"], r["severity"], r["message"],
             r["evidence_json"], r["est_savings_tokens"], ts))
    conn.commit()


def analyse(conn: sqlite3.Connection, tid: int) -> list[dict]:
    """Run rules + persist. Returns recommendation dicts."""
    recs = run_rules(conn, tid)
    write_recommendations(conn, tid, recs)
    return recs
