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
variants). Mr Token infers it from your real usage and the inferred window only
ratchets up (it never flips back down after a compaction). One caveat of
inference: a 1M session looks like a near-full 200k one until it crosses 200k, a
single jump in `ctx %`. If you know your window, set it once and the percentage
stays exact:

- per-shell: `export MRTOKEN_CONTEXT_MAX=1000000`
- persistent: `~/.mrtoken/config.json` -> `{"context_max": 1000000}`

## Does this work with Claude desktop app?

Partly. The global hook can ingest desktop sessions when Claude Code provides the
same hook payload/transcript path, but the desktop app may not render the
terminal HUD. Use `/mr-status`, `/mr-why`, or `mrtoken-transcript status` on
demand.

## Does this work with Claude Code CLI?

Yes. This is the primary beta path. Mr Token installs global Claude Code hooks
and a statusLine into `~/.claude/settings.json`, then resolves the correct local
project DB from each session.

## Does this upload code?

No source upload occurs by default. Data stays local unless a user deliberately exports or shares files.

## Does this support Codex?

Yes, as a secondary beta path. The backend can ingest Codex rollouts, backfill
Codex sessions into a central DB, expose MCP tools to Codex, and install a Stop
hook into `~/.codex/hooks.json` when `~/.codex/` exists.

## Does this apply patches automatically?

No. Doctor generates patch proposals under `.token-tithe/patches/` for manual review.

## What is Doctor?

Doctor is the fuel-efficiency diagnostic system. It explains where tokens are being burned, why, whether the burn is likely useful, and what to change next.

## What is the UI?

The optional TypeScript UI is a local control panel served by `token-tithe ui` on
`127.0.0.1`. It is not the primary beta surface; the beta surface is the
`mrtoken-transcript` HUD/backend.

## What does local-only mean?

The Python backend reads local transcripts, writes local SQLite metadata, and
does not use a hosted backend, telemetry, login, or billing. Optional TS
commands include license plumbing, and optional AI review can call Anthropic only
when explicitly enabled.

## Can this be used on confidential projects?

Only if you are authorized to collect local Claude Code hook payloads for that project. Hook payloads may include paths, commands, prompts, and tool output snippets.
