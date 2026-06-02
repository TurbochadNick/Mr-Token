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

This installs the `mrtoken` shell command.

## Quick start

```bash
# Ingest all past Claude Code sessions + run rules
mrtoken ingest --all --rules

# Fleet summary
mrtoken fleet

# Session report
mrtoken report <session-id-prefix>

# Subagent ROI breakdown
mrtoken subagents <session-id-prefix>

# List all sessions
mrtoken list
```

## Auto-update via hook

`backend/hooks/on_stop.py` is wired as a Claude Code `Stop` hook — it runs automatically when any session ends, ingests the transcript, runs the rule engine, and prints a one-line summary.

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
            "command": "/path/to/python3 /path/to/mr_token/backend/hooks/on_stop.py"
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
| `repeated_context` | high/warn | Duplicate context blocks re-sent across calls |
| `huge_tool_output` | warn | Single tool result > ~10k tokens |
| `retry_loop` | high | Clustered tool errors within a window of calls |
| `low_cache` | info | Cache hit ratio < 40% after 5+ calls |
| `fresh_handoff` | high | Growing input + cache decay + depth — start a fresh session |

## Data model

6 tables: `trace`, `model_call`, `tool_call`, `context_block`, `event`, `recommendation`.  
See `docs/DATA_MODEL.md` for full schema and source mapping.

Default DB: `~/mr_token/mrtoken.db`
