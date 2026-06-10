# token-tithe

`token-tithe` is a local-first TypeScript CLI for Claude Code users. It installs Claude Code hooks, collects local session/tool/prompt events, stores them in SQLite, and prints a terminal audit report.

No backend. No auth. No web dashboard.
The local web UI is called Mr Token; the CLI/package remains `token-tithe`.

## Requirements

- Node.js 22 LTS recommended (builds and tested on 22 through 26; `better-sqlite3`
  v12 ships prebuilt binaries across this range, so no native compile is needed).
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
npx token-tithe ui
```

That is the local MVP boundary. `watch` exists only as the internal Claude Code hook handler installed by `init`.

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

## Mr Token Local UI

Start the local control panel:

```bash
token-tithe ui
```

Options:

```bash
token-tithe ui --port 4317
token-tithe ui --no-open
```

The UI binds to `127.0.0.1` only and serves `http://localhost:4317`. It reads the existing `.token-tithe/token-tithe.db` through the local CLI server. There is no auth, telemetry, source upload, cloud backend, or hosted deployment.

Workflow:

1. Open a project folder in terminal.
2. Run `token-tithe ui`.
3. Click **Initialize Project** if hooks are not installed.
4. Use Claude Code normally.
5. Click **Refresh Audit** or run `token-tithe audit`.
6. Click **Run Doctor** to generate safe patches.

Control panel pages:

- Dashboard: token summary, estimated savings, top finding, findings table, report export.
- Events: filter by event type and tool name.
- Doctor: generate a safe patch bundle and view `SUMMARY.md` / `patch.diff`.
- Setup: project root, database status, events JSONL status, Claude settings status, hook status.

Local API endpoints:

```text
GET /api/summary
GET /api/findings
GET /api/events
GET /api/doctor/latest
GET /api/setup
GET /api/export/report.md
POST /api/init
POST /api/audit/run
POST /api/doctor/run
```

The UI does not include patch application or arbitrary shell command execution.

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
- Hosted deployment
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
