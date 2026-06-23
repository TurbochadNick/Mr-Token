#!/usr/bin/env python3
"""MR Token — recommendation corroboration harness.

We have no human-labeled ground truth, so this does NOT claim "% correct".
Instead, for each fired recommendation it checks whether INDEPENDENT evidence
in the trace corroborates the advice, and assigns a verdict:

  strong — independent evidence backs the recommendation (likely a true positive)
  weak   — fired, but corroborating evidence is thin (candidate false positive)
  moot   — the condition existed but acting on the advice wouldn't have helped
           (e.g. the session ended right after a "start fresh" signal)

Aggregated per rule, the strong-fraction is a defensible PRECISION PROXY and
points at which thresholds need tuning. Pure functions, no AI.
"""
from __future__ import annotations
import json, sqlite3


def _ev(rec) -> dict:
    try:
        return json.loads(rec["evidence_json"]) if rec["evidence_json"] else {}
    except Exception:
        return {}


def _calls_after(conn, tid, ts) -> int:
    if not ts:
        return 0
    return conn.execute(
        "SELECT COUNT(*) FROM model_call WHERE trace_id=? AND timestamp > ?", (tid, ts)
    ).fetchone()[0] or 0


# ── per-rule corroboration ────────────────────────────────────────────────────

def _check_huge_tool_output(conn, tid, ev) -> tuple[str, str]:
    # A huge output only wastes tokens if it PERSISTS in context — i.e. many
    # model calls follow it. If it landed near the end, the advice is moot.
    # The rule collapses possibly-many oversized outputs into ONE rec and records
    # them under `offenders[]` (there is no top-level tool_use_id). Corroborate on
    # the WORST-persisting offender: the rec is justified if ANY big output carried.
    offenders = ev.get("offenders") or []
    if not offenders and ev.get("tool_use_id"):  # tolerate an older single-id shape
        offenders = [{"tool_use_id": ev["tool_use_id"]}]
    best_after = 0
    for off in offenders:
        tuid = off.get("tool_use_id")
        if not tuid:
            continue
        row = conn.execute("""
            SELECT mc.timestamp FROM tool_call tc
            LEFT JOIN model_call mc ON mc.id = tc.model_call_id
            WHERE tc.trace_id=? AND tc.tool_use_id=?""", (tid, tuid)).fetchone()
        best_after = max(best_after, _calls_after(conn, tid, row[0] if row else None))
    if best_after < 3:
        return "moot", f"largest output landed near session end ({best_after} calls after) — not carried"
    if best_after >= 10:
        return "strong", f"oversized output persisted in context for {best_after} subsequent calls"
    return "weak", f"only {best_after} calls carried the output"


def _check_retry_loop(conn, tid, ev) -> tuple[str, str]:
    distinct = ev.get("distinct_calls", 0)
    n = ev.get("error_count", 0)
    if distinct >= 2:
        return "strong", f"{n} errors across {distinct} consecutive calls — genuine loop"
    return "weak", f"{n} errors in a single call — mass tool failure, not a retry loop"


def _check_fresh_handoff(conn, tid, ev) -> tuple[str, str]:
    rows = conn.execute("""
        SELECT input_tokens, output_tokens, cache_read_input_tokens,
               cache_creation_input_tokens, est_cost_usd, timestamp
        FROM model_call WHERE trace_id=? ORDER BY timestamp ASC""", (tid,)).fetchall()
    n = len(rows)
    if n < 4:
        return "weak", "too few calls to corroborate"
    mid = n // 2
    cost1 = sum((r[4] or 0) for r in rows[:mid])
    cost2 = sum((r[4] or 0) for r in rows[mid:])
    after_mid = n - mid
    if after_mid < 10:
        return "moot", f"session ended soon after signals ({after_mid} calls past midpoint)"
    if cost2 > cost1:
        return "strong", (f"2nd half cost ${cost2:,.2f} > 1st half ${cost1:,.2f} over "
                          f"{after_mid} calls — continuing was expensive")
    return "weak", f"2nd-half cost (${cost2:,.2f}) did not exceed 1st half (${cost1:,.2f})"


def _check_repeated_context(conn, tid, ev) -> tuple[str, str]:
    waste = ev.get("wasted_tokens_est", 0)
    if waste >= 20_000:
        return "strong", f"~{waste:,} tokens re-sent — substantial"
    if waste >= 5_000:
        return "weak", f"~{waste:,} tokens re-sent — moderate"
    return "weak", f"only ~{waste:,} tokens re-sent — near the firing floor"


def _check_low_cache(conn, tid, ev) -> tuple[str, str]:
    calls = ev.get("calls", 0)
    ratio = ev.get("cache_hit_ratio", 0)
    if calls >= 10:
        return "strong", f"sustained {ratio:.0%} cache over {calls} calls"
    return "weak", f"low cache but only {calls} calls — may be early-session"


def _check_step_runaway(conn, tid, ev) -> tuple[str, str]:
    # A high step count is corroborated when the steps show CHURN (tool errors +
    # repeated reads) rather than steady progress — independent evidence that the
    # run was inefficient, not just a genuinely large task.
    n = ev.get("model_calls", 0)
    errs = conn.execute(
        "SELECT COUNT(*) FROM tool_call WHERE trace_id=? AND is_error=1", (tid,)).fetchone()[0]
    rereads = conn.execute("""
        SELECT COALESCE(SUM(c - 1), 0) FROM (
          SELECT COUNT(*) c FROM tool_call
          WHERE trace_id=? AND input_hash IS NOT NULL
          GROUP BY LOWER(tool_name), input_hash HAVING c > 1)""", (tid,)).fetchone()[0]
    churn = (errs or 0) + (rereads or 0)
    if churn >= 5:
        return "strong", f"{n} steps with {errs} tool errors + {rereads} re-reads — churn, not steady progress"
    return "weak", f"{n} steps but little churn ({errs} errors, {rereads} re-reads) — may be a genuinely large task"


_CHECKERS = {
    "huge_tool_output": _check_huge_tool_output,
    "retry_loop": _check_retry_loop,
    "fresh_handoff": _check_fresh_handoff,
    "repeated_context": _check_repeated_context,
    "low_cache": _check_low_cache,
    "step_runaway": _check_step_runaway,
}


def validate_db(conn: sqlite3.Connection) -> dict:
    """Corroborate every recommendation in the DB. Returns an aggregate report."""
    conn.row_factory = sqlite3.Row
    recs = conn.execute(
        "SELECT id, trace_id, rule, severity, evidence_json FROM recommendation"
    ).fetchall()

    per_rule: dict[str, dict] = {}
    for rec in recs:
        rule = rec["rule"]
        checker = _CHECKERS.get(rule)
        if not checker:
            continue
        try:
            verdict, reason = checker(conn, rec["trace_id"], _ev(rec))
        except Exception as e:
            verdict, reason = "weak", f"check error: {e}"
        slot = per_rule.setdefault(
            rule, {"fired": 0, "strong": 0, "weak": 0, "moot": 0, "examples": []})
        slot["fired"] += 1
        slot[verdict] += 1
        if len(slot["examples"]) < 2:
            slot["examples"].append({"verdict": verdict, "reason": reason})

    # tuning suggestions where corroboration is thin
    for rule, s in per_rule.items():
        actionable = s["fired"] - s["moot"]
        s["precision_proxy"] = round(s["strong"] / actionable, 2) if actionable else None
        noise = (s["weak"] + s["moot"]) / s["fired"] if s["fired"] else 0
        if noise > 0.30:
            s["suggestion"] = "raise threshold / add a corroborating signal — >30% thin or moot"
        else:
            s["suggestion"] = "thresholds look well-calibrated"
    return {"schema": "mrtoken.validation.v1", "rules": per_rule}


def print_report(report: dict) -> None:
    print(f"\n{'─'*64}")
    print("  MR Token — recommendation corroboration  (precision PROXY, not labels)")
    print(f"{'─'*64}")
    print(f"  {'RULE':22} {'FIRED':>5} {'STRONG':>6} {'WEAK':>5} {'MOOT':>5} {'PROXY':>6}")
    print(f"  {'─'*22} {'─'*5} {'─'*6} {'─'*5} {'─'*5} {'─'*6}")
    rules = report["rules"]
    if not rules:
        print("  no recommendations to validate (ingest + run rules first)\n")
        return
    for rule, s in sorted(rules.items(), key=lambda kv: -kv[1]["fired"]):
        proxy = f"{s['precision_proxy']:.0%}" if s["precision_proxy"] is not None else "  —"
        print(f"  {rule:22} {s['fired']:>5} {s['strong']:>6} {s['weak']:>5} {s['moot']:>5} {proxy:>6}")
    print()
    for rule, s in sorted(rules.items(), key=lambda kv: -kv[1]["fired"]):
        print(f"  {rule}: {s['suggestion']}")
        for ex in s["examples"]:
            print(f"      [{ex['verdict']}] {ex['reason']}")
    print(f"{'─'*64}\n")
