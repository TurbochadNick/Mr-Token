#!/usr/bin/env python3
"""MR Token — measure-don't-degrade (ROADMAP 6.7): the safety guardrail.

Every time the proc engine recommends a tool, we later check whether it actually
helped (did context improve?). Outcomes accrue in a central store; a tool whose
recent outcomes trend negative **auto-disables itself** (policy → off) and says so.
That's the "don't let optimization hurt me" guarantee enforced by data, not faith.

Honesty: the auto-signal is *intervention effectiveness in situ* — "after we pushed
this tool, did context improve?" — which folds in both "the tool didn't help" and
"it kept getting recommended but ignored." Either way, a tool that isn't working in
practice should stop nagging. Explicit user verdicts (feedback) can also feed it.

helped ∈ {+1 helped, 0 neutral, -1 hurt}. Central DB: ~/.mrtoken/data/outcomes.db.
"""
from __future__ import annotations
import os, sqlite3

from mrtoken.datadir import central_default
from mrtoken.ingest import now_iso

MIN_SAMPLE = 4        # don't judge a tool until it has this many outcomes
WINDOW = 12           # judge on the most recent N outcomes
IMPROVE_DROP = 5      # ctx % drop that counts as "helped"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcome (
  id          INTEGER PRIMARY KEY,
  tool        TEXT NOT NULL,
  helped      INTEGER NOT NULL,   -- +1 helped, 0 neutral, -1 hurt
  session_id  TEXT,
  note        TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcome_tool ON outcome(tool);
"""


def _db_path() -> str:
    return os.path.join(central_default(), "outcomes.db")


def _conn() -> sqlite3.Connection:
    p = _db_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(_SCHEMA)
    return conn


def helped_from_ctx(ctx_before: int, ctx_after: int) -> int:
    """Auto-signal: did context improve after we pushed the tool?"""
    if ctx_after <= ctx_before - IMPROVE_DROP:
        return 1
    if ctx_after >= ctx_before:        # didn't drop (climbed or stuck) → not working
        return -1
    return 0


def record(tool: str, helped: int, session_id: str = "", note: str = "") -> None:
    conn = _conn()
    conn.execute("INSERT INTO outcome(tool,helped,session_id,note,created_at) VALUES(?,?,?,?,?)",
                 (tool, int(helped), session_id, note, now_iso()))
    conn.commit()
    conn.close()


def health(tool: str) -> dict:
    conn = _conn()
    rows = conn.execute("SELECT helped FROM outcome WHERE tool=? ORDER BY id DESC LIMIT ?",
                        (tool, WINDOW)).fetchall()
    conn.close()
    helped = sum(1 for (h,) in rows if h > 0)
    hurt = sum(1 for (h,) in rows if h < 0)
    n = len(rows)
    disable = n >= MIN_SAMPLE and hurt > helped
    return {"tool": tool, "n": n, "helped": helped, "hurt": hurt,
            "net": helped - hurt, "disable": disable}


def enforce(emit=None) -> list[str]:
    """Auto-disable tools trending negative (via the policy). Returns disabled names."""
    from mrtoken.policy import autonomy, set_autonomy
    from mrtoken.toolbox import TOOL_REGISTRY
    disabled = []
    for tool in TOOL_REGISTRY:
        h = health(tool)
        if h["disable"] and autonomy(tool) != "off":
            set_autonomy(tool, "off")
            disabled.append(tool)
            if emit:
                emit(f"⚠ mr: auto-disabled `{tool}` — it hurt/didn't help in "
                     f"{h['hurt']}/{h['n']} recent cases. Re-enable with "
                     f"`mrtoken-transcript config --intervene {tool}=tell`.")
    return disabled
