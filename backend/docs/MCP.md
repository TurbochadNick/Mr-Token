# Mr Token MCP server — the agent toolbox

`mrtoken-transcript mcp` runs a minimal MCP stdio server (zero deps, pure stdlib)
that exposes Mr Token's **toolbox** to any MCP client. Both Claude Code and Codex
speak MCP, so one server equips both agents.

## Tools (Phase 6 — growing)
- **`offload`** — stash a large tool output or file *out of context*: writes the full
  content to disk, returns a compact summary + a stash path you can grep/read later.
- **`handoff`** — generate a compact handoff for the current session so you can start a
  fresh one and drop the accumulated context.
- **`compact`** — *advisory*: returns the situation + the instruction to run your host's
  compaction (the actual compaction is a host action you perform).

Each tool is individually toggleable via `MRTOKEN_TOOLS_OFF` (comma-separated names);
full per-tool autonomy (off/tell/ask/do) lands in ROADMAP 6.5.

## Register it

**Claude Code:**
```bash
claude mcp add mrtoken -- mrtoken-transcript mcp
```
(or add to `.mcp.json` / settings: a server named `mrtoken`, command `mrtoken-transcript`, args `["mcp"]`.)

**Codex** — add to `~/.codex/config.toml`:
```toml
[mcp_servers.mrtoken]
command = "mrtoken-transcript"
args = ["mcp"]
```

Then start a session and the agent can call `offload(...)`. Verify with a quick
`tools/list` from the client, or the stdio smoke test:
```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | mrtoken-transcript mcp
```

## Notes
- Stash lives under the central store: `~/.mrtoken/data/offload/<hash>.txt`. Local only,
  never sent anywhere (privacy invariant holds).
- Protocol: JSON-RPC 2.0 over newline-delimited stdio; the server echoes the client's
  requested `protocolVersion`. Implemented in `mrtoken/mcp_server.py`; the `offload`
  capability is a plain function in `mrtoken/offload.py` (testable without the transport).
