#!/usr/bin/env python3
"""MR Token — session-end Stop hook (Claude Code AND Codex).

Fires when a session ends. Ingests the just-finished session transcript
(+ any subagent transcripts) into the project-local .token-tithe DB and runs the rule engine.
Prints a one-line summary visible in the CLI output.

Works for both agents off ONE hook:
  - Claude Code: registered in ~/.claude/settings.json; transcript in ~/.claude/projects.
  - Codex: registered in ~/.codex/hooks.json; rollout in ~/.codex/sessions (parsed by
    the Codex adapter). If no Claude transcript matches the session, we look for a
    Codex rollout matching it.

Payload arrives on stdin (Claude) or, as a hedge, as a JSON argv (some hook protocols).
"""
import glob, json, os, sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

PROJECTS = os.path.expanduser("~/.claude/projects")
CODEX_DIRS = (os.path.expanduser("~/.codex/sessions"),
              os.path.expanduser("~/.codex/archived_sessions"))
CONTEXT_WARN_PCT = 70


def _fmt_token_count(tokens) -> str:
    n = int(tokens or 0)
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M".replace(".0M", "M")
    if n >= 100_000:
        return f"{round(n / 1_000):,}k"
    if n >= 10_000:
        v = n / 1_000
        return f"{v:.1f}k".replace(".0k", "k")
    return f"{n:,}"


def _compact_rec_line(rule: str, message: str, ctx_pct=None) -> str:
    """One short hook nudge. Full recommendation text belongs in status/why."""
    if rule == "fresh_handoff":
        if ctx_pct is not None and ctx_pct < CONTEXT_WARN_PCT:
            return "  ·  long session: /mr-handoff at phase boundary"
        return "  ·  fresh handoff: run /mr-handoff before more work"
    labels = {
        "retry_loop": "retry loop: inspect failing tool calls",
        "huge_tool_output": "huge output: offload or summarize",
        "repeated_context": "repeated context: compact repeated blocks",
        "re_read_loop": "re-read loop: keep one result or narrow the read",
        "step_runaway": "step runaway: re-plan the approach",
        "context_rot": "context rot: handoff at phase boundary",
    }
    if rule in labels:
        return "  ·  " + labels[rule]
    short = message[:90] + "..." if len(message) > 90 else message
    return f"  ·  [{rule}] {short}"


def _pick_high_recommendation(conn, session_id: str, ctx_pct=None):
    rows = conn.execute("""
        SELECT r.rule, r.message FROM recommendation r
        JOIN trace t ON t.id = r.trace_id
        WHERE t.session_id=? AND r.severity='high'
    """, (session_id,)).fetchall()
    if not rows:
        return None

    def score(row):
        rule = row[0]
        if rule == "fresh_handoff" and ctx_pct is not None and ctx_pct < CONTEXT_WARN_PCT:
            return 30
        return {
            "retry_loop": 0,
            "huge_tool_output": 1,
            "fresh_handoff": 2,
            "repeated_context": 3,
            "re_read_loop": 4,
            "step_runaway": 5,
        }.get(rule, 20)

    return sorted(rows, key=score)[0]


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


def find_codex_rollout(payload: dict) -> str | None:
    """Locate the just-finished Codex rollout for this session. Prefer an explicit
    path in the payload; else match the session_id in a rollout filename. No blind
    'newest' fallback — so a Claude session whose transcript is merely late can't be
    misread as Codex."""
    for k in ("rollout_path", "transcript_path", "session_file", "path"):
        p = payload.get(k)
        if isinstance(p, str) and p.endswith(".jsonl") and "/.codex/" in p and os.path.exists(p):
            return p
    sid = payload.get("session_id") or ""
    if sid:
        for base in CODEX_DIRS:
            hits = glob.glob(os.path.join(base, "**", f"*{sid}*.jsonl"), recursive=True)
            if hits:
                return hits[0]
    return None


def _load_payload() -> dict:
    raw = sys.stdin.read().strip()
    try:
        if raw:
            return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # hedge: some hook protocols pass the event JSON as an argv instead of stdin
    for arg in sys.argv[1:]:
        try:
            d = json.loads(arg)
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def main():
    payload = _load_payload()

    session_id = payload.get("session_id", "")
    paths = find_transcripts(session_id) if session_id else []
    codex_path = find_codex_rollout(payload) if not paths else None
    if not paths and not codex_path:
        # nothing to ingest (no Claude transcript, no matching Codex rollout)
        sys.exit(0)

    try:
        from mrtoken.ingest import connect, default_db_path, ingest_file, load_prices
        from mrtoken.rules import analyse

        prices = load_prices()
        # Codex sessions sprawl across many working dirs → aggregate them in ONE
        # central DB; Claude stays per-project. MRTOKEN_DB overrides either.
        if codex_path:
            from mrtoken.datadir import codex_db_path
            db = os.environ.get("MRTOKEN_DB") or codex_db_path()
        else:
            db = os.environ.get("MRTOKEN_DB") or default_db_path(payload.get("cwd"))
        conn = connect(db)
        totals = {"model_calls": 0, "tool_calls": 0, "recs": 0, "high": 0}

        codex_iv = None  # Codex live intervention (proc engine), if it fires
        codex_usage = None
        if codex_path:
            # Codex session: parse the rollout via the Codex adapter (source='codex')
            from mrtoken.ingest_codex import ingest_codex_file, codex_usage_snapshot
            codex_usage = codex_usage_snapshot(codex_path)
            r = ingest_codex_file(conn, codex_path, prices)
            if not r.get("skipped"):
                row = conn.execute("SELECT id FROM trace WHERE session_id=?",
                                   (r["session_id"],)).fetchone()
                if row:
                    recs = analyse(conn, row[0])
                    totals["model_calls"] += r["model_calls"]
                    totals["tool_calls"]  += r["tool_calls"]
                    totals["recs"]        += len(recs)
                    totals["high"]        += sum(1 for rc in recs if rc["severity"] == "high")
                    session_id = r["session_id"]  # for the rec-line query below
                    # proc engine for Codex: live ctx % from the rollout + fired signals
                    try:
                        from mrtoken.intervene import decide
                        cpct = (codex_usage or {}).get("ctx_pct")
                        if cpct is not None:
                            codex_iv = decide(session_id, cpct, None,
                                              [rc["rule"] for rc in recs])
                    except Exception:
                        codex_iv = None
        else:
            for path in paths:
                parent = path.split(os.sep)[-3] if "subagents" in path else None
                r = ingest_file(conn, path, prices, parent_session_id=parent)
                if r.get("skipped"):
                    continue  # near-empty session not persisted; nothing to analyse
                row = conn.execute(
                    "SELECT id FROM trace WHERE session_id=?", (r["session_id"],)
                ).fetchone()
                if not row:
                    continue
                tid = row[0]
                recs = analyse(conn, tid)
                totals["model_calls"] += r["model_calls"]
                totals["tool_calls"]  += r["tool_calls"]
                totals["recs"]        += len(recs)
                totals["high"]        += sum(1 for rc in recs if rc["severity"] == "high")

        # Build the HUD line for the just-finished turn (context %, cost, profile,
        # top signal). The Stop hook fires per-turn in the desktop app, so this is
        # our live status surface there.
        hud = None
        if codex_path:
            # Codex HUD from the rollout's own metrics (build_statusline_text is
            # Claude-transcript-specific and would leak a Claude session's stats).
            row = conn.execute("SELECT profile, total_tokens, est_cost_usd, cache_hit_ratio "
                               "FROM session_summary WHERE session_id=?", (session_id,)).fetchone()
            mdl = conn.execute(
                "SELECT mc.model FROM model_call mc JOIN trace t ON t.id=mc.trace_id "
                "WHERE t.session_id=? AND mc.model IS NOT NULL LIMIT 1", (session_id,)).fetchone()
            if row:
                profile, tot, cost, cache = row
                model = (codex_usage or {}).get("model") or (mdl[0] if mdl else None)
                identity = "codex" + (f" {model}" if model else "")
                parts = ["mr", identity]
                ctx_pct = (codex_usage or {}).get("ctx_pct")
                if ctx_pct is not None:
                    parts.append(f"ctx {int(ctx_pct)}%{' ⚠' if int(ctx_pct) >= CONTEXT_WARN_PCT else ''}")
                if tot:
                    parts.append(f"~{_fmt_token_count(tot)} tok")
                if cache is not None:
                    parts.append(f"cache {cache:.0%}")
                if cost and cost >= 0.01:
                    parts.append(f"~${cost:.2f}")
                if profile:
                    parts.append(profile)
                hud = " · ".join(parts)
        else:
            try:
                from mrtoken.statusline import build_statusline_text
                hud = build_statusline_text(session_id)
            except Exception:
                hud = None

        # Append the top high-priority recommendation, if any.
        rec_line = ""
        if totals["high"]:
            first_high = _pick_high_recommendation(
                conn, session_id, (codex_usage or {}).get("ctx_pct") if codex_path else None)
            if first_high:
                rule, msg = first_high
                rec_line = _compact_rec_line(
                    rule, msg, (codex_usage or {}).get("ctx_pct") if codex_path else None)

        # cost-gated Assist suggestion (opt-in via MRTOKEN_ASSIST; silent otherwise)
        assist_line = ""
        try:
            from mrtoken.assist import assist_suggestion
            main = conn.execute(
                "SELECT id FROM trace WHERE session_id=? AND source IN ('claude_code','codex')",
                (session_id,)).fetchone()
            if main:
                s = assist_suggestion(conn, main[0])
                if s:
                    assist_line = "  ·  " + s
        except Exception:
            pass

        # a fired Codex intervention (proc engine) takes the rec slot — it's the
        # actionable nudge, not just a passive signal.
        if codex_iv:
            rec_line = "  ·  " + codex_iv["message"]
        message = (hud or f"mr · {totals['model_calls']} calls") + rec_line + assist_line
        # passive "update available" nudge (throttled once/day, silent on failure)
        try:
            from mrtoken.update_check import check_for_update
            nudge = check_for_update()
            if nudge:
                message += "  ·  " + nudge
        except Exception:
            pass
        # Emit as a structured systemMessage (renders in the terminal CLI; the
        # desktop GUI app runs the hook for ingestion but does not surface this).
        print(json.dumps({"systemMessage": message}))

    except Exception as e:
        # never crash Claude Code — silent fail, log to stderr
        print(f"mrtoken hook error: {e}", file=sys.stderr)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
