#!/usr/bin/env python3
"""MR Token — the agent toolbox registry (ROADMAP 6.2).

One registry of the tools the agent can call (exposed over MCP by mcp_server.py).
Each tool is {schema, call}. Per-tool toggling lives here too, so the MCP server
and (later) the proc engine share one source of truth. 6.5 extends `tool_enabled`
into the full per-tool autonomy config (off/tell/ask/do); for now it's on/off via
the MRTOKEN_TOOLS_OFF env (comma-separated tool names).

Honesty note: `offload` and `handoff` genuinely *do* something from here; `compact`
is **advisory** — compaction is a host operation the agent performs (`/compact`),
so the tool returns the situation + instruction rather than executing it.
"""
from __future__ import annotations
import json
import os

from mrtoken.offload import OFFLOAD_TOOL, offload_content
from mrtoken.handoff import build_handoff


def _offload_call(args: dict) -> str:
    r = offload_content(content=args.get("content"), path=args.get("path"),
                        query=args.get("query"), max_lines=args.get("max_lines", 40))
    try:  # log realized savings for the report (7.1); never break the tool
        from mrtoken import savings
        savings.record("offload", r["est_tokens_saved"])
    except Exception:
        pass
    return (r["summary"] + f"\n\n[stashed full output → {r['stash_path']} · "
            f"~{r['est_tokens_saved']:,} tokens kept out of context]")


HANDOFF_TOOL = {
    "name": "handoff",
    "description": (
        "Generate a compact handoff for the current session so you can start a FRESH session and "
        "drop the accumulated context. Returns markdown (goal, key decisions, last state, changed "
        "files). Use when context is deep/bloated AND the loaded context is no longer needed for "
        "the remaining work; resetting context you will re-read costs more than continuing "
        "(measured +20% on load-bearing context)."),
    "inputSchema": {"type": "object", "properties": {
        "session": {"type": "string", "description": (
            "session id (default: the caller's own session from MRTOKEN_SESSION / "
            "CLAUDE_CODE_SESSION_ID; refused if unknown)")}}},
}


def _handoff_call(args: dict) -> str:
    """The `session` field is a tool-caller-supplied ID, not a path — but the old code
    passed the raw string to build_handoff, which passes it to resolve_path, which returns
    any real file. A caller could therefore hand over a filesystem path despite the
    schema's contract and get its CONTENT back. Resolve it through the UNTRUSTED,
    project-local resolver, then hand build_handoff that transcript's session id (matched
    exactly against the store) together with the ALREADY-VERIFIED path.

    An omitted `session` is the caller's own session from the environment, resolved
    project-locally. There is no newest-transcript fallback: on a shared project the
    newest transcript can be another seat's.
    """
    from mrtoken.watch import resolve_session_local
    args = args if isinstance(args, dict) else {}
    if "session" not in args:                       # presence, not truthiness
        caller = os.environ.get("MRTOKEN_SESSION") or os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not caller:
            return ("mrtoken handoff: the caller's own session cannot be determined (no "
                    "MRTOKEN_SESSION or CLAUDE_CODE_SESSION_ID). Pass `session: <your session "
                    "id>` (Bash: `echo $CLAUDE_CODE_SESSION_ID`).")
        path = resolve_session_local(caller)
        if not path:
            return ("mrtoken handoff: no transcript in THIS project matches the caller's "
                    "session. Pass `session: <your session id>` for a session in this project.")
    else:
        path = resolve_session_local(args["session"])
        if not path:
            return ("mrtoken handoff: no transcript in THIS project matches that session id. "
                    "Pass the session id of a session in this project "
                    "(Bash: `echo $CLAUDE_CODE_SESSION_ID`); a path is not accepted.")
    sid = os.path.basename(path)[:-len(".jsonl")]
    return build_handoff(None, sid, exact=True, transcript_path=path)


# Context OCCUPANCY at or above this share of the window reads as HEAVY. Named so the
# threshold is quotable in the response instead of buried as a magic number. Matches
# statusline.CONTEXT_WARN_PCT so the tool and the HUD can never disagree about "heavy".
COMPACT_HEAVY_PCT = 70

# A transcript not written within this window is STALE: it may not reflect the session
# the caller is actually in, so it measures UNKNOWN rather than being reported as current.
COMPACT_STALE_AFTER_S = 10 * 60

COMPACT_TOOL = {
    "name": "compact",
    "description": (
        "Advisory: measures THIS session's context occupancy and reports HEAVY / NOT_HEAVY / "
        "UNKNOWN, then — only when heavy — recommends compaction. NOTE: the actual compaction is "
        "a host action you perform (e.g. /compact in Claude Code); this tool measures and advises. "
        "Pass `session` (or set MRTOKEN_SESSION / CLAUDE_CODE_SESSION_ID): without an explicit "
        "binding the measurement is UNKNOWN — this tool never guesses which session you are in."),
    "inputSchema": {"type": "object", "properties": {
        "session": {"type": "string",
                    "description": "session id (default: MRTOKEN_SESSION / CLAUDE_CODE_SESSION_ID)"}}},
}


def _compact_transcript_for(session: str) -> "str | tuple[None, str]":
    """Resolve an untrusted session id through THE single project-local resolver.

    This previously ran its own `PROJECTS/*/<id>.jsonl` search: spelling-validated and
    globally unique, but never bound to the CALLER'S project — so a foreign project's exact
    session id resolved and its occupancy was reported back. Uniqueness is not authorisation.
    There is now exactly one untrusted lookup and every tool uses it.
    """
    from mrtoken.watch import resolve_session_local, valid_session_id
    if not valid_session_id(session):
        return None, "session id is missing or unsafe"
    path = resolve_session_local(session)
    if not path:
        return None, "no transcript in THIS project matches that session id"
    return path



def _compact_measure(session, explicit: bool = False) -> dict:
    """Provider-reported context occupancy for one session. Metadata only.

    OCCUPANCY, not throughput: the current context size is the LAST turn's input side,
    not the sum over turns. Summing would grow forever and call every long session heavy
    even straight after a compaction actually emptied it.

    Dedup by message id is mandatory: transcript lines repeat the same assistant message
    (observed up to 4x), and the inflation differs BY FIELD, so it does not cancel out.
    """
    import time
    # Only an ABSENT binding is "no binding". A session the caller supplied explicitly —
    # even "" / None / 0 / False / [] / {} — is their stated intent and must be validated,
    # not silently replaced by the environment.
    if not explicit and not session:
        return {"verdict": "UNKNOWN",
                "reason": "no session binding (pass `session`, or set MRTOKEN_SESSION / "
                          "CLAUDE_CODE_SESSION_ID)"}
    resolved = _compact_transcript_for(session)
    if isinstance(resolved, tuple):
        return {"verdict": "UNKNOWN", "reason": resolved[1]}
    path = resolved
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return {"verdict": "UNKNOWN", "reason": "transcript is unreadable"}
    if age > COMPACT_STALE_AFTER_S:
        return {"verdict": "UNKNOWN",
                "reason": f"transcript is stale (last written {int(age // 60)} min ago)"}

    fields = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    seen, last, peak = set(), None, 0
    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage") or obj.get("usage")
                if not isinstance(usage, dict):
                    continue
                if not any(k in usage for k in fields):
                    continue
                key = msg.get("id") or obj.get("requestId")
                if key is None or key in seen:
                    continue
                seen.add(key)
                occ = sum(v for v in (usage.get(f) for f in fields) if isinstance(v, int))
                last = occ
                peak = max(peak, occ)
    except OSError:
        return {"verdict": "UNKNOWN", "reason": "transcript is unreadable"}

    if last is None:
        # absent usage is NOT a measured zero
        return {"verdict": "UNKNOWN", "reason": "no provider-reported usage in that transcript"}

    from mrtoken.statusline import context_window
    window = context_window(peak)
    pct = (last / window * 100) if window else 0
    return {"verdict": "HEAVY" if pct >= COMPACT_HEAVY_PCT else "NOT_HEAVY",
            "occupancy_tokens": last, "window": window, "pct": round(pct, 1),
            "turns": len(seen), "threshold_pct": COMPACT_HEAVY_PCT,
            "provenance": "measured (provider-reported, deduped by message id)"}


def _compact_call(args: dict) -> str:
    from mrtoken.intervene import _caller_session_env
    # Defence in depth, and NOT a normalization: a non-dict container is malformed, not
    # empty. Collapsing it to {} here would re-create the very fallthrough the boundary
    # check now prevents — the same `or {}` / `else {}` semantic collapse, third spelling.
    if not isinstance(args, dict):
        return ("Context occupancy: UNKNOWN — malformed tool arguments (expected an object).\n"
                "No compaction is recommended on this basis, because nothing was measured.")
    # PRESENCE, not truthiness. `args.get("session") or env` conflated key-absent with
    # key-present-but-falsey, so an explicit "" / None / 0 / False / [] / {} fell through
    # to the environment. In an MCP server that environment names the SERVER's session,
    # not the caller's — so an invalid explicit binding silently measured, and reported,
    # a DIFFERENT session. The env fallback is correct ONLY when the key is absent.
    explicit = "session" in args
    session = args["session"] if explicit else _caller_session_env()
    m = _compact_measure(session, explicit=explicit)
    v = m["verdict"]

    if v == "UNKNOWN":
        # An absent measurement must never read as a positive one.
        return ("Context occupancy: UNKNOWN — " + m["reason"] + ".\n"
                "No compaction is recommended on this basis, because nothing was measured. "
                "This is not a statement that context is light; it is the absence of a "
                "measurement. Re-call with `session: <your session id>` "
                "(Bash: `echo $CLAUDE_CODE_SESSION_ID`) to get a real reading.")

    head = (f"Context occupancy: {v} — {m['occupancy_tokens']:,} tok of a "
            f"{m['window']:,} window ({m['pct']}%), threshold {m['threshold_pct']}%, "
            f"measured over {m['turns']} deduped turns.")

    if v == "NOT_HEAVY":
        return (head + "\n"
                "Compaction is NOT indicated — you are below the threshold. Compacting now "
                "would drop context you may still need without relieving pressure that the "
                "measurement does not show.")

    return (head + "\n"
            "• Claude Code: run /compact.  • Codex: use your context-compaction command.\n"
            "If the bulk is a single huge output, `offload` it instead. Any reset (compact or "
            "handoff) only pays if the dropped context won't be needed again; if you'll re-read "
            "it, continuing is cheaper. Compact vs handoff is a workflow choice (stay here vs "
            "fresh session), not a cost one; measured costs are about the same.")


CONFIRM_DISPOSABLE_TOOL = {
    "name": "confirm_disposable",
    "description": (
        "Confirm that the large context loaded in THIS session is no longer needed for the remaining "
        "work — i.e. it is safe to drop via handoff/compact. Call this ONLY after actually checking "
        "what the remaining task needs; Mr Token's automatic recency heuristic cannot tell whether "
        "you'll re-open those refs. A fresh confirmation lets Mr Token propose a reset beyond an "
        "advisory nudge; it expires as the session moves on. No content is stored — only a timestamp "
        "and the current turn index."),
    "inputSchema": {"type": "object", "properties": {
        "session": {"type": "string", "description": (
            "session id/prefix. Optional for one active session; required if multiple "
            "sessions are active in this project.")}}},
}


def _confirm_disposable_call(args: dict) -> str:
    """PRESENCE, not truthiness — and unlike `handoff`, this one WRITES.

    `args.get("session")` lost key presence, so an explicit-but-invalid session (notably
    "") fell through `_session_calls`' `not session_arg` test to the one-recent-session
    default, and `record_disposable_confirmation` then persisted a disposal confirmation
    against a session the caller never named. A read binding to the wrong session is bad;
    a WRITE to it is worse. Only an ABSENT key may use the default.
    """
    from mrtoken.intervene import AmbiguousSessionError, record_disposable_confirmation
    from mrtoken.watch import valid_session_id
    args = args if isinstance(args, dict) else {}
    session = None
    if "session" in args:
        session = args["session"]
        if not valid_session_id(session):
            return ("confirm_disposable: invalid session id — nothing recorded. Pass a "
                    "valid session id, or omit `session` to use this project's single "
                    "active session.")
    try:
        sid, call = record_disposable_confirmation(session)
    except AmbiguousSessionError as e:
        return str(e)
    if not sid:
        return "no active session transcript found — nothing recorded."
    return (f"recorded: loaded context marked disposable for session {sid[:8]} (turn {call}). "
            "Mr Token may now propose a handoff/compact reset; this confirmation expires as the "
            "session continues, so re-confirm if you're still safe to drop later.")


TOOL_REGISTRY = {
    "offload": {"schema": OFFLOAD_TOOL, "call": _offload_call},
    "handoff": {"schema": HANDOFF_TOOL, "call": _handoff_call},
    "compact": {"schema": COMPACT_TOOL, "call": _compact_call},
    "confirm_disposable": {"schema": CONFIRM_DISPOSABLE_TOOL, "call": _confirm_disposable_call},
}


def tool_enabled(name: str) -> bool:
    off = {t.strip() for t in os.environ.get("MRTOKEN_TOOLS_OFF", "").split(",") if t.strip()}
    return name not in off


def enabled_tool_schemas() -> list[dict]:
    return [d["schema"] for n, d in TOOL_REGISTRY.items() if tool_enabled(n)]


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    """Run a tool by name. Returns (text, is_error)."""
    if not tool_enabled(name):
        return f"tool '{name}' is disabled (MRTOKEN_TOOLS_OFF)", True
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return f"unknown tool: {name}", True
    try:
        return entry["call"](args), False
    except Exception as e:
        return f"{name} error: {e}", True
