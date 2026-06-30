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

`mrtoken-transcript init` registers the Mr Token MCP server for Codex when
`~/.codex` exists. `mrtoken-transcript doctor` verifies the Codex MCP section, so
hooks/skills can no longer look healthy while the `offload` tool is unavailable.

**Claude Code:**
```bash
claude mcp add mrtoken -- mrtoken-transcript mcp
```
(or add to `.mcp.json` / settings: a server named `mrtoken`, command `mrtoken-transcript`, args `["mcp"]`.)

**Codex manual recovery** — add to `~/.codex/config.toml`:
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

## Plug-and-play modules (ROADMAP 7.2, groundwork)
Register an *external* token-saver (e.g. headroom's MCP server) as a Mr Token module so it
flows through the same toggle + measurement machinery:
```bash
mrtoken-transcript modules --add headroom --command headroom --arg mcp   # register
mrtoken-transcript modules --register headroom                           # print Claude/Codex snippet
mrtoken-transcript modules --disable headroom                            # toggle off
```
A module's savings show in `mrtoken-transcript savings` once recorded under its name. NOTE:
the registry declares + toggles modules and emits registration; it does **not** vendor, run, or
trust external code — actually wiring + measuring headroom/ponytail is the gated 7.3 (dep/trust review).

## Notes
- Stash lives under the central store: `~/.mrtoken/data/offload/<hash>.txt`. Local only,
  never sent anywhere (privacy invariant holds).
- Protocol: JSON-RPC 2.0 over newline-delimited stdio; the server echoes the client's
  requested `protocolVersion`. Implemented in `mrtoken/mcp_server.py`; the `offload`
  capability is a plain function in `mrtoken/offload.py` (testable without the transport).
