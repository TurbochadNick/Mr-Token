#!/usr/bin/env python3
"""MR Token — fresh-handoff generator (the one assistive action).

When a session has grown bloated, the cheapest fix is to start a NEW session
with a compact handoff summary. This builds that summary from data we already
have — deterministically, NO AI call in v1:

  • Goal            — session title, else the first user prompt
  • Current task    — the most recent user request
  • Changed files   — file paths from Edit/Write/MultiEdit/NotebookEdit calls
  • Recent commands — last few Bash commands (truncated)
  • Open signals    — recommendations the rule engine fired for this session
  • Cost so far     — real tokens + API-equivalent estimate

The result is PRINTED for the user to review and paste into a fresh session.
Content (paths, prompts, commands) is read on demand and never persisted — the
ledger stays metadata-only.

(An optional `--polish` step that sends this to an LLM to tighten it is the
natural paid enhancement; the seam is marked below but not implemented in v1.)
"""
from __future__ import annotations
import json, os

from mrtoken.ingest import connect, load_prices, ingest_file, default_db_path
from mrtoken.rules import analyse
from mrtoken.watch import resolve_path

EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit"}
MAX_FILES = 15
MAX_COMMANDS = 6
PROMPT_CHARS = 280
CMD_CHARS = 100


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _truncate(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _scan_transcript(path: str) -> dict:
    """Pull the human-meaningful detail a handoff needs (content, on demand)."""
    title = first_prompt = last_prompt = None
    changed: list[str] = []
    seen_files: set[str] = set()
    commands: list[str] = []

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = o.get("type")
            msg = o.get("message") if isinstance(o.get("message"), dict) else {}

            if etype in ("custom-title", "ai-title") and not title:
                title = o.get("title") or o.get("text")

            if etype == "assistant":
                for b in (msg.get("content") or []):
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name = (b.get("name") or "").lower()
                    inp = b.get("input") or {}
                    if name in EDIT_TOOLS:
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if fp and fp not in seen_files:
                            seen_files.add(fp); changed.append(fp)
                    elif name == "bash" and inp.get("command"):
                        commands.append(_truncate(inp["command"], CMD_CHARS))

            elif etype == "user":
                content = msg.get("content") if msg else o.get("content")
                # skip tool-result-only user turns; keep real prompts
                if isinstance(content, list) and all(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue
                txt = _text(content) if isinstance(content, list) else (content or "")
                txt = txt.strip()
                if txt:
                    if not first_prompt:
                        first_prompt = txt
                    last_prompt = txt

    return {"title": title, "first_prompt": first_prompt, "last_prompt": last_prompt,
            "changed_files": changed, "commands": commands[-MAX_COMMANDS:]}


def build_handoff(db_path: str | None, session_arg: str | None) -> str:
    path = resolve_path(session_arg)
    if not path:
        return "mrtoken handoff: no transcript found for this project"

    db_path = db_path or default_db_path()
    conn = connect(db_path)
    prices = load_prices()
    parent = path.split(os.sep)[-3] if "subagents" in path else None
    r = ingest_file(conn, path, prices, parent_session_id=parent)
    sid = r["session_id"]
    tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (sid,)).fetchone()[0]
    analyse(conn, tid)

    s = _scan_transcript(path)
    summary = conn.execute(
        "SELECT profile, model_calls, total_tokens, est_cost_usd, cache_hit_ratio, "
        "tool_calls, tool_errors FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
    profile, calls, total_tok, cost, cache, tools, errs = summary or (None,)*7
    recs = conn.execute(
        "SELECT rule, severity, message FROM recommendation WHERE trace_id=? "
        "ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END", (tid,)).fetchall()

    goal = _truncate(s["title"] or s["first_prompt"] or "(state the goal)", PROMPT_CHARS)
    out = []
    out.append(f"# Handoff — continue in a fresh session\n")
    out.append(f"_Session {sid[:8]} · profile: {profile or 'unknown'} · "
               f"{calls or 0} model calls · ~{(total_tok or 0):,} tokens · "
               f"est ${cost or 0:,.2f} (API-equivalent)_\n")

    out.append("## Goal")
    out.append(f"{goal}\n")

    if s["last_prompt"] and s["last_prompt"] != s["first_prompt"]:
        out.append("## Where I left off (most recent request)")
        out.append(f"{_truncate(s['last_prompt'], PROMPT_CHARS)}\n")

    if s["changed_files"]:
        out.append("## Files touched")
        for f in s["changed_files"][:MAX_FILES]:
            out.append(f"- `{f}`")
        if len(s["changed_files"]) > MAX_FILES:
            out.append(f"- …and {len(s['changed_files']) - MAX_FILES} more")
        out.append("")

    if s["commands"]:
        out.append("## Recent commands")
        for c in s["commands"]:
            out.append(f"- `{c}`")
        out.append("")

    if recs:
        # collapse repeats by rule — a handoff should be tight, not a rule dump
        by_rule: dict[str, dict] = {}
        for rule, sev, message in recs:
            slot = by_rule.setdefault(rule, {"sev": sev, "message": message, "count": 0})
            slot["count"] += 1
        out.append("## Why start fresh (open signals)")
        for rule, slot in sorted(
                by_rule.items(),
                key=lambda kv: {"high": 0, "warn": 1, "info": 2}.get(kv[1]["sev"], 3))[:5]:
            times = f" (×{slot['count']})" if slot["count"] > 1 else ""
            out.append(f"- **{rule}**{times} ({slot['sev']}): {slot['message']}")
        out.append("")

    out.append("## Carry into the new session")
    out.append("- The goal and most recent request above")
    out.append("- The files touched (re-open only the ones still in play)")
    out.append("- Any decisions/constraints not captured here — add them before you paste\n")

    # --- SEAM: optional LLM polish (paid tier) would rewrite the above here ---

    return "\n".join(out)
