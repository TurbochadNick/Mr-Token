# FAQ

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
