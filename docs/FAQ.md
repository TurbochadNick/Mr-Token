# FAQ

## What does "ctx 78%" or "large context" mean?

It is how full the model's context window is. The context window is the total
amount of text (your prompt, the whole conversation history, file contents, tool
output) the model can hold at once. `ctx 78%` means this session is using about
78% of that window.

Why a full context costs you:

- **Every turn re-sends the whole history**, so the fuller the window, the more
  tokens (and money) each new turn costs. Cost grows with how full you are.
- **Quality degrades as it fills** ("context rot"): the model has more to attend
  to and is likelier to lose the thread, miss earlier detail, or repeat itself.
- **When it hits the limit, Claude auto-compacts**, summarizing and dropping
  detail. That is lossy and out of your control.

So a high percentage is a signal to act *before* the limit forces a worse outcome.
Mr Token flags it around 70% and suggests `/mr-handoff` (start a fresh session
with a compact summary) rather than waiting for a lossy auto-compact.

The window size depends on the model (commonly 200k tokens, 1M on some Claude
variants). Mr Token infers it from your real usage, so the percentage is accurate
on 1M-context models instead of pinning them at 99%. Override with the
`MRTOKEN_CONTEXT_MAX` environment variable if needed.

## Does this work with Claude desktop app?

No. The pilot targets Claude Code CLI hooks.

## Does this work with Claude Code CLI?

Yes. Mr Token installs project-local Claude Code hooks into `.claude/settings.local.json`.

## Does this upload code?

No source upload occurs by default. Data stays local unless a user deliberately exports or shares files.

## Does this support Codex?

Not yet. The codebase has an adapter structure, but only the Claude Code adapter is implemented.

## Does this apply patches automatically?

No. Doctor generates patch proposals under `.token-tithe/patches/` for manual review.

## What is Doctor?

Doctor is the fuel-efficiency diagnostic system. It explains where tokens are being burned, why, whether the burn is likely useful, and what to change next.

## What is the UI?

The UI is a local Mr Token control panel served by `token-tithe ui` on `127.0.0.1`.

## What does local-only mean?

The server binds to localhost, reads local SQLite data, and does not use a hosted backend, telemetry, login, or billing.

## Can this be used on confidential projects?

Only if you are authorized to collect local Claude Code hook payloads for that project. Hook payloads may include paths, commands, prompts, and tool output snippets.
