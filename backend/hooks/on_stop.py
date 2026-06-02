#!/usr/bin/env python3
"""MR Token — Claude Code Stop hook.

Fires when a session ends. Ingests the just-finished session transcript
(+ any subagent transcripts) into ~/mrtoken.db and runs the rule engine.
Prints a one-line summary visible in Claude Code output.

Receives on stdin:
  { "session_id": "<uuid>", "hook_event_name": "Stop", ... }
"""
import glob, json, os, sys
sys.path.insert(0, os.path.expanduser("~/mr_token/backend"))

DB = os.path.expanduser("~/mr_token/mrtoken.db")
PROJECTS = os.path.expanduser("~/.claude/projects")


def find_transcripts(session_id: str) -> list[str]:
    """Return main transcript + any subagent transcripts for this session."""
    paths = []
    # main transcript: any project dir
    for p in glob.glob(os.path.join(PROJECTS, "*", f"{session_id}.jsonl")):
        paths.append(p)
    # subagent transcripts nested under the session dir
    for p in glob.glob(os.path.join(PROJECTS, "*", session_id, "subagents", "agent-*.jsonl")):
        paths.append(p)
    return paths


def main():
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    session_id = payload.get("session_id", "")
    if not session_id:
        # nothing to do — hook fired without a session_id
        sys.exit(0)

    paths = find_transcripts(session_id)
    if not paths:
        # transcript may not be written yet; no-op
        sys.exit(0)

    try:
        from mrtoken.ingest import connect, ingest_file, load_prices
        from mrtoken.rules import analyse

        prices = load_prices()
        conn = connect(DB)
        totals = {"model_calls": 0, "tool_calls": 0, "recs": 0, "high": 0}

        for path in paths:
            parent = path.split(os.sep)[-3] if "subagents" in path else None
            r = ingest_file(conn, path, prices, parent_session_id=parent)
            tid = conn.execute(
                "SELECT id FROM trace WHERE session_id=?", (r["session_id"],)
            ).fetchone()[0]
            recs = analyse(conn, tid)
            totals["model_calls"] += r["model_calls"]
            totals["tool_calls"]  += r["tool_calls"]
            totals["recs"]        += len(recs)
            totals["high"]        += sum(1 for rc in recs if rc["severity"] == "high")

        # one-line summary printed to Claude Code transcript footer
        high_str = f"  {totals['high']} high-priority" if totals["high"] else ""
        print(
            f"mrtoken ✓  {totals['model_calls']} calls · "
            f"{totals['recs']} recommendations{high_str}"
            f"  →  mrtoken report {session_id[:8]}"
        )

        # if high-priority recommendations exist, surface the first message
        if totals["high"]:
            conn2 = conn  # same connection
            first_high = conn2.execute("""
                SELECT r.rule, r.message FROM recommendation r
                JOIN trace t ON t.id = r.trace_id
                WHERE t.session_id=? AND r.severity='high'
                ORDER BY CASE r.rule
                  WHEN 'fresh_handoff' THEN 0
                  WHEN 'retry_loop'    THEN 1
                  ELSE 2 END
                LIMIT 1
            """, (session_id,)).fetchone()
            if first_high:
                rule, msg = first_high
                # truncate for terminal display
                short = msg[:120] + "…" if len(msg) > 120 else msg
                print(f"  [{rule}] {short}")

    except Exception as e:
        # never crash Claude Code — silent fail, log to stderr
        print(f"mrtoken hook error: {e}", file=sys.stderr)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
