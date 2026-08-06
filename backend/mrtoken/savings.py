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

import mrtoken.datadir as dd   # referenced through the module so tests can patch central_default
from mrtoken.ingest import now_iso

_SCHEMA = ("CREATE TABLE IF NOT EXISTS saving ("
           "id INTEGER PRIMARY KEY, tool TEXT NOT NULL, tokens INTEGER NOT NULL, "
           "session_id TEXT, created_at TEXT NOT NULL, "
           "source TEXT, rule TEXT, project_key TEXT)")

# Stage-2 Repair 1 (attributable numerator). New rows carry session_id + source
# (provider) + the firing rule + a project/cohort key, so a realized saving joins to
# exactly one trace / one provider. Columns are added ADDITIVELY; the legacy rows
# (empty session_id) are NOT backfilled — they stay legacy_unattributable and are
# excluded from every ratio (see attributed_rows()). NOTE: running _migrate_saving()
# against a LIVE store is a schema mutation — capture a preimage and gate it
# separately (per the Stage-2 brief). Only temp DBs are touched during development.
_ATTR_COLS = (("source", "TEXT"), ("rule", "TEXT"), ("project_key", "TEXT"))


def _migrate_saving(conn: sqlite3.Connection) -> None:
    """Idempotent additive migration: add the attribution columns if missing."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(saving)")}
    for col, typ in _ATTR_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE saving ADD COLUMN {col} {typ}")


def _db_path() -> str:
    # Resolve THROUGH the module so patching mrtoken.datadir.central_default (or
    # savings.dd) redirects every read/write — never bind the live path at import.
    return os.path.join(dd.central_default(), "savings.db")


def _db() -> sqlite3.Connection:
    """WRITE connection. Creates the store with the full (attributed) schema if
    missing. Does NOT migrate an existing store — that is the single explicit,
    separately-gated entry point migrate_saving_db(), which no read path calls."""
    p = _db_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    return conn


def _db_ro() -> "sqlite3.Connection | None":
    """READ-ONLY connection, or None if the store does not exist. Never creates,
    schemas, migrates, or makedirs — a read must not mutate or spawn a store."""
    p = _db_path()
    if not os.path.exists(p):
        return None
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def migrate_saving_db() -> None:
    """The SINGLE explicit entry point that migrates an EXISTING store to add the
    attribution columns (additive). No read path calls this. GATED: capture a preimage
    and get approval before running it against a live store — never run from here."""
    p = _db_path()
    if not os.path.exists(p):
        return
    conn = sqlite3.connect(p)
    _migrate_saving(conn)
    conn.commit()
    conn.close()


def record(tool: str, tokens, session_id: str = "", *,
           source: str | None = None, rule: str | None = None,
           project_key: str | None = None) -> None:
    """Log realized tokens saved by a tool action (no-op for non-positive).

    Stage-2 Repair 1: optionally attribute the row to its session / provider / firing
    rule / project so it joins to exactly one trace. Callers that lack a session
    identity (e.g. the MCP offload path — the server has no session env) simply omit
    them, and the row stays legacy_unattributable rather than carrying invented values."""
    try:
        tokens = int(tokens or 0)
    except (TypeError, ValueError):
        return
    if tokens <= 0:
        return
    conn = _db()
    conn.execute(
        "INSERT INTO saving(tool,tokens,session_id,created_at,source,rule,project_key) "
        "VALUES(?,?,?,?,?,?,?)",
        (tool, tokens, session_id, now_iso(), source, rule, project_key))
    conn.commit()
    conn.close()


def attributed_rows() -> list:
    """Realized rows that carry attribution (session_id present), READ-ONLY. Excludes
    empty-session_id legacy rows from every ratio (Repair 1 — no backfill). Missing
    store => empty. (The synthetic rows id 14/15 are surfaced for gated cleanup, not
    removed here.)"""
    conn = _db_ro()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT tool, tokens, session_id, source, rule, project_key, created_at "
        "FROM saving WHERE session_id IS NOT NULL AND session_id <> ''").fetchall()
    conn.close()
    return rows


def realized() -> dict:
    conn = _db_ro()
    if conn is None:                 # missing store => empty; a read never creates one
        return {"total": 0, "by_tool": {}}
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
