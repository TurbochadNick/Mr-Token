# Mr Token — repo guide for agents

Mr Token is a local-first token-efficiency tool for Claude Code. Two
complementary parts live in this repo:

| Part | Path | Language | Role |
|---|---|---|---|
| `token-tithe` CLI + local UI | `src/`, `web/` | TypeScript | Installs Claude Code hooks, records hook **events**, estimates token burn, renders the dashboard/Doctor. Customer-facing command: `mrtoken` (also `token-tithe`). |
| transcript backend | `backend/` | Python | Parses session **transcripts** for *accurate* token counts, cache stats, cost, subagent ROI, and rule-based recommendations. Command: `mrtoken-transcript`. |

Both write to the **same** project-local SQLite DB: `.token-tithe/token-tithe.db`.
The TS side owns the `events` table; the Python side owns `trace`, `model_call`,
`tool_call`, `context_block`, `recommendation`, and the `session_summary` **view**.
They never collide and are joinable on `session_id`.

## ⚑ If you're working on the dashboard, Doctor, or any UI that shows tokens/cost

The TS `events` table holds **estimated** tokens (char-counted). The Python
backend holds the **real** API token counts, cache ratios, cost, and profile.
**Before adding token/cost display, read these — the accurate data is already there:**

1. `backend/docs/UI-INTEGRATION.md` — exact `session_summary` columns, the
   estimated↔actual SQL join, the `export` JSON schema, and the stability contract.
2. `backend/docs/HANDOFF-TO-NICK.md` — the short version + two open questions.

Consume it either by querying the `session_summary` view directly from the shared
DB, or via `mrtoken-transcript export [session]` (JSON, schema
`mrtoken.session_summary.v1`). Prefer **actual** (session_summary) when the row
exists, fall back to **estimated** (events) otherwise.

## Working in each part

- **TypeScript:** `pnpm install && pnpm build`; tests `pnpm test` (Vitest).
  Entry point `src/cli.ts`; audit rules `src/audit/rules.ts`; UI `web/`.
- **Python backend:** `pip install -e backend/`; tests
  `cd backend && python3 -m unittest tests.test_backend`. Entry point
  `backend/mrtoken/cli.py`. Commands: `init`, `ingest`, `report`, `list`,
  `subagents`, `fleet`, `export`, `validate`, `watch`, `handoff`, `why`, `roi`.
- **Skills:** `backend/skills/<name>/SKILL.md` are bundled Claude Code skills;
  `mrtoken-transcript init` installs them GLOBALLY into `~/.claude/skills/` (so
  `/mr-*` and the Stop-hook flywheel work in every project, like the hooks do).
  `/mr-handoff` generates a fresh-session handoff; `/mr-why` diagnoses where a
  session's cost went.

## Privacy invariant (both sides)

Metadata-first: store token counts, hashes, sizes, tool names, timings, cost
estimates — **not** raw prompts, source, secrets, or logs unless content capture
is explicitly enabled. Keep this when adding features on either side.
