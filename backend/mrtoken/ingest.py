#!/usr/bin/env python3
"""MR Token MVP — Layer 1 ingester.

Parse a Claude Code transcript JSONL into the SQLite ledger.
Metadata-default: we hash content for repeat detection; we do NOT store raw text.

Usage:
    python3 -m mrtoken.ingest <transcript.jsonl> [--db mrtoken.db]
    python3 -m mrtoken.ingest --all [--db mrtoken.db]   # ingest ~/.claude/projects/**.jsonl
"""
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, sys, glob
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "schema.sql")
PRICES = os.path.join(HERE, "prices.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def load_prices():
    with open(PRICES) as f:
        return json.load(f)


def price_for(prices, model: str):
    if not model:
        return prices["models"]["default"]
    for key, tbl in prices["models"].items():
        if key != "default" and key in model:
            return tbl
    return prices["models"]["default"]


def est_cost(prices, model, usage) -> float:
    p = price_for(prices, model)
    m = 1_000_000.0
    return round(
        usage.get("input_tokens", 0)               / m * p["input"]
        + usage.get("output_tokens", 0)            / m * p["output"]
        + usage.get("cache_read_input_tokens", 0)  / m * p["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) / m * p["cache_write"],
        6,
    )


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    with open(SCHEMA) as f:
        conn.executescript(f.read())
    return conn


def content_text(content) -> str:
    """Flatten a message.content (str or list of blocks) to text for hashing/sizing."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                parts.append(str(b)); continue
            t = b.get("type")
            if t == "text":
                parts.append(b.get("text", ""))
            elif t == "tool_result":
                parts.append(content_text(b.get("content", "")))
            elif t == "tool_use":
                parts.append(json.dumps(b.get("input", {})))
            else:
                parts.append(json.dumps(b))
        return "\n".join(parts)
    return json.dumps(content)


def ingest_file(conn: sqlite3.Connection, path: str, prices, parent_session_id: str | None = None) -> dict:
    sid = os.path.splitext(os.path.basename(path))[0]
    # subagent files: agent-<hex>.jsonl inside <session>/subagents/
    # use the parent session dir name as parent linkage
    is_subagent = "subagents" in path
    if is_subagent and not parent_session_id:
        parent_session_id = path.split(os.sep)[-3]  # <session-uuid>/subagents/agent-*.jsonl
    cur = conn.cursor()
    # idempotent: drop prior rows for this session
    row = cur.execute("SELECT id FROM trace WHERE session_id=?", (sid,)).fetchone()
    if row:
        tid = row[0]
        for t in ("model_call", "tool_call", "event", "context_block", "recommendation"):
            cur.execute(f"DELETE FROM {t} WHERE trace_id=?", (tid,))
        cur.execute("DELETE FROM trace WHERE id=?", (tid,))

    meta = {"project_path": None, "git_branch": None, "cc_version": None,
            "entrypoint": None, "title": None, "first_ts": None, "last_ts": None}
    model_calls, tool_calls, pending_tools = [], [], {}  # tool_use_id -> tool_call dict
    blocks = {}  # (block_type, hash) -> dict
    n_lines = 0

    def track_block(btype, text, ts):
        if not text:
            return
        h = sha(text)
        key = (btype, h)
        b = blocks.get(key)
        if b is None:
            blocks[key] = {"block_type": btype, "hash": h,
                           "char_count": len(text), "token_count": len(text) // 4,
                           "repeat_count": 1, "first_seen": ts, "last_seen": ts}
        else:
            b["repeat_count"] += 1
            b["last_seen"] = ts

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_lines += 1
            ts = o.get("timestamp")
            if ts:
                meta["first_ts"] = min(meta["first_ts"], ts) if meta["first_ts"] else ts
                meta["last_ts"] = max(meta["last_ts"], ts) if meta["last_ts"] else ts
            for k_meta, k_src in (("project_path", "cwd"), ("git_branch", "gitBranch"),
                                  ("cc_version", "version"), ("entrypoint", "entrypoint")):
                if o.get(k_src) and not meta[k_meta]:
                    meta[k_meta] = o[k_src]
            etype = o.get("type")
            msg = o.get("message") if isinstance(o.get("message"), dict) else {}

            if etype in ("custom-title", "ai-title") and not meta["title"]:
                meta["title"] = o.get("title") or o.get("text")

            if etype == "assistant" and "usage" in msg:
                u = msg["usage"]
                cc = u.get("cache_creation") or {}
                model_calls.append({
                    "request_id": o.get("requestId"),
                    "message_uuid": o.get("uuid"),
                    "parent_uuid": o.get("parentUuid"),
                    "model": msg.get("model"),
                    "timestamp": ts,
                    "input_tokens": u.get("input_tokens", 0),
                    "output_tokens": u.get("output_tokens", 0),
                    "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
                    "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                    "ephemeral_1h_tokens": cc.get("ephemeral_1h_input_tokens", 0),
                    "ephemeral_5m_tokens": cc.get("ephemeral_5m_input_tokens", 0),
                    "service_tier": u.get("service_tier"),
                    "stop_reason": msg.get("stop_reason"),
                    "is_sidechain": 1 if o.get("isSidechain") else 0,
                    "est_cost_usd": est_cost(prices, msg.get("model"), u),
                    "price_version": prices["version"],
                })
                # tool_use blocks requested by this assistant turn
                msg_uuid = o.get("uuid")  # link tool_calls back to this model_call later
                for b in (msg.get("content") or []):
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        inp = json.dumps(b.get("input", {}))
                        pending_tools[b.get("id")] = {
                            "tool_use_id": b.get("id"), "tool_name": b.get("name"),
                            "input_chars": len(inp), "input_hash": sha(inp),
                            "started_at": ts, "output_chars": None,
                            "output_tokens_est": None, "output_hash": None,
                            "is_error": 0, "ended_at": None,
                            "_msg_uuid": msg_uuid,  # internal; used to set model_call_id after insert
                        }
                track_block("assistant", content_text(msg.get("content")), ts)

            elif etype == "user":
                # tool_result blocks close out pending tool calls
                content = msg.get("content") if msg else o.get("content")
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            tu = b.get("tool_use_id")
                            txt = content_text(b.get("content", ""))
                            tc = pending_tools.get(tu) or {"tool_use_id": tu, "tool_name": None,
                                "input_chars": None, "input_hash": None, "started_at": None}
                            tc.update({"output_chars": len(txt), "output_tokens_est": len(txt) // 4,
                                       "output_hash": sha(txt),
                                       "is_error": 1 if b.get("is_error") else 0, "ended_at": ts})
                            tool_calls.append(tc); pending_tools.pop(tu, None)
                track_block("user", content_text(content), ts)

            elif etype == "system":
                track_block("system", content_text(msg.get("content") if msg else o.get("content")), ts)

    # any tool_use never closed (e.g. truncated session)
    tool_calls.extend(pending_tools.values())

    # write
    source = "claude_code_subagent" if is_subagent else "claude_code"
    cur.execute("""INSERT INTO trace(source,session_id,parent_session_id,project_path,git_branch,
                   cc_version,entrypoint,started_at,ended_at,title,ingested_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (source, sid, parent_session_id, meta["project_path"], meta["git_branch"],
                 meta["cc_version"], meta["entrypoint"], meta["first_ts"], meta["last_ts"],
                 meta["title"], now_iso()))
    tid = cur.lastrowid
    for mc in model_calls:
        cur.execute("""INSERT INTO model_call(trace_id,request_id,message_uuid,parent_uuid,model,
            timestamp,input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens,
            ephemeral_1h_tokens,ephemeral_5m_tokens,service_tier,stop_reason,is_sidechain,
            est_cost_usd,price_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, mc["request_id"], mc["message_uuid"], mc["parent_uuid"], mc["model"], mc["timestamp"],
             mc["input_tokens"], mc["output_tokens"], mc["cache_read_input_tokens"],
             mc["cache_creation_input_tokens"], mc["ephemeral_1h_tokens"], mc["ephemeral_5m_tokens"],
             mc["service_tier"], mc["stop_reason"], mc["is_sidechain"], mc["est_cost_usd"], mc["price_version"]))
    # build msg_uuid → model_call db id map for linking tool_calls
    uuid_to_mcid = {r[0]: r[1] for r in cur.execute(
        "SELECT message_uuid, id FROM model_call WHERE trace_id=? AND message_uuid IS NOT NULL", (tid,)
    )}
    for tc in tool_calls:
        mc_id = uuid_to_mcid.get(tc.get("_msg_uuid"))
        cur.execute("""INSERT INTO tool_call(trace_id,model_call_id,tool_use_id,tool_name,
            input_chars,input_hash,output_chars,output_tokens_est,output_hash,is_error,
            started_at,ended_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, mc_id, tc.get("tool_use_id"), tc.get("tool_name"),
             tc.get("input_chars"), tc.get("input_hash"),
             tc.get("output_chars"), tc.get("output_tokens_est"), tc.get("output_hash"),
             tc.get("is_error", 0), tc.get("started_at"), tc.get("ended_at")))
    for b in blocks.values():
        cur.execute("""INSERT OR IGNORE INTO context_block(trace_id,block_type,hash,token_count,
            char_count,repeat_count,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?)""",
            (tid, b["block_type"], b["hash"], b["token_count"], b["char_count"],
             b["repeat_count"], b["first_seen"], b["last_seen"]))
    conn.commit()
    return {"session_id": sid, "lines": n_lines, "model_calls": len(model_calls),
            "tool_calls": len(tool_calls), "context_blocks": len(blocks)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="transcript .jsonl")
    ap.add_argument("--all", action="store_true", help="ingest all ~/.claude/projects/**.jsonl")
    ap.add_argument("--db", default="mrtoken.db")
    ap.add_argument("--rules", action="store_true", help="run rule engine after ingestion")
    a = ap.parse_args(argv)
    prices = load_prices()
    conn = connect(a.db)
    paths = []
    if a.all:
        # depth 2: main session transcripts  (<project>/<session>.jsonl)
        # depth 3: subagent transcripts       (<project>/<session>/subagents/agent-*.jsonl)
        paths = (glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
                 + glob.glob(os.path.expanduser("~/.claude/projects/*/*/subagents/agent-*.jsonl")))
    elif a.path:
        paths = [a.path]
    else:
        ap.error("give a path or --all")
    total = {"sessions": 0, "model_calls": 0, "tool_calls": 0, "recommendations": 0}
    for p in paths:
        try:
            parent = p.split(os.sep)[-3] if "subagents" in p else None
            r = ingest_file(conn, p, prices, parent_session_id=parent)
            total["sessions"] += 1
            total["model_calls"] += r["model_calls"]
            total["tool_calls"] += r["tool_calls"]
            if a.rules:
                from mrtoken.rules import analyse
                tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                                   (r["session_id"],)).fetchone()[0]
                recs = analyse(conn, tid)
                total["recommendations"] += len(recs)
        except Exception as e:
            print(f"SKIP {os.path.basename(p)}: {e}", file=sys.stderr)
    print(json.dumps({"db": a.db, **total}, indent=2))


if __name__ == "__main__":
    main()
