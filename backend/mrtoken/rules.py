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
LOW_CACHE_MIN_CALLS = 10      # need a sustained sample (early-session ratios are noisy)
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
    raw_waste = sum((r - 1) * (t or 0) for _, r, t in rows)

    # Cache-aware: prompt caching serves re-sent identical blocks at ~cache_read
    # cost (~10% of input), so most repeated context is NOT real waste on a
    # well-cached session. Discount by the session cache-hit ratio — only the
    # UNCACHED fraction is genuinely re-paid.
    mc = conn.execute("""
        SELECT SUM(input_tokens), SUM(cache_read_input_tokens),
               SUM(cache_creation_input_tokens) FROM model_call WHERE trace_id=?
    """, (tid,)).fetchone()
    inp, cr, cw = (x or 0 for x in mc)
    total_in = inp + cr + cw
    cache_ratio = (cr / total_in) if total_in else 0.0
    effective_waste = int(raw_waste * (1 - cache_ratio))

    if effective_waste < REPEATED_WASTE_WARN:
        return []
    sev = "high" if effective_waste >= REPEATED_WASTE_HIGH else "warn"
    ev = {"wasted_tokens_est": effective_waste, "raw_repeated_tokens": raw_waste,
          "cache_hit_ratio": round(cache_ratio, 3), "duplicate_blocks": len(rows),
          "worst": [{"type": bt, "repeat": r, "tok": t}
                    for bt, r, t in sorted(rows, key=lambda x: -(x[1]-1)*(x[2] or 0))[:3]]}
    cache_note = (f" (after {cache_ratio:.0%} cache discount; {raw_waste:,} raw)"
                  if cache_ratio > 0.05 else "")
    return [_rec("repeated_context", sev,
                 f"~{effective_waste:,} uncached tokens re-sent in duplicate context "
                 f"blocks{cache_note}. Consider compacting or summarising repeated sections.",
                 ev, effective_waste)]


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
    n = len(rows)
    total_tok = sum(oc // 4 for _, oc, _ in rows)
    # ONE collapsed rec, not one per output (a single session can have 30+ and
    # spamming near-identical warnings buries the signal)
    if n == 1:
        name, oc, _ = rows[0]
        msg = (f"Tool '{name}' returned ~{oc//4:,} tok{prof_note}. "
               "Write large outputs to disk and pass only a compact summary.")
    else:
        top = ", ".join(f"{nm} ~{oc//4:,} tok" for nm, oc, _ in rows[:3])
        more = f" (+{n - 3} more)" if n > 3 else ""
        msg = (f"{n} oversized tool outputs{prof_note}, ~{total_tok:,} tok total "
               f"(biggest: {top}{more}). Each is re-paid into context on every later "
               "call — write large outputs to disk and pass compact summaries.")
    return [_rec("huge_tool_output", "warn", msg,
                 {"count": n, "total_tokens_est": total_tok, "profile": profile,
                  "threshold_chars": limit,
                  "offenders": [{"tool": nm, "output_chars": oc, "tool_use_id": ti}
                                for nm, oc, ti in rows[:10]]},
                 max(0, total_tok - 2000 * n))]


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

    # Split signals into SIZE (the session is merely big) vs TROUBLE (real
    # degradation). A well-cached long session does NOT benefit from a handoff —
    # handoff resets the cheap cached prefix (the project's own ROI finding). The
    # old guard fired on input-growth + depth, which BOTH just mean "big", so it
    # cried wolf on healthy productive sessions. Now require real trouble.
    size_signals, trouble_signals = [], []
    if inp_first and inp_last / inp_first >= HANDOFF_INPUT_GROWTH:
        size_signals.append(f"input tokens grew {inp_last/inp_first:.1f}× from first to last quarter")
    if n >= 30:
        size_signals.append(f"{n} model calls — conversation depth is high")
    if ratio_first - ratio_last >= HANDOFF_CACHE_DECAY:
        trouble_signals.append(f"cache hit fell {ratio_first:.0%} → {ratio_last:.0%} (context churning)")
    late_cutoff = mc_rows[n // 2][6]
    errs_late = conn.execute("""
        SELECT COUNT(*) FROM tool_call tc
        LEFT JOIN model_call mc ON mc.id=tc.model_call_id
        WHERE tc.trace_id=? AND tc.is_error=1 AND mc.timestamp >= ?
    """, (tid, late_cutoff)).fetchone()[0] or 0
    if errs_late >= 3:
        trouble_signals.append(f"{errs_late} tool errors in second half — stale context may be compounding")

    signals = trouble_signals + size_signals
    # need at least one TROUBLE signal (churn/errors) plus corroboration
    if not trouble_signals or len(signals) < 2:
        return []

    # estimate savings: drop the repeated/stale portion of cached input
    waste_row = conn.execute("""
        SELECT SUM((repeat_count-1)*token_count) FROM context_block
        WHERE trace_id=? AND repeat_count>1
    """, (tid,)).fetchone()[0] or 0

    return [_rec("fresh_handoff", "high",
                 "Starting a fresh session with a compact handoff summary is likely more efficient "
                 "than continuing this conversation. Run /mr-handoff (or `mrtoken-transcript handoff`) "
                 "to generate one — goal, key decisions, last state, and changed files.",
                 {"signals": signals, "conversation_depth": n,
                  "input_growth_ratio": round(inp_last / inp_first, 2) if inp_first else None,
                  "cache_ratio_first_quarter": round(ratio_first, 3),
                  "cache_ratio_last_quarter": round(ratio_last, 3),
                  "late_errors": errs_late},
                 waste_row or None)]


# ── engine ────────────────────────────────────────────────────────────────────

RE_READ_TRIGGER = 3          # same read repeated >= this many times = a re-read loop
READ_TOOLS = {"read", "grep", "glob", "notebookread"}


def rule_re_read_loop(conn, tid: int) -> list:
    """Re-reading the same file/target wastes tokens AND bloats context — a top
    dynamic-cost driver (Stanford agent-spend study: same task varies up to 30x by
    re-reads). Detected privacy-cleanly: a repeated read produces the SAME input
    hash, so we count duplicate (tool, input_hash) groups without storing paths."""
    rows = conn.execute("""
        SELECT LOWER(tool_name) name, COUNT(*) c, AVG(COALESCE(output_tokens_est,0)) avg_out
        FROM tool_call WHERE trace_id=? AND input_hash IS NOT NULL
        GROUP BY LOWER(tool_name), input_hash HAVING c >= ?
    """, (tid, RE_READ_TRIGGER)).fetchall()
    hits = [(n, c, a) for n, c, a in rows if n in READ_TOOLS]
    if not hits:
        return []
    redundant = sum(c - 1 for _, c, _ in hits)              # the avoidable re-reads
    wasted = int(sum((c - 1) * (a or 0) for _, c, a in hits))  # re-paid output tokens
    by_tool = {}
    for n, c, _ in hits:
        by_tool[n] = by_tool.get(n, 0) + (c - 1)
    sev = "warn" if wasted >= 2000 else "info"
    return [_rec("re_read_loop", sev,
                 f"{redundant} redundant re-read(s) of the same target "
                 f"(~{wasted:,} tok re-paid into context). Read once and keep the result, "
                 "or read targeted ranges instead of re-reading whole files.",
                 {"redundant_reads": redundant, "wasted_tokens_est": wasted,
                  "by_tool": by_tool, "distinct_targets": len(hits)},
                 wasted or None)]


STEP_RUNAWAY_WARN = 120   # model calls in ONE session — an unusually high step count
STEP_RUNAWAY_HIGH = 250


def rule_step_runaway(conn, tid: int) -> list:
    """An extreme number of steps (model calls) in one session is itself a cost
    driver — the same task can cost far more purely by taking more steps (Stanford
    agent-spend study). Distinct from fresh_handoff (which keys on cost/cache growth):
    this flags raw step-count outliers, where re-planning or a reset usually helps."""
    n = conn.execute("SELECT COUNT(*) FROM model_call WHERE trace_id=?", (tid,)).fetchone()[0]
    if n < STEP_RUNAWAY_WARN:
        return []
    tools = conn.execute("SELECT COUNT(*) FROM tool_call WHERE trace_id=?", (tid,)).fetchone()[0]
    sev = "high" if n >= STEP_RUNAWAY_HIGH else "warn"
    return [_rec("step_runaway", sev,
                 f"{n} model calls in one session ({tools} tool calls) — an unusually high "
                 f"step count. Steps compound token cost; consider /mr-handoff to reset or "
                 f"re-planning the approach so the agent takes fewer, bigger steps.",
                 {"model_calls": n, "tool_calls": tools})]


CONTEXT_ROT_MIN_CALLS = 20      # need enough calls to compare halves
CONTEXT_ROT_CARRY = 100_000     # peak carried context (cache_read) to count as "large"
CONTEXT_ROT_CACHE_DROP = 0.10   # first-half minus second-half cache hit ratio


def rule_context_rot(conn, tid: int) -> list:
    """SOFT quality hint (never high): when a session's context has grown large AND
    its cache efficiency is falling (or re-reads rising), long-context attention can
    degrade ('context rot'). This is a quality risk, not a cost rule — info only, so
    it never crowds out actionable cost signals. Keep it a hint (per the brief)."""
    rows = conn.execute(
        "SELECT input_tokens, cache_read_input_tokens, cache_creation_input_tokens, timestamp "
        "FROM model_call WHERE trace_id=? ORDER BY timestamp", (tid,)).fetchall()
    n = len(rows)
    if n < CONTEXT_ROT_MIN_CALLS:
        return []
    peak_carry = max((r[1] or 0) for r in rows)
    if peak_carry < CONTEXT_ROT_CARRY:
        return []

    def cache_ratio(rs):
        cr = sum(r[1] or 0 for r in rs)
        base = sum((r[0] or 0) + (r[1] or 0) + (r[2] or 0) for r in rs)
        return (cr / base) if base else 0.0

    mid = n // 2
    r1, r2 = cache_ratio(rows[:mid]), cache_ratio(rows[mid:])
    drop = r1 - r2
    rereads = conn.execute("""
        SELECT COALESCE(SUM(c - 1), 0) FROM (
          SELECT COUNT(*) c FROM tool_call
          WHERE trace_id=? AND input_hash IS NOT NULL
          GROUP BY LOWER(tool_name), input_hash HAVING c > 1)""", (tid,)).fetchone()[0] or 0
    if drop < CONTEXT_ROT_CACHE_DROP and rereads < 3:
        return []
    reasons = []
    if drop >= CONTEXT_ROT_CACHE_DROP:
        reasons.append(f"cache efficiency fell {r1:.0%}→{r2:.0%}")
    if rereads >= 3:
        reasons.append(f"{rereads} re-reads")
    return [_rec("context_rot", "info",
                 f"Context has grown large (~{peak_carry:,} tok carried) and {'; '.join(reasons)} — "
                 f"long contexts can degrade output quality ('context rot'). A fresh /mr-handoff "
                 f"keeps the agent sharp. Soft hint — a quality risk, not a cost rule.",
                 {"peak_carry_tokens": peak_carry, "cache_ratio_first": round(r1, 3),
                  "cache_ratio_second": round(r2, 3), "re_reads": rereads, "calls": n})]


ALL_RULES = [
    rule_repeated_context,
    rule_huge_tool_output,
    rule_retry_loop,
    rule_low_cache,
    rule_fresh_handoff,
    rule_re_read_loop,
    rule_step_runaway,
    rule_context_rot,
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
