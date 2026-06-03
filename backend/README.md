# MR Token — Python Backend

Local-first token observability for AI agent workflows.

Companion to the `token-tithe` TypeScript CLI in the repo root.

## How they fit together

| Layer | Component | What it captures |
|---|---|---|
| **Real-time events** | `token-tithe` (TypeScript) | Hook events, prompt text, tool I/O sizes, estimated tokens, CLAUDE.md bloat |
| **Accurate token counts** | `mrtoken` (Python, this package) | Real API token counts, cache stats, subagent ROI, cost estimates from transcript JSONL |

`token-tithe` captures events as they happen via Claude Code hooks.  
`mrtoken` reads the session transcript after each session ends for the real numbers.

Both write to local SQLite. Future: the TypeScript UI reads from the Python DB for accurate cost data.

## Install

```bash
cd backend
pip install -e .
```

This installs the `mrtoken-transcript` shell command. The repo-root TypeScript CLI owns the customer-facing `mrtoken` command.

## Quick start

```bash
# Ingest all past Claude Code sessions + run rules
mrtoken-transcript ingest --all --rules

# Fleet summary
mrtoken-transcript fleet

# Session report
mrtoken-transcript report <session-id-prefix>

# Subagent ROI breakdown
mrtoken-transcript subagents <session-id-prefix>

# List all sessions
mrtoken-transcript list
```

## Auto-update via hook

`backend/hooks/on_stop.py` is wired as a Claude Code `Stop` hook — it runs automatically when any session ends, ingests the transcript, runs the rule engine, and prints a one-line summary.

By default, transcript data is reconciled into the current project's `.token-tithe/token-tithe.db`, alongside the TypeScript CLI/UI data. Set `MRTOKEN_DB=/path/to/db` in the hook command to override this.

To enable, add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/python3 /path/to/Mr-Token/backend/hooks/on_stop.py"
          }
        ]
      }
    ]
  }
}
```

## What it measures

- `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` — real values from the Anthropic API response, not estimates
- Per-model estimated API-equivalent cost (labeled — not a subscription bill)
- Subagent token consumption + compression ratio (result tokens / subagent total)
- Context block repeat detection via hashing
- Tool output sizes

## Rules (Layer 2)

| Rule | Severity | Signal |
|---|---|---|
| `repeated_context` | high/warn | Duplicate context blocks re-sent — **cache-aware** (discounts the cached fraction; only uncached re-sends count) |
| `huge_tool_output` | warn | Single tool result over the profile threshold (research 80k / code-agent 40k / benchmark 24k chars) |
| `retry_loop` | high | Clustered tool errors across consecutive calls (distinguishes a real loop from single-call mass failure) |
| `low_cache` | info | Cache hit ratio below the profile floor after 10+ calls |

Thresholds are **profile-aware** (see Session profiles above).

## Validating the rules

There is no human-labeled ground truth, so `validate` does **not** claim "% correct".
It corroborates each fired recommendation against independent evidence in the
trace and reports a **precision proxy** (strong / weak / moot), pointing at which
rules need tuning:

```bash
mrtoken-transcript validate            # table
mrtoken-transcript validate --json     # machine-readable
```

Across a 55-session real fleet: huge_tool_output 91%, retry_loop 100%,
fresh_handoff 94%, low_cache 100% strong-corroboration. (The harness is what
surfaced that `repeated_context` was double-counting cache-served re-sends,
which led to the cache-aware fix above.)
| `fresh_handoff` | high | Growing input + cache decay + depth — start a fresh session |

## Session profiles (TTO Eco Mode methodology)

Each session is classified into a work profile — `code`, `research`, `agent`,
`benchmark` — deterministically from its tool-call distribution (no AI, no
prompt text needed). Rule thresholds are then **profile-aware**: a 20k-token
Read is normal in `research` but flagged in `benchmark`. Stored on `trace.profile`.

## Integration surface for the UI

The `session_summary` SQL **view** (in the shared `.token-tithe/token-tithe.db`)
exposes accurate per-session metrics keyed on `session_id`:

```
trace_id, session_id, parent_session_id, source, profile, profile_confidence,
project_path, title, started_at, ended_at, model_calls, input_tokens,
output_tokens, cache_read_tokens, cache_write_tokens, total_tokens,
est_cost_usd, cache_hit_ratio, tool_calls, tool_errors,
recommendation_count, high_recommendations
```

The TypeScript `events` table is keyed on the same `session_id`, so the UI can
join **estimated (events) ↔ actual (session_summary)** per session. Two ways to consume:

1. **Direct SQL** — `SELECT * FROM session_summary` from the shared DB.
2. **JSON export** — `mrtoken-transcript export [session-prefix]` emits
   `{schema: "mrtoken.session_summary.v1", sessions: [...]}` with each session's
   recommendations attached.

## Data model

6 tables: `trace`, `model_call`, `tool_call`, `context_block`, `event`, `recommendation`,
plus the `session_summary` view.  
See `docs/DATA_MODEL.md` for full schema and source mapping.

Default DB: `.token-tithe/token-tithe.db` in the detected project root.
