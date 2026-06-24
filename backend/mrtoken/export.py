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
    "model_calls", "is_low_activity", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "total_tokens", "est_cost_usd",
    "cache_hit_ratio", "tool_calls", "tool_errors", "recommendation_count",
    "high_recommendations",
]


def session_summaries(conn: sqlite3.Connection, prefix: str | None = None,
                      since: str | None = None) -> list[dict]:
    """Return per-session accurate metrics from the session_summary view.
    `since` (ISO timestamp) keeps only sessions started at/after it — for an
    incremental dashboard refresh that pulls just what's new."""
    sql = f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM session_summary"
    clauses, params = [], []
    if prefix:
        clauses.append("session_id LIKE ?"); params.append(prefix + "%")
    if since:
        clauses.append("started_at >= ?"); params.append(since)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY started_at DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(zip(SUMMARY_COLUMNS, row)) for row in rows]


DETAIL_COLUMNS = [
    "session_id", "trace_id", "model_call_id", "timestamp", "model",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "reasoning_tokens", "est_cost_usd", "tool_calls", "tool_errors",
]


def session_detail(conn: sqlite3.Connection, prefix: str) -> list[dict]:
    """Per-model-call timeline for one session (drill-down panel). Metadata only —
    token/cost/tool counts per call, no content."""
    sql = (f"SELECT {', '.join(DETAIL_COLUMNS)} FROM session_detail "
           "WHERE session_id LIKE ? ORDER BY timestamp")
    rows = conn.execute(sql, (prefix + "%",)).fetchall()
    return [dict(zip(DETAIL_COLUMNS, row)) for row in rows]


def export_detail(conn: sqlite3.Connection, prefix: str) -> str:
    """JSON timeline of one session's model calls (schema mrtoken.session_detail.v1)."""
    from mrtoken import __version__
    return json.dumps({"schema": "mrtoken.session_detail.v1",
                       "tool_version": __version__,
                       "session_prefix": prefix,
                       "calls": session_detail(conn, prefix)}, indent=2)


# the only fields that reveal WHAT/WHERE you work; --redact nulls these so the
# export is safe to share. All metrics + generic rule messages stay intact.
IDENTIFYING_FIELDS = ("project_path", "title")


def export_report(conn: sqlite3.Connection, prefix: str | None = None,
                  redact: bool = False, since: str | None = None) -> str:
    """Return a JSON document of session summaries + their recommendations.

    redact=True drops project_path and title (the only work-revealing fields),
    keeping every metric, the generic rule messages, and session_id (so a
    recipient can still dedupe) — making the file safe to hand to anyone.
    since (ISO) limits to sessions started at/after it (incremental refresh)."""
    summaries = session_summaries(conn, prefix, since)
    for s in summaries:
        if redact:
            for f in IDENTIFYING_FIELDS:
                s[f] = None
        recs = conn.execute(
            "SELECT rule, severity, message, est_savings_tokens FROM recommendation "
            "WHERE trace_id=? ORDER BY CASE severity WHEN 'high' THEN 0 "
            "WHEN 'warn' THEN 1 ELSE 2 END", (s["trace_id"],)
        ).fetchall()
        s["recommendations"] = [
            {"rule": r[0], "severity": r[1], "message": r[2], "est_savings_tokens": r[3]}
            for r in recs
        ]
    from mrtoken import __version__
    return json.dumps({"schema": "mrtoken.session_summary.v1",
                       "tool_version": __version__,  # so a tester's export self-identifies
                       "redacted": redact,
                       "sessions": summaries}, indent=2)
