# Privacy

Mr Token is local-first.

## Default Data Location

Events are written to:

- `.token-tithe/token-tithe.db`
- `.token-tithe/events.jsonl`

Claude hooks are written to:

- `.claude/settings.local.json`

Patch proposals are written to:

- `.token-tithe/patches/`

## No Backend

Mr Token does not include a hosted backend, login, billing, telemetry, or cloud sync.

## No Source Upload By Default

Mr Token does not upload source code by default. The local UI reads the local SQLite database through a localhost-only server.

AI review is disabled by default.

## Data Captured

Mr Token captures Claude Code hook data, including:

- hook event metadata
- event type
- session id when available
- tool names
- commands
- file paths
- prompt length
- stdout/stderr/result length
- estimated token counts
- raw Claude Code hook payloads

## Risk

Claude Code hook payloads may contain snippets of source, commands, tool output, file paths, or other sensitive project context depending on the event. Use Mr Token only in projects where you are authorized to collect this local diagnostic data.
