# MR Token quickstart (terminal HUD, real token counts)

This is the fastest path to the MR Token MVP: a live, in-terminal fuel gauge for
Claude Code, backed by your session's REAL token counts (not estimates). Two
minutes to install, then it runs passively while you work.

> Two parts live in this repo. This guide covers the **Python backend**
> (`mrtoken-transcript`), which is the shippable MVP. The TypeScript
> `token-tithe` web dashboard (see the top-level README) is an optional, separate
> UI and is not required for any of the below.

## Requirements

- Python 3.11+
- Claude Code (the CLI or the desktop app; see "Where you'll see it" below)

## Install (one command)

```bash
git clone <repo-url> mr_token
cd mr_token
./install.sh
```

`install.sh` checks Python, installs the backend, sets up the hooks + `/mr-*`
skills, and prints what to do next. Update later with `./update.sh`.

Prefer to do it by hand:

```bash
pip install -e backend/        # installs the `mrtoken-transcript` command
mrtoken-transcript init        # hooks + skills + statusLine
```

## Per-project setup (optional)

`install.sh` already enables the live HUD and `/mr-*` everywhere. To also get
retrospective reports for a specific project, run this from its root:

```bash
mrtoken-transcript init
```

`init` is safe and idempotent. It:

- creates a project-local `.token-tithe/token-tithe.db` (metadata only: token
  counts, hashes, sizes, timings, cost estimates; never your source or prompts),
- installs the `/mr-handoff`, `/mr-status`, `/mr-why`, and context-efficiency
  skills globally into `~/.claude/skills/` (so they work in every project),
- adds a `statusLine` and `Stop` / `UserPromptSubmit` / `PreCompact` hooks to
  `~/.claude/settings.json`, backing the file up first.

Run `mrtoken-transcript init --dry-run` first if you want to see exactly what it
will touch.

## What `init` changes (and how to turn it off)

`init` adds Claude Code hooks so MR Token can see your sessions. They are all
**read-only and 100% local**: they read the session transcript, write metadata to
a local `.token-tithe/` folder, and print the HUD. They never modify your
prompts, never block Claude, and never send anything anywhere. They only fire
during a Claude Code session, there is no background process.

| What | Where | What it does |
|---|---|---|
| **Stop** hook | `~/.claude/settings.json` (global) | After each turn/session, reads the transcript into the right local DB and computes the HUD |
| **statusLine** | `~/.claude/settings.json` (global) | Draws the bottom status bar (`mr · ctx 38% · …`) |
| **UserPromptSubmit** hook | `~/.claude/settings.json` (global) | Shows the one-line HUD when you submit a prompt |
| **PreCompact** hook | `~/.claude/settings.json` (global) | Suggests `/mr-handoff` right before Claude auto-compacts |
| `/mr-*` skills | `~/.claude/skills/` (global) | The `/mr-status`, `/mr-why`, `/mr-handoff`, and context-efficiency commands |

If `~/.codex/` exists, `init` also installs the MR Token skills into
`~/.codex/skills/` and the Stop hook into `~/.codex/hooks.json`. Codex sessions
aggregate into the central Codex DB and can be inspected with commands such as
`mrtoken-transcript fleet --codex`. The Codex Stop hook also prints a compact
usage line with context percentage, fresh tokens, cache ratio, estimated cost
when priced, and profile. Recommendation nudges are short labels; use `/mr-why`
for the full explanation.

`init` backs up each settings file before editing and preserves your other
hooks/settings. Turn all of it off any time with one command:

```bash
mrtoken-transcript uninstall      # see docs/UNINSTALL.md
```

## Where you'll see it

| You're using | What you get |
|---|---|
| **Claude Code in a terminal** | The full ambient HUD: a bottom status bar (`mr · ctx 78% ⚠ · ~$1.20 · code · ⚠ compact soon`) plus a one-line nudge each turn. This is the whole point. |
| **Claude Code desktop app** | Background ingestion runs, but the app does not render an ambient bar. Pull status on demand with `/mr-status` (and `/mr-why`, `/mr-handoff`). |
| **Codex** | The Stop hook ingests each matched rollout into the central Codex DB and prints a compact usage line (`mr · codex gpt-5.5 · ctx 28% · ~681k tok · cache 96% · code · long session: /mr-handoff at phase boundary`). |

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
