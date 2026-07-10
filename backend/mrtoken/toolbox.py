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
        "files). Use when context is deep/bloated and continuing is expensive."),
    "inputSchema": {"type": "object", "properties": {
        "session": {"type": "string", "description": "session id/prefix (default: current/newest)"}}},
}


def _handoff_call(args: dict) -> str:
    return build_handoff(None, args.get("session"))


COMPACT_TOOL = {
    "name": "compact",
    "description": (
        "Advisory: when context is heavy but you want to keep going in THIS session, compact it. "
        "Returns the recommendation + the instruction to run your host's compaction. NOTE: the "
        "actual compaction is a host action you perform (e.g. /compact in Claude Code) — this tool "
        "advises and justifies it; if the bulk is one huge output, prefer `offload` or `handoff`."),
    "inputSchema": {"type": "object", "properties": {}},
}


def _compact_call(args: dict) -> str:
    return ("Context is heavy — compact to keep working in this session.\n"
            "• Claude Code: run /compact.  • Codex: use your context-compaction command.\n"
            "If the bulk is a single huge output, `offload` it instead; if you're deep into a long "
            "task, `handoff` to a fresh session is usually cheaper than compacting.")


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
    from mrtoken.intervene import AmbiguousSessionError, record_disposable_confirmation
    try:
        sid, call = record_disposable_confirmation(args.get("session"))
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
