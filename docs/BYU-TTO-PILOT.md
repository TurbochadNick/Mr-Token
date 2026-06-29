# BYU TTO Pilot: Mr Token

## What Mr Token Does

Mr Token is a local-first fuel-efficiency diagnostic tool for AI coding-agent
usage. The supported pilot surface is the Python backend command
`mrtoken-transcript`.

It installs Claude Code hooks, reads local transcripts, records metadata-only
token/cache/tool data, diagnoses dynamic waste patterns, and surfaces the next
action through a terminal HUD plus `/mr-*` skills.

## What It Does Not Do

- No cloud backend
- No login or billing for the Python backend beta
- No telemetry
- No source upload by default
- No automatic patch application
- No arbitrary shell command execution from the optional UI
- No hosted dashboard
- No hosted Codex service or cloud relay

## Pilot Scope

The pilot is scoped to local Claude Code usage. A technical evaluator should
install Mr Token in a test repository, use Claude Code normally for several
days, then inspect the HUD, reports, and redacted export.

Claude Code terminal sessions show the full status line and turn-boundary
nudges. Claude Code desktop sessions can still be ingested by the global hook,
but the desktop app may not render the ambient terminal HUD; use `/mr-status`,
`/mr-why`, or `mrtoken-transcript status` on demand.

When `~/.codex/` exists, `init` installs the MR Token skills and Stop hook for
Codex as well. Codex sessions aggregate into the central Codex DB and can be
inspected with `mrtoken-transcript ... --codex`.

## Local-Only Data Model

Data is written locally:

- `.token-tithe/token-tithe.db`
- `~/.mrtoken/data/`
- `~/.claude/settings.json`
- `~/.claude/skills/`

The project DB stores token counts, cache stats, hashes, sizes, timings, tool
names, recommendations, and feedback. It does not store raw prompts, source
files, full transcripts, or secrets by default.

## First Run

```bash
git clone <repo> mr_token
cd mr_token
./install.sh
mrtoken-transcript status
```

Use Claude Code normally. When you want a report:

```bash
mrtoken-transcript why
mrtoken-transcript savings
mrtoken-transcript export --redact > mrtoken-beta.json
```

## Success Criteria

A successful pilot shows:

- Hooks install without destroying existing Claude Code settings.
- Sessions are ingested locally.
- HUD/status reports show actual token/cache/cost data.
- Recommendations identify real dynamic waste when it occurs.
- `/mr-status`, `/mr-why`, and `/mr-handoff` are understandable and useful.
- `export --redact` produces a shareable metadata-only pilot file.
- Uninstall steps are clear and reversible.

## Known Alpha Limitations

- The Python backend is the supported beta path; the TS dashboard is optional.
- Desktop apps may run hooks without rendering the terminal HUD.
- Codex support is newer than the Claude Code path and should be treated as
  secondary in the pilot.
- API-equivalent cost is an estimate, not a subscription bill.
- Diagnosis is rule-based and may produce false positives.
