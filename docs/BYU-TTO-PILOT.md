# BYU TTO Pilot: Mr Token

## What Mr Token Does

Mr Token is a local fuel-efficiency diagnostic tool for AI coding-agent usage. The backend package is still named `token-tithe`.

It installs Claude Code hooks, records local hook events, estimates token burn, diagnoses waste patterns, and generates safe patch proposals that may reduce future token use.

## What It Does Not Do

- No cloud backend
- No login or billing
- No telemetry
- No source upload by default
- No automatic patch application
- No arbitrary shell command execution from the UI
- No Codex, OpenClaw, or Claude desktop support in this pilot

## Pilot Scope

The pilot is scoped to local Claude Code CLI projects. A technical evaluator should install Mr Token in a test repository, initialize hooks, use Claude Code normally, then inspect the local dashboard and Doctor output.

## Claude Code CLI Requirement

This pilot requires Claude Code CLI hook support. Mr Token writes hooks into project-local `.claude/settings.local.json`.

## Local-Only Data Model

Data is written inside the current project:

- `.token-tithe/token-tithe.db`
- `.token-tithe/events.jsonl`
- `.token-tithe/patches/`
- `.claude/settings.local.json`

The local web UI binds to `127.0.0.1` and reads the SQLite database through the local CLI server.

## First Audit

```bash
git clone <repo>
cd <repo>
pnpm install
pnpm build
npm link
token-tithe ui
```

In the UI:

1. Open Setup.
2. Click **Initialize Project**.
3. Use Claude Code normally.
4. Click **Refresh Audit**.
5. Open Doctor and click **Run Doctor**.

## Success Criteria

A successful pilot shows:

- Hooks install without destroying existing `.claude/settings.local.json`.
- Events are captured locally.
- Dashboard shows token burn, events, and diagnosis findings.
- Doctor generates patch proposals under `.token-tithe/patches/`.
- Patches are never applied automatically.
- Uninstall steps are clear and reversible.

## Known Alpha Limitations

- Only Claude Code CLI is supported.
- Hook payloads may contain file paths, commands, and snippets of tool output.
- Token estimation uses deterministic heuristics, not provider billing records.
- Diagnosis is rule-based and may produce false positives.
- The UI has no authentication because it binds to localhost only.
