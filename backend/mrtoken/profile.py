#!/usr/bin/env python3
"""MR Token — session profile classifier.

Derived from the TTO Eco Mode methodology: classify each session into one of
four work profiles so that waste thresholds can be context-calibrated instead
of one-size-fits-all (a 20k-token Read is normal in `research`, alarming in
`benchmark`).

Deterministic and cheap — NO AI call. Classifies purely on the tool-call
distribution we already store (tool_name + sizes), so it never needs prompt
text and stays within the metadata-only privacy boundary.

Profiles (Eco Mode):
  agent     — orchestrates subagents/Task tools
  benchmark — runs commands, little/no file editing (logs dominate)
  code      — edits/writes files
  research  — reads/searches, little editing

Returns (profile, confidence 0..1, signals[]).
"""
from __future__ import annotations
import sqlite3

READ_SEARCH = {"read", "grep", "glob", "webfetch", "websearch", "toolsearch",
               "notebookread", "ls"}
EDIT_WRITE = {"edit", "write", "multiedit", "notebookedit"}
AGENT_TOOLS = {"task"}


def classify_profile(conn: sqlite3.Connection, tid: int) -> tuple[str, float, list[str]]:
    rows = conn.execute(
        "SELECT LOWER(COALESCE(tool_name,'')) name, COUNT(*) n, "
        "       AVG(COALESCE(output_chars,0)) avg_out "
        "FROM tool_call WHERE trace_id=? GROUP BY name", (tid,)
    ).fetchall()
    counts = {name: n for name, n, _ in rows}
    avg_out = {name: a for name, _, a in rows}
    return classify_from_counts(counts, avg_out)


def classify_from_counts(counts: dict[str, int],
                         avg_out: dict[str, float] | None = None) -> tuple[str, float, list[str]]:
    """Pure classifier over a tool-name distribution. Shared by the DB path
    (classify_profile) and the live advisor (watch), so both agree."""
    avg_out = avg_out or {}
    total = sum(counts.values())
    if total == 0:
        return ("code", 0.2, ["no tool calls — default"])

    def frac(group) -> float:
        return sum(n for name, n in counts.items()
                   if name in group or any(name.startswith(g) for g in group)) / total

    agent_n = sum(n for name, n in counts.items()
                  if name in AGENT_TOOLS or "agent" in name or "subagent" in name)
    read_frac = frac(READ_SEARCH)
    edit_frac = frac(EDIT_WRITE)
    bash_frac = counts.get("bash", 0) / total
    bash_avg_out = avg_out.get("bash", 0)
    task_frac = agent_n / total

    signals = [f"{total} tool calls",
               f"read/search {read_frac:.0%}", f"edit/write {edit_frac:.0%}",
               f"bash {bash_frac:.0%}", f"task {task_frac:.0%}"]

    # priority order matches Eco Mode's intent.
    # `agent` requires orchestration to be a real FRACTION of the work — a few
    # Task calls inside a long coding session is `code`, not `agent`.
    if task_frac >= 0.05 and agent_n >= 2:
        return ("agent", min(0.95, 0.4 + task_frac),
                signals + [f"{agent_n} Task/subagent calls ({task_frac:.0%})"])
    if edit_frac >= 0.10:
        return ("code", min(0.9, 0.4 + edit_frac), signals + ["mutates files"])
    if bash_frac >= 0.5 and edit_frac == 0:
        # bash-dominated, no edits → running/benchmarking; large outputs strengthen it
        conf = min(0.85, 0.4 + bash_frac) + (0.1 if bash_avg_out > 8000 else 0)
        return ("benchmark", min(0.9, conf), signals + [f"bash avg output {int(bash_avg_out)} chars"])
    if read_frac >= 0.5:
        return ("research", min(0.9, 0.4 + read_frac), signals + ["read/search dominated"])
    return ("code", 0.3, signals + ["mixed — default to code"])
