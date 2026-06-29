# Security Notes

## Local First

The Python backend beta runs locally and does not send telemetry or source code
anywhere by default. The core rule engine is deterministic and does not call an
LLM.

## Localhost UI

The optional TypeScript UI binds to `127.0.0.1`, not `0.0.0.0`.

## No Arbitrary Shell Execution

The optional UI does not expose an endpoint for arbitrary shell commands.

The Python MCP toolbox exposes specific local tools such as `offload`,
`handoff`, and advisory `compact`; it does not provide a generic shell tool.

## Write Scope

The current backend beta may write to:

- `.token-tithe/`
- `~/.mrtoken/data/`
- `~/.claude/settings.json`
- `~/.claude/skills/`
- `~/.codex/skills/` when `~/.codex/` exists
- `~/.codex/hooks.json` when `~/.codex/` exists

The TypeScript dashboard path may also write to:

- `.token-tithe/events.jsonl`
- `.token-tithe/patches/`
- `.claude/settings.local.json`

## Patch Safety

Doctor generates patch proposals only. It never applies patches automatically.

## Network Behavior

No network call is made by the Python backend beta's always-on detection path.

Optional network paths:

- the TypeScript `mrtoken`/`token-tithe` commands verify license keys for
  license-gated commands;
- optional AI audit review uses Anthropic only when explicitly enabled and
  configured with `ANTHROPIC_API_KEY`;
- external MCP/token-saver modules are opt-in and need their own privacy review.

## Known Alpha Risks

- Hook payloads can contain file paths, commands, and snippets of tool output.
- Diagnosis is heuristic and may produce false positives.
- Users should review backed-up settings changes before using the tool in
  sensitive repositories.
