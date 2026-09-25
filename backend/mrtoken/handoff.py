#!/usr/bin/env python3
"""MR Token — fresh-handoff generator (the one assistive action).

When a session has grown bloated, the cheapest fix is to start a NEW session
with a compact handoff summary. This builds that summary from data we already
have — deterministically, NO AI call in v1:

  • Goal            — session title, else the most recent substantive request
  • Current task    — the most recent user request
  • Changed files   — edited files that still exist on disk, most-recent first
  • Recent commands — last few Bash commands (truncated)
  • Open signals    — recommendations the rule engine fired for this session
  • Cost so far     — real tokens + verified-API estimate when available

The result is PRINTED for the user to review and paste into a fresh session.
Content (paths, prompts, commands) is read on demand and never persisted — the
ledger stays metadata-only.

(An optional `--polish` step that sends this to an LLM to tighten it is the
natural paid enhancement; the seam is marked below but not implemented in v1.)
"""
from __future__ import annotations
import json, os

from mrtoken.ingest import (CallerSessionRefused, ReadOnlyDatabaseError, SessionSelectionError,
                            connect_readonly, default_db_path, select_requested_session,
                            select_session)
from mrtoken.watch import resolve_path


def _attested_transcript(path: str, sid: str) -> str | None:
    """`path` only if it IS `sid`'s transcript in this project, else None.

    A caller-supplied path is not trusted to match the selected row: its name and its
    symlink-resolved file must both be `<sid>.jsonl`, and the resolved file must lie
    directly in this project's transcript directory."""
    from mrtoken import watch
    bucket = watch.project_bucket()
    if not bucket:
        return None
    expected_dir = os.path.realpath(os.path.join(watch.PROJECTS, bucket))
    real = os.path.realpath(path)
    name = f"{sid}.jsonl"
    if (os.path.basename(path) != name or os.path.basename(real) != name
            or os.path.dirname(real) != expected_dir or not os.path.isfile(real)):
        return None
    return real

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


def _is_substantive(txt: str) -> bool:
    """A real human request, not a transcript artifact. Filters compaction
    continuations, pasted handoffs, and slash-command / system wrappers so the
    Goal and 'where I left off' lines never latch onto machine noise."""
    t = (txt or "").strip()
    if not t:
        return False
    low = t.lower()
    if t.startswith("# Handoff"):
        return False
    if low.startswith("caveat: the messages below"):
        return False
    if "this session is being continued from a previous conversation" in low:
        return False
    if t.startswith("<command-") or t.startswith("<local-command"):
        return False
    if t.startswith("<system-reminder>") and t.endswith("</system-reminder>"):
        return False
    return True


def _scan_transcript(path: str) -> dict:
    """Pull the human-meaningful detail a handoff needs (content, on demand)."""
    custom_title = ai_title = first_prompt = last_prompt = None
    last_touch: dict[str, int] = {}   # file_path -> last edit index (recency order)
    commands: list[str] = []
    idx = 0

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

            # title lives under customTitle / aiTitle (not "title"); a human-set
            # custom title always wins, an ai-title only fills if none seen yet
            if etype == "custom-title":
                custom_title = (o.get("customTitle") or o.get("title")
                                or o.get("text") or custom_title)
            elif etype == "ai-title" and not ai_title:
                ai_title = o.get("aiTitle") or o.get("title") or o.get("text")

            if etype == "assistant":
                for b in (msg.get("content") or []):
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name = (b.get("name") or "").lower()
                    inp = b.get("input") or {}
                    if name in EDIT_TOOLS:
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if fp:
                            idx += 1
                            last_touch[fp] = idx   # keep most-recent touch order
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
                if txt and _is_substantive(txt):
                    if not first_prompt:
                        first_prompt = txt
                    last_prompt = txt

    # most-recently-touched first, keeping only files that still exist — drops
    # stale pre-migration / deleted paths so the list shows what's still in play
    changed = [fp for fp in sorted(last_touch, key=last_touch.get, reverse=True)
               if os.path.exists(fp)]
    return {"title": custom_title or ai_title, "custom_title": custom_title,
            "ai_title": ai_title,
            "first_prompt": first_prompt, "last_prompt": last_prompt,
            "changed_files": changed, "commands": commands[-MAX_COMMANDS:]}


def _codex_text(content) -> str:
    """Extract text from the user-message shapes emitted in a Codex rollout."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _codex_text(content.get("text") or content.get("content") or "")
    if isinstance(content, list):
        return "\n".join(_codex_text(part) for part in content)
    return ""


def _rollout_session_id(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("type") == "session_meta":
                    payload = item.get("payload") or {}
                    session_id = payload.get("session_id") or payload.get("id")
                    return session_id if isinstance(session_id, str) else None
                return None
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _find_codex_rollout(session_id: str, root: str | None = None) -> str | None:
    """Find only the rollout whose own session meta matches the selected DB row."""
    root = root or os.path.expanduser("~/.codex/sessions")
    if not os.path.isdir(root):
        return None
    for directory, _, names in os.walk(root):
        for name in names:
            if not name.endswith(".jsonl") or session_id not in name:
                continue
            path = os.path.join(directory, name)
            if _rollout_session_id(path) == session_id:
                return path
    return None


def _scan_codex_rollout(path: str) -> dict:
    """Read a selected Codex rollout on demand; never add its content to the DB."""
    first_prompt = last_prompt = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = item.get("payload") or {}
                role = payload.get("role")
                kind = payload.get("type")
                if item.get("type") == "response_item" and kind == "message" and role == "user":
                    text = _codex_text(payload.get("content")).strip()
                elif item.get("type") == "event_msg" and kind == "user_message":
                    text = _codex_text(payload.get("message") or payload.get("content")).strip()
                else:
                    continue
                if text and _is_substantive(text):
                    first_prompt = first_prompt or text
                    last_prompt = text
    except OSError:
        pass
    return {"title": None, "custom_title": None, "ai_title": None,
            "first_prompt": first_prompt, "last_prompt": last_prompt,
            "changed_files": [], "commands": []}


def goal_from_scan(s: dict) -> str:
    """The session's CURRENT goal, ranked. Extracted so it is testable on its own.

    A HUMAN-set custom title wins — a person chose it deliberately. An AI-generated title
    must NOT outrank current work: it is a session-START artifact that never refreshes.
    Measured on a real 830k-token session: 132 `ai-title` events, ONE distinct value,
    first == last, emitted early and unchanged all session, so the goal read
    "Environment validation session" ~24h and eight tasks after that stopped being true.
    An ai-title is still a better fallback than nothing.
    """
    return (s.get("custom_title") or s.get("last_prompt")
            or s.get("ai_title") or s.get("first_prompt")
            or "(state the goal)")


def build_handoff(db_path: str | None, session_arg: str | None, *,
                  source: str | None = None, codex_root: str | None = None,
                  exact: bool = False, transcript_path: str | None = None) -> str:
    """Render one already-recorded session without ingesting or changing its store.

    `exact` matches `session_arg` as a whole id, not a prefix. `transcript_path` is a
    transcript the caller has ALREADY verified for that id (the MCP tool resolves it
    project-locally); it is read instead of resolving the id again."""
    db_path = db_path or default_db_path()
    try:
        conn = connect_readonly(db_path)
    except ReadOnlyDatabaseError as exc:
        return str(exc)
    # An omitted id means the CALLER's own session: the newest row can be another seat's,
    # and its transcript would then be read into this seat's context.
    try:
        tid, sid, selected_source, profile = (
            select_session(conn, session_arg, source=source, exact=True)
            if exact and session_arg is not None else
            select_requested_session(conn, session_arg, source=source, command="handoff"))
    except (CallerSessionRefused, SessionSelectionError) as exc:
        conn.close()
        return str(exc)

    # Database selection is authoritative. A transcript is read only afterwards,
    # for on-demand handoff detail, and must attest to that already-selected id.
    if selected_source == "codex":
        path = _find_codex_rollout(sid, codex_root)
        s = _scan_codex_rollout(path) if path else {
            "title": None, "custom_title": None, "ai_title": None,
            "first_prompt": None, "last_prompt": None,
            "changed_files": [], "commands": []}
    else:
        if transcript_path is not None:
            path = _attested_transcript(transcript_path, sid)
            if path is None:
                conn.close()
                return (f"mrtoken: session unavailable: the supplied transcript does not "
                        f"attest to session {sid[:8]} in this project")
        else:
            path = resolve_path(sid)
        s = _scan_transcript(path) if path else {
            "title": None, "custom_title": None, "ai_title": None,
            "first_prompt": None, "last_prompt": None,
            "changed_files": [], "commands": []}

    summary = conn.execute(
        "SELECT model_calls, cumulative_expenditure_tokens, cumulative_expenditure_provenance, "
        "api_est_cost_usd, billing_mode FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
    calls, total_tok, total_provenance, api_cost, billing_mode = summary or (None,)*5
    from mrtoken.rules import advice_on  # rule-based "open signals" are switched off
    recs = [] if not advice_on() else conn.execute(
        "SELECT rule, severity, message FROM recommendation WHERE trace_id=? "
        "ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END", (tid,)).fetchall()

    # Goal anchors on the title, else the MOST RECENT substantive request — the
    # first prompt goes stale on long, multi-task, or multiply-compacted sessions.
    # A HUMAN-set custom title wins: a person chose it deliberately. An AI title must NOT
    # outrank current work — it is a session-START artifact that never refreshes. Measured
    # on a real 830k-token session: 132 `ai-title` events, ONE distinct value, first == last,
    # emitted early and re-emitted unchanged all session. Ranking it above `last_prompt`
    # made the goal ~24h and eight tasks stale.
    goal = _truncate(goal_from_scan(s), PROMPT_CHARS)
    out = []
    out.append(f"# Handoff — continue in a fresh session\n")
    chosen = "implicit caller session" if session_arg is None else "explicit"
    line = (f"_Session {sid[:8]} · source: {selected_source} · {chosen} · profile: {profile or 'unknown'} · "
            f"{calls or 0} model calls · "
            + (f"cumulative token total ~{total_tok:,} ({total_provenance})" if total_tok is not None else "UNKNOWN cumulative token total"))
    if billing_mode == "api" and api_cost is not None:
        line += f" · est API usage ${api_cost:,.2f}"
    out.append(line + "_\n")

    out.append("## Goal")
    out.append(f"{goal}\n")

    # only when it adds something beyond the Goal (e.g. Goal came from the title)
    if s["last_prompt"] and _truncate(s["last_prompt"], PROMPT_CHARS) != goal:
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

    # Declared continuation state — read for the ALREADY-RESOLVED session id, from THIS
    # project's store. Never consults the environment, never falls back to a newest session,
    # and renders every undeclared field as a NAMED GAP (see mrtoken/manifest.py).
    from mrtoken.manifest import load_manifest, verify_manifest, render_section
    m, load_err = load_manifest(sid)
    v = verify_manifest(m, sid, transcript_path=path) if m is not None else None
    out.extend(render_section(m, v, load_error=load_err))

    out.append("## Carry into the new session")
    out.append("- The goal and most recent request above")
    out.append("- The files touched (re-open only the ones still in play)")
    out.append("- The declared state above — fill every named gap or re-declare before you paste\n")

    # --- SEAM: optional LLM polish (paid tier) would rewrite the above here ---

    conn.close()
    return "\n".join(out)
