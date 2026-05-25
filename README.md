# token-tithe

`token-tithe` is a local-first TypeScript CLI for Claude Code users. It installs Claude Code hooks, collects local session/tool/prompt events, stores them in SQLite, and prints a terminal audit report.

No backend. No auth. No web dashboard.

## Requirements

- Node.js 22+
- pnpm

## Install

```bash
pnpm install
pnpm build
pnpm link --global
```

For local development:

```bash
pnpm dev -- --help
```

## Commands

```bash
npx token-tithe init
npx token-tithe audit
npx token-tithe doctor
```

That is the MVP boundary. `watch` exists only as the internal Claude Code hook handler installed by `init`.

## What `init` Does

`token-tithe init` locates the current project root, creates:

```text
.token-tithe/
.token-tithe/events.jsonl
.token-tithe/token-tithe.db
```

It safely reads or creates project-local Claude Code settings at:

```text
.claude/settings.local.json
```

Before editing an existing settings file, it writes a timestamped backup next to it.

Hooks are installed for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`, and `PostCompact`. Existing settings and hooks are preserved. Each hook pipes Claude Code event JSON into the local handler with the event name:

```bash
token-tithe watch --stdin --hook-event 'UserPromptSubmit' --db '/project/.token-tithe/token-tithe.db' --events '/project/.token-tithe/events.jsonl'
```

## Local Data

By default, SQLite data is stored at:

```text
.token-tithe/token-tithe.db
```

Raw hook events are also appended to:

```text
.token-tithe/events.jsonl
```

Each JSONL row is normalized with timestamp, project path, session id, event type, tool name, file path, command, prompt/output/result lengths, estimated tokens, and the raw Claude Code hook event.

## AI Privacy

No external AI call is made by default.

Configure optional AI review in your project `package.json`:

```json
{
  "tokenTithe": {
    "ai": {
      "enabled": false,
      "model": "claude-haiku-4-5",
      "redaction": true
    }
  }
}
```

When `tokenTithe.ai.enabled` is `true`, `token-tithe audit` uses `ANTHROPIC_API_KEY` from the environment. It sends only a redacted structured audit summary by default. It must not send raw source files or full transcripts unless full-context mode is explicitly enabled.

## Doctor Patches

`token-tithe doctor` generates safe patch proposals only. It does not apply them.

Patch bundles are written to:

```text
.token-tithe/patches/YYYYMMDD-HHMMSS/
```

Each bundle includes proposed files, `patch.diff`, and `SUMMARY.md` for manual review.

## Not In Scope

- Browser extension
- ChatGPT integration
- SaaS dashboard
- Team billing
- Complex auth
- Slack bot
- AI prompt coach

Override it with:

```bash
TOKEN_TITHE_DB=/path/to/token-tithe.db token-tithe audit
```

## Development

```bash
pnpm typecheck
pnpm test
pnpm build
```
