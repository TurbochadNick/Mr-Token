#!/usr/bin/env python3
"""MR Token — internal feedback & observability (ROADMAP 5D).

Two halves of the same loop, both metadata-only:

  explain  — decode a session's fired recommendations + their evidence_json into
             readable "what triggered it" lines, so a HUD signal like
             "⚠ huge output" is inspectable, not opaque.
  feedback — record a human verdict (right / wrong / unsure) on a fired rule, and
             summarise per-rule LABELLED precision — the real-usage upgrade to
             validate's automated corroboration proxy.
"""
from __future__ import annotations
import json, sqlite3

from mrtoken.ingest import now_iso

VERDICTS = ("right", "wrong", "unsure")

# Which evidence fields matter most, per rule — shown first when explaining.
_KEY_EVIDENCE = {
    "huge_tool_output": ["count", "total_tokens_est", "offenders"],
    "retry_loop": ["error_count", "distinct_calls"],
    "fresh_handoff": ["signals", "conversation_depth", "input_growth_ratio"],
    "repeated_context": ["wasted_tokens_est", "duplicate_blocks"],
    "low_cache": ["calls", "cache_hit_ratio"],
    "re_read_loop": ["redundant_reads", "wasted_tokens_est", "by_tool"],
    "step_runaway": ["model_calls", "tool_calls"],
    "context_rot": ["peak_carry_tokens", "cache_ratio_first", "cache_ratio_second", "re_reads"],
}


def _fmt_val(v) -> str:
    if isinstance(v, list):
        return f"[{len(v)} item(s)] " + ", ".join(
            (json.dumps(x) if not isinstance(x, dict) else
             "{" + ", ".join(f"{k}={x[k]}" for k in list(x)[:3]) + "}") for x in v[:2])
    return str(v)


def explain_session(conn: sqlite3.Connection, prefix: str) -> list[dict]:
    """Return each fired recommendation for the session with decoded evidence."""
    row = conn.execute(
        "SELECT id, session_id FROM trace WHERE session_id LIKE ? ORDER BY started_at DESC LIMIT 1",
        (prefix + "%",)).fetchone()
    if not row:
        return []
    tid, sid = row
    recs = conn.execute(
        "SELECT rule, severity, message, evidence_json, est_savings_tokens "
        "FROM recommendation WHERE trace_id=? ORDER BY "
        "CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END", (tid,)).fetchall()
    out = []
    for rule, sev, msg, evj, savings in recs:
        try:
            ev = json.loads(evj) if evj else {}
        except Exception:
            ev = {}
        keys = _KEY_EVIDENCE.get(rule, list(ev))
        evidence = [(k, _fmt_val(ev[k])) for k in keys if k in ev]
        out.append({"rule": rule, "severity": sev, "message": msg,
                    "est_savings_tokens": savings, "session_id": sid,
                    "trace_id": tid, "evidence": evidence})
    return out


def print_explain(conn: sqlite3.Connection, prefix: str) -> None:
    rows = explain_session(conn, prefix)
    print(f"\n{'─'*64}")
    print("  MR Token — explain: why each signal fired")
    print(f"{'─'*64}")
    if not rows:
        print("  no session match, or no recommendations fired.\n"); return
    pref = {"high": "[!]", "warn": "[~]"}
    for r in rows:
        save = f"  · ~{r['est_savings_tokens']:,} tok addressable" if r["est_savings_tokens"] else ""
        print(f"\n  {pref.get(r['severity'], '[i]')} {r['rule']} ({r['severity']}){save}")
        for k, v in r["evidence"]:
            print(f"        {k}: {v}")
    print(f"\n  Mark a verdict:  mrtoken-transcript feedback {rows[0]['session_id'][:8]} "
          f"<rule> right|wrong [--note ...]")
    print(f"{'─'*64}\n")


def record_feedback(conn: sqlite3.Connection, prefix: str, rule: str,
                    verdict: str, note: str | None = None) -> dict:
    """Persist a verdict on a fired rule. Raises ValueError on a bad verdict."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    row = conn.execute(
        "SELECT id, session_id FROM trace WHERE session_id LIKE ? ORDER BY started_at DESC LIMIT 1",
        (prefix + "%",)).fetchone()
    tid, sid = (row[0], row[1]) if row else (None, prefix)
    conn.execute("INSERT INTO feedback(trace_id,session_id,rule,verdict,note,created_at) "
                 "VALUES(?,?,?,?,?,?)", (tid, sid, rule, verdict, note, now_iso()))
    conn.commit()
    return {"session_id": sid, "rule": rule, "verdict": verdict}


def feedback_summary(conn: sqlite3.Connection) -> dict:
    """Per-rule labelled precision from real verdicts (right / wrong / unsure)."""
    rows = conn.execute(
        "SELECT rule, verdict, COUNT(*) FROM feedback GROUP BY rule, verdict").fetchall()
    per_rule: dict[str, dict] = {}
    for rule, verdict, n in rows:
        s = per_rule.setdefault(rule, {"right": 0, "wrong": 0, "unsure": 0})
        s[verdict] = s.get(verdict, 0) + n
    for s in per_rule.values():
        decided = s["right"] + s["wrong"]
        s["labelled_precision"] = round(s["right"] / decided, 2) if decided else None
    return per_rule


def print_feedback_summary(conn: sqlite3.Connection) -> None:
    per_rule = feedback_summary(conn)
    print(f"\n{'─'*60}")
    print("  MR Token — feedback (LABELLED precision from real verdicts)")
    print(f"{'─'*60}")
    if not per_rule:
        print("  no feedback yet — run `mrtoken-transcript explain <session>`, then "
              "`feedback <session> <rule> right|wrong`.\n"); return
    print(f"  {'RULE':22} {'RIGHT':>5} {'WRONG':>5} {'UNSURE':>6} {'PRECISION':>10}")
    for rule, s in sorted(per_rule.items(), key=lambda kv: -(kv[1]['right'] + kv[1]['wrong'])):
        p = f"{s['labelled_precision']:.0%}" if s["labelled_precision"] is not None else "  —"
        print(f"  {rule:22} {s['right']:>5} {s['wrong']:>5} {s['unsure']:>6} {p:>10}")
    print(f"{'─'*60}\n")
