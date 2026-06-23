#!/usr/bin/env python3
"""MR Token — cost-gated Assist suggestion (ROADMAP 3.4).

The Assist tier is the only place MR Token would spend tokens on an LLM (generate
a handoff, summarise logs, diagnose cost). Per the brief it is **opt-in and never
automatic** — so this module only ever *suggests* an assist, and only when the
expected token savings clearly justify the assist's own cost.

Gate:  suggest iff  projected_savings >= ASSIST_SAVINGS_RATIO * ASSIST_COST_TOKENS

Defaults (Zach's call, both tunable here): opt-in OFF, ratio 5x. Conservative on
purpose — it stays silent on routine sessions and only speaks when there is real
money on the table, preserving the "cheap, no-LLM-by-default" promise. Toggle on
with the MRTOKEN_ASSIST env var. Metadata-only; no content is read.
"""
from __future__ import annotations
import os, sqlite3

ASSIST_COST_TOKENS = 5_000     # rough token cost of running one assist (e.g. /mr-handoff)
ASSIST_SAVINGS_RATIO = 5       # require savings >= this multiple of the assist cost

# rules whose remedy is a fresh start → suggest /mr-handoff; otherwise /mr-why
_HANDOFF_RULES = {"fresh_handoff", "step_runaway", "context_rot", "repeated_context"}


def assist_enabled() -> bool:
    """Opt-in via env var; OFF by default so behavior is unchanged out of the box."""
    return os.environ.get("MRTOKEN_ASSIST", "").strip().lower() in ("1", "true", "yes", "on")


def projected_savings(conn: sqlite3.Connection, tid: int) -> int:
    """Sum of est_savings_tokens across the session's recommendations (None→0)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(est_savings_tokens, 0)), 0) "
        "FROM recommendation WHERE trace_id=?", (tid,)).fetchone()
    return int(row[0] or 0)


def assist_suggestion(conn: sqlite3.Connection, tid: int, enabled: bool | None = None) -> str | None:
    """Return a one-line assist suggestion, or None when the assist is disabled or
    the savings don't clear the gate. NEVER runs the assist — only suggests it."""
    if enabled is None:
        enabled = assist_enabled()
    if not enabled:
        return None
    saved = projected_savings(conn, tid)
    if saved < ASSIST_SAVINGS_RATIO * ASSIST_COST_TOKENS:
        return None
    rules = {r[0] for r in conn.execute(
        "SELECT DISTINCT rule FROM recommendation WHERE trace_id=?", (tid,))}
    assist = "/mr-handoff" if (_HANDOFF_RULES & rules) else "/mr-why"
    return (f"assist worth it: {assist} could recover ~{saved:,} tok, "
            f"~{saved // ASSIST_COST_TOKENS}x the ~{ASSIST_COST_TOKENS:,}-tok assist cost")
