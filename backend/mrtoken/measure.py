#!/usr/bin/env python3
"""MR Token — Stage-2 measurement primitives (instrumentation repair).

Two functions the repaired instrument needs, kept separate from the rules so the
measurement logic is testable in isolation against a temp DB:

  * Repair 2 — a NON-OVERLAPPING, additive addressable total. Rules claim waste by
    emitting the set of unit-ids they implicate; the addressable quantity is the UNION
    of those ids, each counted ONCE, with tokens taken from that unit's own recorded
    count. The canonical unit is `context_block` (keyed on its real uniqueness triple
    trace_id+hash+block_type). `tool_call` is DELIBERATELY excluded: it has no measured
    token count (only `output_tokens_est`, an estimate) and a large tool OUTPUT becomes
    a context_block, so counting both double-counts the same tokens.

  * Repair 3 — the OUTCOME, derived ONLY from `model_call` measured columns; never from
    `est_savings_tokens` (which is the estimator grading itself). Estimates stay a
    targeting heuristic, not the benefit number.

Read-only over whatever connection it's given (a temp DB in tests). No CLI, no writes.
"""
from __future__ import annotations
import sqlite3
from typing import Iterable


def union_addressable_tokens(conn: sqlite3.Connection,
                             claims: Iterable[tuple]) -> int:
    """Repair 2. `claims` = iterable of context_block unit-ids (trace_id, hash,
    block_type) that rules implicate as waste. Each DISTINCT block is counted once,
    tokens from its own `token_count` — so three rules claiming one block sum to that
    block's tokens ONCE, not three times. Unknown or tokenless blocks contribute 0."""
    total = 0
    for key in {(t, h, b) for (t, h, b) in claims}:   # dedup on the real uniqueness triple
        row = conn.execute(
            "SELECT token_count FROM context_block "
            "WHERE trace_id=? AND hash=? AND block_type=?", key).fetchone()
        if row and row[0] is not None:
            total += int(row[0])
    return total


def measured_task_tokens(conn: sqlite3.Connection,
                         trace_ids: Iterable[int]) -> dict:
    """Repair 3. Sum MEASURED throughput from `model_call` for the given traces (a
    'completed task' = its trace set, defined by the pre-registered protocol — the DB
    has no task/completion field). Uses only measured columns; never est_savings."""
    ids = list(trace_ids)
    if not ids:
        return {"input": 0, "output": 0, "cache": 0, "reasoning": 0,
                "total_tokens": 0, "est_cost_usd": 0.0}
    ph = ",".join("?" * len(ids))
    row = conn.execute(
        f"SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), "
        f"COALESCE(SUM(cache_read_input_tokens + cache_creation_input_tokens),0), "
        f"COALESCE(SUM(reasoning_tokens),0), ROUND(COALESCE(SUM(est_cost_usd),0),6) "
        f"FROM model_call WHERE trace_id IN ({ph})", tuple(ids)).fetchone()
    return {"input": row[0], "output": row[1], "cache": row[2],
            "reasoning": row[3], "total_tokens": row[0] + row[1],
            "est_cost_usd": row[4]}
