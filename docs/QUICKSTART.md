# MR Token quickstart (terminal HUD, real token counts)

This is the fastest path to the MR Token MVP: a live, in-terminal fuel gauge for
Claude Code, backed by your session's REAL token counts (not estimates). Two
minutes to install, then it runs passively while you work.

> Two parts live in this repo. This guide covers the **Python backend**
> (`mrtoken-transcript`), which is the shippable MVP. The TypeScript
> `token-tithe` web dashboard (see the top-level README) is an optional, separate
> UI and is not required for any of the below.

## Requirements

- Python 3.10+
- Claude Code (the CLI or the desktop app; see "Where you'll see it" below)

## Install

```bash
git clone <repo-url> mr_token
cd mr_token
pip install -e backend/        # installs the `mrtoken-transcript` command
```

## Set it up in a project

From the root of a project you use Claude Code in:

```bash
mrtoken-transcript init
```

`init` is safe and idempotent. It:

- creates a project-local `.token-tithe/token-tithe.db` (metadata only: token
  counts, hashes, sizes, timings, cost estimates; never your source or prompts),
- installs the `/mr-handoff`, `/mr-status`, `/mr-why` skills globally into
  `~/.claude/skills/` (so they work in every project),
- adds a `statusLine` and `Stop` / `UserPromptSubmit` / `PreCompact` hooks to
  `~/.claude/settings.json`, backing the file up first.

Run `mrtoken-transcript init --dry-run` first if you want to see exactly what it
will touch.

## Where you'll see it

| You're using | What you get |
|---|---|
| **Claude Code in a terminal** | The full ambient HUD: a bottom status bar (`mr · ctx 78% ⚠ · ~$1.20 · code · ⚠ compact soon`) plus a one-line nudge each turn. This is the whole point. |
| **Claude Code desktop app** | Background ingestion runs, but the app does not render an ambient bar. Pull status on demand with `/mr-status` (and `/mr-why`, `/mr-handoff`). |

The HUD updates as you work. When it flags something (context filling up, a
retry loop, the same file re-read repeatedly), that is the moment to act.

## The three commands

- `/mr-status` — one-glance snapshot: context %, cost, profile, and the single
  most important next action.
- `/mr-why` — diagnoses where this session's tokens actually went and names the
  biggest leak.
- `/mr-handoff` — generates a compact, paste-ready summary to continue in a
  fresh session when this one has grown bloated.

All three also work as plain commands:

```bash
mrtoken-transcript status      # or: why | handoff
```

## Verify it's live

```bash
mrtoken-transcript status
```

You should see a status line for your current session. If you do, the HUD is
working in your terminal sessions too.

## Uninstall

See [UNINSTALL.md](UNINSTALL.md). In short: `init` backs up your settings before
editing, and the data is just the local `.token-tithe/` folder.
