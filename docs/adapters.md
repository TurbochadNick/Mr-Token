# Adapter Model

Mr Token keeps `token-tithe` as the core engine and uses adapters for tool-specific event sources.

## Current Adapter

`src/adapters/claude-code/` is the only implemented adapter.

It owns Claude Code-specific behavior:

- Hook event names: `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`, `PostCompact`
- `.claude/settings.local.json` hook installation and merge behavior
- Claude Code hook JSON parsing
- Normalization from Claude Code hook payloads into the shared event shape
- The internal `token-tithe watch` hook handler path

The database schema remains shared and compatible. Adapters normalize into the same event fields:

- timestamp
- project path
- session id
- event type
- tool name
- file path
- command
- prompt/output/result lengths
- estimated tokens
- raw event JSON

## Core Engine

The core engine should stay adapter-neutral where practical:

- SQLite schema and queries
- audit rules
- doctor patch generation
- local Mr Token UI API
- terminal reports

Compatibility re-exports remain under `src/hooks/` for now, but new Claude Code code should import from `src/adapters/claude-code/`.

## Planned Future Adapters

Future adapters may live beside Claude Code:

```text
src/adapters/codex/
src/adapters/openclaw/
```

Those adapters should provide their own install and normalization logic, then emit the shared normalized event shape. Do not implement Codex or OpenClaw until their hook/event contracts are known.

## Non-Goals For This Refactor

- No Codex adapter implementation
- No OpenClaw adapter implementation
- No database schema change
- No behavior change to existing Claude Code commands
- No changes to the local-only privacy model
