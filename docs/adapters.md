# TypeScript Adapter Model

This document describes the older TypeScript `token-tithe` event adapter layer.
It does not describe the Python transcript backend, which now has Claude Code and
Codex transcript ingestion paths.

## Current Adapter

`src/adapters/claude-code/` is the only implemented TypeScript event adapter.

It owns Claude Code-specific behavior:

- Hook event names: `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`, `PostCompact`
- `.claude/settings.local.json` hook installation and merge behavior for the TS event collector
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

Future TypeScript event adapters may live beside Claude Code:

```text
src/adapters/codex/
src/adapters/openclaw/
```

Those adapters should provide their own install and normalization logic, then
emit the shared normalized event shape. Do not infer that this blocks the Python
backend's Codex transcript adapter; that path lives under `backend/mrtoken/`.

## Non-Goals For This Refactor

- No TypeScript Codex event adapter implementation
- No OpenClaw adapter implementation
- No database schema change
- No behavior change to existing Claude Code commands
- No changes to the local-only privacy model
