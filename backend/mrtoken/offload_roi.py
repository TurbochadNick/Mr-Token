#!/usr/bin/env python3
"""Small paired ROI reader for Codex offload smoke tests.

This is not a live runner. It compares two already-ingested sessions:
- ignore: agent continued after a huge output without offload
- follow: agent followed MR Token's offload/summarize guidance

The post-nudge anchor is the first oversized tool output in each session. That is
the deterministic event that causes the HUD/offload advice, and it lets us compare
future token growth without relying on terminal UI text.
"""
from __future__ import annotations
import json
import sqlite3

from mrtoken.rules import HUGE_TOOL_CHARS


def _trace(conn: sqlite3.Connection, prefix: str) -> dict:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, session_id, source FROM trace WHERE session_id LIKE ? ORDER BY started_at DESC",
        (prefix + "%",),
    ).fetchall()
    if not rows:
        raise ValueError(f"no session matches {prefix!r}")
    if len(rows) > 1:
        matches = ", ".join(r["session_id"][:12] for r in rows[:5])
        raise ValueError(f"session prefix {prefix!r} is ambiguous: {matches}")
    return dict(rows[0])


def _anchor(conn: sqlite3.Connection, tid: int, threshold_chars: int) -> dict | None:
    row = conn.execute(
        """
        SELECT tc.tool_name, tc.output_chars, mc.timestamp
        FROM tool_call tc
        LEFT JOIN model_call mc ON mc.id = tc.model_call_id
        WHERE tc.trace_id=? AND COALESCE(tc.output_chars, 0) >= ?
        ORDER BY mc.timestamp ASC, tc.id ASC
        LIMIT 1
        """,
        (tid, threshold_chars),
    ).fetchone()
    if not row:
        return None
    return {"tool_name": row[0], "output_chars": row[1] or 0, "timestamp": row[2]}


def _metrics(conn: sqlite3.Connection, prefix: str, threshold_chars: int) -> dict:
    tr = _trace(conn, prefix)
    tid = tr["id"]
    anchor = _anchor(conn, tid, threshold_chars)
    session_row = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(input_tokens + output_tokens), 0),
               COALESCE(SUM(input_tokens + cache_read_input_tokens + cache_creation_input_tokens), 0),
               COALESCE(SUM(est_cost_usd), 0),
               COALESCE(SUM(output_tokens), 0)
        FROM model_call WHERE trace_id=?
        """,
        (tid,),
    ).fetchone()
    session_tool_row = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN COALESCE(output_chars, 0) >= ? THEN 1 ELSE 0 END), 0)
        FROM tool_call WHERE trace_id=?
        """,
        (threshold_chars, tid),
    ).fetchone()
    where = "trace_id=?"
    params: list = [tid]
    if anchor and anchor["timestamp"]:
        where += " AND timestamp > ?"
        params.append(anchor["timestamp"])

    row = conn.execute(
        f"""
        SELECT COUNT(*),
               COALESCE(SUM(input_tokens + output_tokens), 0),
               COALESCE(SUM(input_tokens + cache_read_input_tokens + cache_creation_input_tokens), 0),
               COALESCE(SUM(est_cost_usd), 0),
               COALESCE(SUM(output_tokens), 0)
        FROM model_call WHERE {where}
        """,
        tuple(params),
    ).fetchone()
    tool_row = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN COALESCE(output_chars, 0) >= ? THEN 1 ELSE 0 END), 0)
        FROM tool_call tc
        LEFT JOIN model_call mc ON mc.id = tc.model_call_id
        WHERE tc.trace_id=? AND (? IS NULL OR mc.timestamp > ?)
        """,
        (threshold_chars, tid, anchor["timestamp"] if anchor else None,
         anchor["timestamp"] if anchor else None),
    ).fetchone()
    rec_rows = conn.execute(
        "SELECT rule, COUNT(*) FROM recommendation WHERE trace_id=? GROUP BY rule",
        (tid,),
    ).fetchall()
    final = conn.execute(
        """
        SELECT input_tokens + cache_read_input_tokens + cache_creation_input_tokens
        FROM model_call WHERE trace_id=? ORDER BY timestamp DESC LIMIT 1
        """,
        (tid,),
    ).fetchone()

    return {
        "session_id": tr["session_id"],
        "source": tr["source"],
        "anchor": anchor,
        "session_model_calls": session_row[0] or 0,
        "session_total_tokens": session_row[1] or 0,
        "session_input_side_tokens": session_row[2] or 0,
        "session_est_cost_usd": round(session_row[3] or 0, 6),
        "session_output_tokens": session_row[4] or 0,
        "session_tool_calls": session_tool_row[0] or 0,
        "session_tool_errors": session_tool_row[1] or 0,
        "session_huge_outputs": session_tool_row[2] or 0,
        "post_model_calls": row[0] or 0,
        "post_total_tokens": row[1] or 0,
        "post_input_side_tokens": row[2] or 0,
        "post_est_cost_usd": round(row[3] or 0, 6),
        "post_output_tokens": row[4] or 0,
        "post_tool_calls": tool_row[0] or 0,
        "post_tool_errors": tool_row[1] or 0,
        "post_huge_outputs": tool_row[2] or 0,
        "final_context_tokens": final[0] if final else None,
        "recommendations": {r[0]: r[1] for r in rec_rows},
    }


def compare_offload_pair(
    conn: sqlite3.Connection,
    ignore_prefix: str,
    follow_prefix: str,
    threshold_chars: int = HUGE_TOOL_CHARS,
    ignore_passed: bool | None = None,
    follow_passed: bool | None = None,
    mode: str = "post-anchor",
) -> dict:
    if mode not in ("post-anchor", "prevention"):
        raise ValueError("mode must be 'post-anchor' or 'prevention'")
    ignore = _metrics(conn, ignore_prefix, threshold_chars)
    follow = _metrics(conn, follow_prefix, threshold_chars)
    prefix = "session" if mode == "prevention" else "post"
    token_key = f"{prefix}_total_tokens"
    cost_key = f"{prefix}_est_cost_usd"
    error_key = f"{prefix}_tool_errors"
    huge_key = f"{prefix}_huge_outputs"
    delta = ignore[token_key] - follow[token_key]
    cost_delta = ignore[cost_key] - follow[cost_key]
    pct = (delta / ignore[token_key]) if ignore[token_key] else None
    quality_known = ignore_passed is not None and follow_passed is not None
    quality_ok = bool(ignore_passed and follow_passed) if quality_known else None
    directional_win = (
        quality_ok is True
        and delta > 0
        and follow[error_key] <= ignore[error_key]
        and follow[huge_key] <= ignore[huge_key]
    )
    return {
        "schema": "mrtoken.offload_roi_pair.v1",
        "mode": mode,
        "threshold_chars": threshold_chars,
        "ignore": ignore,
        "follow": follow,
        "quality": {
            "ignore_passed": ignore_passed,
            "follow_passed": follow_passed,
            "known": quality_known,
            "ok": quality_ok,
        },
        "delta": {
            "tokens_saved": delta,
            "token_reduction_ratio": round(pct, 4) if pct is not None else None,
            "est_cost_saved_usd": round(cost_delta, 6),
            "tool_errors_delta": ignore[error_key] - follow[error_key],
            "huge_outputs_delta": ignore[huge_key] - follow[huge_key],
            "post_total_tokens_saved": ignore["post_total_tokens"] - follow["post_total_tokens"],
            "post_token_reduction_ratio": round(
                (ignore["post_total_tokens"] - follow["post_total_tokens"]) /
                ignore["post_total_tokens"], 4
            ) if ignore["post_total_tokens"] else None,
            "post_est_cost_saved_usd": round(
                ignore["post_est_cost_usd"] - follow["post_est_cost_usd"], 6),
            "post_tool_errors_delta": ignore["post_tool_errors"] - follow["post_tool_errors"],
            "post_huge_outputs_delta": ignore["post_huge_outputs"] - follow["post_huge_outputs"],
            "session_total_tokens_saved": ignore["session_total_tokens"] - follow["session_total_tokens"],
            "session_token_reduction_ratio": round(
                (ignore["session_total_tokens"] - follow["session_total_tokens"]) /
                ignore["session_total_tokens"], 4
            ) if ignore["session_total_tokens"] else None,
            "session_est_cost_saved_usd": round(
                ignore["session_est_cost_usd"] - follow["session_est_cost_usd"], 6),
            "session_tool_errors_delta": ignore["session_tool_errors"] - follow["session_tool_errors"],
            "session_huge_outputs_delta": ignore["session_huge_outputs"] - follow["session_huge_outputs"],
        },
        "directional_win": directional_win,
        "notes": [
            "This is a paired smoke metric, not a causal claim.",
            "Both oracle flags must be true before token savings mean anything.",
            "The anchor is the first oversized tool output in each session.",
        ],
    }


def print_offload_pair(report: dict) -> None:
    def yn(v):
        return "yes" if v is True else "no" if v is False else "unknown"

    print("\nMR Token Codex offload ROI pair")
    print("-------------------------------")
    print(f"mode: {report.get('mode', 'post-anchor')}")
    print(f"threshold: {report['threshold_chars']:,} output chars")
    prefix = "session" if report.get("mode") == "prevention" else "post"
    for label in ("ignore", "follow"):
        m = report[label]
        anchor = m["anchor"]
        if anchor:
            anchor_s = f"{anchor['tool_name']} {anchor['output_chars']:,} chars"
        else:
            anchor_s = "none"
        print(
            f"{label:6} {m['session_id'][:12]:12} "
            f"{prefix}_tokens={m[f'{prefix}_total_tokens']:,} "
            f"{prefix}_cost=${m[f'{prefix}_est_cost_usd']:,.4f} "
            f"errors={m[f'{prefix}_tool_errors']} huge_outputs={m[f'{prefix}_huge_outputs']} "
            f"anchor={anchor_s}"
        )
    q = report["quality"]
    print(f"quality gate: ignore={yn(q['ignore_passed'])}, follow={yn(q['follow_passed'])}")
    d = report["delta"]
    ratio = d["token_reduction_ratio"]
    ratio_s = "n/a" if ratio is None else f"{ratio:.1%}"
    print(
        f"delta: {d['tokens_saved']:,} {prefix} tokens saved "
        f"({ratio_s}), ${d['est_cost_saved_usd']:,.4f}"
    )
    print("directional win: " + ("yes" if report["directional_win"] else "no"))
    if not q["known"]:
        print("note: supply --ignore-passed/--follow-passed after running both oracles")
    print()


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2)
