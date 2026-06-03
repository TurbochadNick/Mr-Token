#!/usr/bin/env python3
"""MR Token — export bridge.

Emits the accurate transcript-derived metrics (real token counts, cache stats,
cost, profile, recommendation counts) as JSON, keyed by session_id.

This is the integration surface for the TypeScript token-tithe UI/audit: it can
either read the `session_summary` SQL view directly from the shared
.token-tithe/token-tithe.db, or shell out to:

    mrtoken-transcript export [session-prefix] [--db PATH]

Both expose the same fields. The TS `events` table is keyed on the same
session_id, so the UI can join estimated (events) ↔ actual (this) per session.
"""
from __future__ import annotations
import json, sqlite3


SUMMARY_COLUMNS = [
    "trace_id", "session_id", "parent_session_id", "source", "profile",
    "profile_confidence", "project_path", "title", "started_at", "ended_at",
    "model_calls", "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_write_tokens", "total_tokens", "est_cost_usd", "cache_hit_ratio",
    "tool_calls", "tool_errors", "recommendation_count", "high_recommendations",
]


def session_summaries(conn: sqlite3.Connection, prefix: str | None = None) -> list[dict]:
    """Return per-session accurate metrics from the session_summary view."""
    sql = f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM session_summary"
    params: tuple = ()
    if prefix:
        sql += " WHERE session_id LIKE ?"
        params = (prefix + "%",)
    sql += " ORDER BY started_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(zip(SUMMARY_COLUMNS, row)) for row in rows]


def export_report(conn: sqlite3.Connection, prefix: str | None = None) -> str:
    """Return a JSON document of session summaries + their recommendations."""
    summaries = session_summaries(conn, prefix)
    for s in summaries:
        recs = conn.execute(
            "SELECT rule, severity, message, est_savings_tokens FROM recommendation "
            "WHERE trace_id=? ORDER BY CASE severity WHEN 'high' THEN 0 "
            "WHEN 'warn' THEN 1 ELSE 2 END", (s["trace_id"],)
        ).fetchall()
        s["recommendations"] = [
            {"rule": r[0], "severity": r[1], "message": r[2], "est_savings_tokens": r[3]}
            for r in recs
        ]
    return json.dumps({"schema": "mrtoken.session_summary.v1",
                       "sessions": summaries}, indent=2)
