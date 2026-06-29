# Privacy

Mr Token is local-first.

## Default Data Location

The Python backend beta writes metadata to:

- `.token-tithe/token-tithe.db`
- `~/.mrtoken/data/`

Claude hooks are written to:

- `~/.claude/settings.json`
- `~/.claude/skills/`
- `~/.codex/hooks.json` and `~/.codex/skills/` when `~/.codex/` exists

The optional TypeScript dashboard path may also write:

- `.token-tithe/events.jsonl`
- `.token-tithe/patches/`
- `.claude/settings.local.json`

## No Hosted Backend

The Python backend beta does not include a hosted backend, login, billing,
telemetry, or cloud sync.

## No Source Upload By Default

Mr Token does not upload source code by default. The optional local UI reads the
local SQLite database through a localhost-only server.

AI review is disabled by default. License verification and AI review belong to
the optional TypeScript command path, not the always-on Python detection path.

## Data Captured

The backend captures metadata derived from Claude Code transcripts and hook
payloads, including:

- session id when available
- tool names
- commands
- file paths
- prompt/output/result lengths
- actual token counts from transcripts where available
- cache read/write token counts
- API-equivalent cost estimates
- hashed context blocks for repeat detection
- rule recommendations and feedback

## Risk

Claude Code hook payloads and transcripts may contain snippets of source,
commands, tool output, file paths, or other sensitive project context depending
on the event. Mr Token's default ledger avoids raw prompt/source storage, but use
it only in projects where you are authorized to collect local diagnostic
metadata.
