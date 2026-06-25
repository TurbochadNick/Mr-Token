#!/usr/bin/env python3
"""MR Token — minimal MCP stdio server (ROADMAP 6.1).

Exposes the toolbox to any MCP client — Claude Code AND Codex both speak MCP, so
one server equips both agents. Hand-rolled JSON-RPC 2.0 over newline-delimited
stdio (the MCP stdio transport): zero dependencies, keeping the backend pure-stdlib.

Run it:  mrtoken-transcript mcp     (this is the command you register with each agent)

Register (see docs/MCP.md):
  Claude Code:  claude mcp add mrtoken -- mrtoken-transcript mcp
  Codex:        [mcp_servers.mrtoken]  command="mrtoken-transcript"  args=["mcp"]

Tools: `offload` (more land here as Phase 6 proceeds: handoff, compact, …).
"""
from __future__ import annotations
import json, sys

from mrtoken import __version__
from mrtoken.toolbox import enabled_tool_schemas, call_tool

PROTOCOL_VERSION = "2024-11-05"


def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _call_tool(name: str, args: dict) -> dict:
    """Dispatch a tools/call through the toolbox registry → MCP result shape."""
    text, is_error = call_tool(name, args)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle_request(req: dict):
    """Handle one JSON-RPC request. Returns a response dict, or None for notifications."""
    mid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "initialize":
        pv = params.get("protocolVersion") or PROTOCOL_VERSION  # echo the client's version
        return _result(mid, {"protocolVersion": pv,
                             "capabilities": {"tools": {}},
                             "serverInfo": {"name": "mrtoken", "version": __version__}})
    if method in ("notifications/initialized", "initialized"):
        return None  # notification, no reply
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": enabled_tool_schemas()})
    if method == "tools/call":
        name = params.get("name")
        return _result(mid, _call_tool(name, params.get("arguments") or {}))
    if mid is not None:
        return _error(mid, -32601, f"method not found: {method}")
    return None  # unknown notification


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
