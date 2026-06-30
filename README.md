# Mr Token

Mr Token is a local-first token-efficiency tool for coding-agent workflows. It
shows where long sessions are burning context, flags dynamic waste such as huge
tool outputs and retry loops, and gives the agent or user the next action to take
now.

## Current Beta Surface

For beta testers, the supported surface is the Python backend/HUD:
`mrtoken-transcript`.

That path:

- installs Claude Code hooks, `/mr-*` skills, and a terminal status line;
- reads Claude Code transcripts after turns/sessions;
- stores metadata-only token, cache, tool, and recommendation data locally;
- reports accurate transcript-derived token counts, cache stats, API-equivalent
  cost estimates, and deterministic recommendations;
- provides `status`, `why`, `handoff`, `savings`, `export`, `feedback`, and MCP
  toolbox commands.

Install it with:

```bash
./install.sh
```

Then use Claude Code normally. In a terminal session, the HUD/status line is the
main experience. On demand:

```bash
mrtoken-transcript status
mrtoken-transcript doctor
mrtoken-transcript why
mrtoken-transcript handoff
mrtoken-transcript savings
mrtoken-transcript beta-note
mrtoken-transcript export --redact > mrtoken-beta.json
mrtoken-transcript doctor --bundle
mrtoken-transcript beta-summary mrtoken-beta.json mrtoken-doctor-bundle.json
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the tester flow.
Ownership is still gated; see [OWNERSHIP_GATE.md](OWNERSHIP_GATE.md) and
[docs/GOVERNANCE.md](docs/GOVERNANCE.md) before widening distribution.

## Other Surfaces

The repo also contains a TypeScript CLI/local UI under `src/` and `web/`. That
surface is useful for dashboard work and can read the backend's accurate
`session_summary` view, but it is not the primary beta install path right now.
It currently includes license/login plumbing for the `mrtoken`/`token-tithe`
commands, so do not describe it as "no auth" in tester material.

Codex support exists in the backend adapter, central Codex DB commands, MCP
toolbox registration, and live Stop-hook ingestion. When `~/.codex/` exists,
`mrtoken-transcript init` installs MR Token skills and the Stop hook into
`~/.codex/hooks.json`. The Codex Stop hook prints a compact usage line with
context percentage, fresh tokens, cache ratio, estimated cost when priced, and
profile. Recommendation nudges are short labels; full explanations live in
`/mr-why` and `mrtoken-transcript why`.

## What It Stores

The default Claude Code beta path writes:

```text
<project>/.token-tithe/token-tithe.db
~/.mrtoken/data/
~/.claude/settings.json
~/.claude/skills/
```

The project DB stores metadata such as token counts, cache stats, hashes, sizes,
tool names, timings, cost estimates, recommendations, and feedback. It does not
store raw prompts, source files, full transcripts, or secrets by default.

Codex sessions aggregate into a central DB:

```text
~/.mrtoken/data/codex.db
```

## Privacy And Network

The always-on backend is local and deterministic. It makes no network calls by
default and no LLM call in the core detection loop.

Optional features can add network behavior:

- the TypeScript `mrtoken`/`token-tithe` command verifies license keys for
  license-gated commands;
- the TypeScript audit AI review can call Anthropic only when explicitly enabled
  in config and provided `ANTHROPIC_API_KEY`;
- external MCP/token-saver modules are opt-in and must pass a separate trust and
  privacy review before being recommended.

## Development

TypeScript:

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

Python backend:

```bash
./scripts/test-backend.sh
```

The script selects Python 3.11+ and runs the suite with an isolated temporary
`HOME`, so central `~/.mrtoken` data is not touched. Set `PYTHON=/path/to/python`
or `MRTOKEN_TEST_HOME=/path/to/home` to override.
