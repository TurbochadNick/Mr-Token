#!/usr/bin/env python3
"""MR Token — Codex transcript adapter (ROADMAP 3.5).

Codex (OpenAI CLI) writes its own JSONL rollout under ~/.codex/sessions/.../*.jsonl,
shaped very differently from Claude Code's. This adapter maps it into the SAME
`trace → model_call / tool_call` schema with source='codex', so the existing rule
engine, reports, fleet, and ROI all work unchanged across both agents.

Codex line shapes used:
  session_meta            payload.session_id, cwd, timestamp
  turn_context            payload.model            (current model for following calls)
  event_msg/token_count   payload.info.last_token_usage = per-response token usage
  response_item           function_call / custom_tool_call (+ *_output) = tool calls

Token mapping: Codex `input_tokens` INCLUDES cached, so fresh input = input − cached,
and cached_input_tokens → cache_read. reasoning_output_tokens → reasoning_tokens.
Cost is computed only if the model is in the price table (Claude-priced today), else
left NULL — tokens are the ground truth, cost is a best-effort overlay.
"""
from __future__ import annotations
import hashlib, json, os

from mrtoken.ingest import now_iso, load_prices, est_cost


def _is_codex_transcript(path: str) -> bool:
    """Sniff: a Codex rollout's first non-empty line is a session_meta record."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                return d.get("type") == "session_meta"
    except (json.JSONDecodeError, OSError):
        return False
    return False


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def ingest_codex_file(conn, path: str, prices=None) -> dict:
    """Ingest one Codex rollout JSONL into the shared schema. Idempotent: replaces
    any prior rows for the session (trace.session_id is UNIQUE)."""
    if prices is None:
        prices = load_prices()
    sid = None
    cwd = first_ts = last_ts = None
    model = None
    model_calls, tool_calls = [], []
    pending = {}  # call_id -> tool_call dict awaiting its output

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp")
            if ts:
                first_ts = first_ts or ts
                last_ts = ts
            t = d.get("type")
            p = d.get("payload") or {}

            if t == "session_meta":
                sid = p.get("session_id") or sid
                cwd = p.get("cwd") or cwd
            elif t == "turn_context":
                model = p.get("model") or model
            elif t == "event_msg" and p.get("type") == "token_count":
                u = (p.get("info") or {}).get("last_token_usage") or {}
                if not u or not (u.get("total_tokens") or u.get("output_tokens")):
                    continue
                cached = u.get("cached_input_tokens", 0) or 0
                fresh_in = max(0, (u.get("input_tokens", 0) or 0) - cached)
                out = u.get("output_tokens", 0) or 0
                model_calls.append({
                    "timestamp": ts, "model": model,
                    "input_tokens": fresh_in, "output_tokens": out,
                    "cache_read_input_tokens": cached,
                    "reasoning_tokens": u.get("reasoning_output_tokens"),
                    "est_cost_usd": est_cost(prices, model, {
                        "input_tokens": fresh_in, "output_tokens": out,
                        "cache_read_input_tokens": cached, "cache_creation_input_tokens": 0}),
                })
            elif t == "response_item":
                pt = p.get("type")
                if pt in ("function_call", "custom_tool_call", "web_search_call", "tool_search_call"):
                    call_id = p.get("call_id") or p.get("id")
                    inp = p.get("arguments") or p.get("input") or json.dumps(p.get("action") or {})
                    inp = inp if isinstance(inp, str) else json.dumps(inp)
                    tc = {"tool_use_id": call_id, "tool_name": p.get("name") or pt,
                          "input_chars": len(inp), "input_hash": _hash(inp),
                          "output_chars": None, "output_hash": None, "is_error": 0,
                          "started_at": ts, "ended_at": ts}
                    tool_calls.append(tc)
                    if call_id:
                        pending[call_id] = tc
                elif pt in ("function_call_output", "custom_tool_call_output", "tool_search_output"):
                    call_id = p.get("call_id")
                    out = p.get("output")
                    out = out if isinstance(out, str) else json.dumps(out)
                    tc = pending.get(call_id)
                    if tc is not None:
                        tc["output_chars"] = len(out)
                        tc["output_hash"] = _hash(out)
                        tc["output_tokens_est"] = len(out) // 4
                        # Codex tool output marks failure as a non-zero exit code
                        low = out.lower()
                        tc["is_error"] = 1 if ("exit code: " in low and "exit code: 0" not in low) \
                            or ("exited with code " in low and "code 0" not in low) else 0
                        tc["ended_at"] = ts

    if not sid:
        sid = os.path.splitext(os.path.basename(path))[0]
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM trace WHERE session_id=?", (sid,)).fetchone()
    if row:
        tid = row[0]
        for tbl in ("model_call", "tool_call", "event", "context_block", "recommendation"):
            cur.execute(f"DELETE FROM {tbl} WHERE trace_id=?", (tid,))
        cur.execute("DELETE FROM trace WHERE id=?", (tid,))

    if not model_calls:
        conn.commit()
        return {"session_id": sid, "model_calls": 0, "tool_calls": 0, "skipped": True}

    cur.execute("""INSERT INTO trace(source,session_id,project_path,started_at,ended_at,ingested_at)
                   VALUES('codex',?,?,?,?,?)""", (sid, cwd, first_ts, last_ts, now_iso()))
    tid = cur.lastrowid
    for mc in model_calls:
        cur.execute("""INSERT INTO model_call(trace_id,model,timestamp,input_tokens,output_tokens,
            cache_read_input_tokens,reasoning_tokens,est_cost_usd)
            VALUES(?,?,?,?,?,?,?,?)""",
            (tid, mc["model"], mc["timestamp"], mc["input_tokens"], mc["output_tokens"],
             mc["cache_read_input_tokens"], mc["reasoning_tokens"], mc["est_cost_usd"]))
    for tc in tool_calls:
        cur.execute("""INSERT INTO tool_call(trace_id,tool_use_id,tool_name,input_chars,input_hash,
            output_chars,output_tokens_est,output_hash,is_error,started_at,ended_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, tc["tool_use_id"], tc["tool_name"], tc["input_chars"], tc["input_hash"],
             tc.get("output_chars"), tc.get("output_tokens_est"), tc.get("output_hash"),
             tc.get("is_error", 0), tc.get("started_at"), tc.get("ended_at")))
    conn.commit()
    return {"session_id": sid, "model_calls": len(model_calls),
            "tool_calls": len(tool_calls), "skipped": False}
