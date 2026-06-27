#!/usr/bin/env python3
"""MR Token — the savings report (ROADMAP 7.1): make the value FELT.

Rosson's point: show the token-count improvement so people see the value. Two
honest figures:
  - REALIZED — tokens actually kept out of context by tools that ran (e.g. every
    `offload` call logs its est_tokens_saved here). Grows as the toolbox gets used.
  - ADDRESSABLE — tokens of waste the rules have *identified* (sum of recommendation
    est_savings) — the opportunity, shown now even before the tools are used.

Realized savings live in a central log (~/.mrtoken/data/savings.db) so they
aggregate across all sessions/projects.
"""
from __future__ import annotations
import os, sqlite3

from mrtoken.datadir import central_default
from mrtoken.ingest import now_iso

_SCHEMA = ("CREATE TABLE IF NOT EXISTS saving ("
           "id INTEGER PRIMARY KEY, tool TEXT NOT NULL, tokens INTEGER NOT NULL, "
           "session_id TEXT, created_at TEXT NOT NULL)")


def _db() -> sqlite3.Connection:
    p = os.path.join(central_default(), "savings.db")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    return conn


def record(tool: str, tokens, session_id: str = "") -> None:
    """Log realized tokens saved by a tool action (no-op for non-positive)."""
    try:
        tokens = int(tokens or 0)
    except (TypeError, ValueError):
        return
    if tokens <= 0:
        return
    conn = _db()
    conn.execute("INSERT INTO saving(tool,tokens,session_id,created_at) VALUES(?,?,?,?)",
                 (tool, tokens, session_id, now_iso()))
    conn.commit()
    conn.close()


def realized() -> dict:
    conn = _db()
    rows = conn.execute("SELECT tool, COALESCE(SUM(tokens),0), COUNT(*) FROM saving GROUP BY tool").fetchall()
    conn.close()
    by_tool = {t: {"tokens": int(tk), "uses": n} for t, tk, n in rows}
    return {"total": sum(v["tokens"] for v in by_tool.values()), "by_tool": by_tool}


def addressable(conn: sqlite3.Connection) -> int:
    """Tokens of waste the rules identified (sum of recommendation est_savings)."""
    try:
        row = conn.execute("SELECT COALESCE(SUM(est_savings_tokens),0) FROM recommendation").fetchone()
        return int(row[0] or 0)
    except sqlite3.Error:
        return 0


def print_savings(conn: sqlite3.Connection) -> None:
    r = realized()
    addr = addressable(conn)
    print(f"\n{'─'*56}")
    print("  MR Token — savings")
    print(f"{'─'*56}")
    print(f"  realized (tools that ran)   ~{r['total']:>12,} tok")
    for tool, d in sorted(r["by_tool"].items(), key=lambda kv: -kv[1]["tokens"]):
        print(f"    {tool:10} ~{d['tokens']:>12,} tok  ({d['uses']} use(s))")
    if not r["by_tool"]:
        print("    (none yet — savings log fills as offload/handoff get used)")
    print(f"  addressable (rules found)   ~{addr:>12,} tok  ⚠ opportunity, not yet realized")
    print(f"{'─'*56}\n")
