#!/usr/bin/env python3
"""MR Token — minimal MCP stdio server (ROADMAP 6.1).

Exposes the toolbox to any MCP client — Claude Code AND Codex both speak MCP, so
one server equips both agents. Hand-rolled JSON-RPC 2.0 over newline-delimited
stdio (the MCP stdio transport): zero dependencies, keeping the backend pure-stdlib.

Run it:  mrtoken-transcript mcp     (this is the command you register with each agent)

Register (see docs/MCP.md):
  Claude Code:  claude mcp add mrtoken -- mrtoken-transcript mcp
  Codex:        [mcp_servers.mrtoken]  command="mrtoken-transcript"  args=["mcp"]

Tools: `offload`, `handoff`, `compact` (advisory), `confirm_disposable`. The registry in
toolbox.py is the source of truth; per-tool toggling via MRTOKEN_TOOLS_OFF lives there too.
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
    # PRESENCE, not truthiness (both here and for `arguments` below). `x or {}` makes a
    # PRESENT-but-invalid value indistinguishable from an ABSENT one, and every tool
    # downstream then falls back to server-side defaults — e.g. the environment's session,
    # which in an MCP server names the SERVER's session, not the caller's. A malformed
    # call must fail, not quietly resolve to someone else's state.
    # PRESENCE, not `.get(...) is None`: `.get` returns None for BOTH key-absent and
    # key-present-with-JSON-null, so testing `is None` is the same collapse one more time.
    # `"params" not in req` is the only test that separates "no params" from "params: null".
    if "params" not in req:
        params = {}
    else:
        raw_params = req["params"]
        if not isinstance(raw_params, dict):
            if mid is None:
                return None
            return _error(mid, -32602, "invalid params: `params` must be an object")
        params = raw_params

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
        # An ABSENT `arguments` legitimately means "no arguments" -> {}. A PRESENT
        # non-object is a malformed call and is rejected here, at the boundary, so
        # offload / handoff / confirm_disposable are covered too — per-tool checks
        # would not have been.
        if "arguments" in params:
            raw_args = params["arguments"]
            if not isinstance(raw_args, dict):
                if mid is None:
                    return None
                return _error(mid, -32602,
                              "invalid params: `arguments` must be an object")
            args = raw_args
        else:
            args = {}
        return _result(mid, _call_tool(name, args))
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
