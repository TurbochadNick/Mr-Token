# MR Token — Data Model (MVP)

*Grounded in verified Claude Code transcript JSONL fields (2026-06-01). SQLite.*

## Design rules
- **6 tables**, not the 12 from the originating spec. `trace = Claude Code session` for MVP (a "task" is an optional later subdivision). `span` is a **derived view**, not a table — it's just `model_call ∪ tool_call` ordered by timestamp. `handoff`/`cost_snapshot` are not tables (a handoff is LLM output; a cost snapshot is a query).
- Tokens are stored raw; **dollars are computed**, never the source of truth.
- **Metadata-default**: we store sizes/hashes/counts, not content. `context_block.hash` enables repeat/stale detection without keeping text.

## Source mapping (where each field comes from)
All from transcript JSONL `~/.claude/projects/<escaped-cwd>/<sessionId>.jsonl`, one JSON object per line. Entry `type` ∈ {`user`, `assistant`, `system`, `attachment`, ...}. **`assistant`** entries carry `message.usage` (token ground truth) and `message.content` (tool_use blocks). **`user`** entries carry tool_result blocks. Confidence: **verified-locally** unless noted.

| Model field | Transcript source |
|---|---|
| trace.session_id | `sessionId` |
| trace.project_path | `cwd` |
| trace.git_branch | `gitBranch` |
| trace.cc_version | `version` |
| trace.entrypoint | `entrypoint` (e.g. claude-desktop) |
| model_call.request_id | `requestId` |
| model_call.message_uuid / parent_uuid | `uuid` / `parentUuid` (message tree → retry/loop detection) |
| model_call.model | `message.model` |
| model_call.timestamp | `timestamp` (ISO8601) |
| model_call.input/output/cache_read/cache_creation tokens | `message.usage.*` |
| model_call.ephemeral_1h / _5m | `message.usage.cache_creation.ephemeral_1h_input_tokens` / `_5m_*` |
| model_call.service_tier | `message.usage.service_tier` |
| model_call.stop_reason | `message.stop_reason` |
| model_call.is_sidechain | `isSidechain` (true → subagent; free subagent attribution) |
| tool_call.* | `assistant` content `tool_use` block (name, input) paired by `tool_use_id` with `user` content `tool_result` block (output) |
| reasoning_tokens | not a separate field — extended thinking is counted inside `output_tokens` (docs). Store NULL; derive ratio heuristically later. |

## Schema (DDL)

```sql
-- A unit of work. MVP: one Claude Code session.
CREATE TABLE trace (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL DEFAULT 'claude_code',
  session_id    TEXT NOT NULL UNIQUE,
  project_path  TEXT,
  git_branch    TEXT,
  cc_version    TEXT,
  entrypoint    TEXT,
  started_at    TEXT,           -- min(timestamp)
  ended_at      TEXT,           -- max(timestamp)
  title         TEXT,           -- optional, from ai-title/custom-title entries
  ingested_at   TEXT NOT NULL
);

-- One assistant LLM response. Token ground truth.
CREATE TABLE model_call (
  id                        INTEGER PRIMARY KEY,
  trace_id                  INTEGER NOT NULL REFERENCES trace(id),
  request_id                TEXT,
  message_uuid              TEXT,
  parent_uuid               TEXT,            -- message tree
  model                     TEXT,
  timestamp                 TEXT,
  input_tokens              INTEGER NOT NULL DEFAULT 0,
  output_tokens             INTEGER NOT NULL DEFAULT 0,
  cache_read_input_tokens   INTEGER NOT NULL DEFAULT 0,
  cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
  ephemeral_1h_tokens       INTEGER NOT NULL DEFAULT 0,
  ephemeral_5m_tokens       INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens          INTEGER,         -- NULL: folded into output_tokens
  service_tier              TEXT,
  stop_reason               TEXT,
  is_sidechain              INTEGER NOT NULL DEFAULT 0,   -- subagent
  est_cost_usd              REAL,            -- computed: tokens × price table
  price_version             TEXT             -- which price table produced est_cost_usd
);

-- One tool invocation (tool_use ↔ tool_result), metadata only.
CREATE TABLE tool_call (
  id              INTEGER PRIMARY KEY,
  trace_id        INTEGER NOT NULL REFERENCES trace(id),
  model_call_id   INTEGER REFERENCES model_call(id),  -- the call that requested it
  tool_use_id     TEXT,
  tool_name       TEXT,
  input_chars     INTEGER,
  input_hash      TEXT,
  output_chars    INTEGER,        -- huge-tool-output rule keys on this
  output_tokens_est INTEGER,      -- estimated (chars/4 or tokenizer)
  output_hash     TEXT,
  is_error        INTEGER DEFAULT 0,
  started_at      TEXT,
  ended_at        TEXT
);

-- Point-in-time lifecycle markers (subagent/compaction/session). Metadata only.
CREATE TABLE event (
  id          INTEGER PRIMARY KEY,
  trace_id    INTEGER NOT NULL REFERENCES trace(id),
  kind        TEXT NOT NULL,    -- subagent_start|subagent_stop|compaction|session_stop|...
  timestamp   TEXT,
  meta_json   TEXT              -- small, non-sensitive attributes only
);

-- Distinct context blocks tracked by hash for repeat/stale detection.
CREATE TABLE context_block (
  id            INTEGER PRIMARY KEY,
  trace_id      INTEGER NOT NULL REFERENCES trace(id),
  block_type    TEXT NOT NULL,  -- system|developer|user|history|handoff|file|log|tool_schema|retrieved_doc
  hash          TEXT NOT NULL,
  token_count   INTEGER,
  char_count    INTEGER,
  repeat_count  INTEGER NOT NULL DEFAULT 1,   -- times this hash appeared across calls
  first_seen    TEXT,
  last_seen     TEXT,
  source_path   TEXT,           -- if from a file
  sensitivity   TEXT,           -- null|low|medium|high (set by secret scan)
  UNIQUE(trace_id, hash)
);

-- Rule-engine output. One row per fired rule per trace.
CREATE TABLE recommendation (
  id              INTEGER PRIMARY KEY,
  trace_id        INTEGER NOT NULL REFERENCES trace(id),
  rule            TEXT NOT NULL,   -- repeated_context|huge_tool_output|retry_loop|fresh_handoff|...
  severity        TEXT NOT NULL,   -- info|warn|high
  message         TEXT NOT NULL,   -- human-readable advice
  evidence_json   TEXT,            -- numbers backing the call (token counts, ids)
  est_savings_tokens INTEGER,      -- nullable
  created_at      TEXT NOT NULL
);

-- span is a DERIVED view, not a table:
-- model_call and tool_call unioned, ordered by timestamp = the task timeline.
```

## Rule inputs (so the schema supports the 3 MVP rules)
- **repeated_context** → `context_block.repeat_count > 1` and `token_count` large ⇒ wasted re-sent tokens = `(repeat_count-1) × token_count`.
- **huge_tool_output** → `tool_call.output_chars` (or `output_tokens_est`) over threshold; flag offload-to-file.
- **retry_loop** → multiple `model_call` rows sharing `parent_uuid` / near-identical sequences, or repeated `tool_call.is_error` on same `tool_name`.
- **fresh_handoff** (the one trusted recommendation) → cumulative context size growing while `cache_read` ratio falls and old failed attempts (error tool_calls) remain upstream in the tree.

## Collection strategy (ranked, corrected from research)
1. **Transcript JSONL parser** — primary. Richest, cheapest, retrospective, no setup. **MVP uses only this.**
2. OTEL metrics receiver — optional, for near-real-time token counters (60s interval).
3. OTEL traces (beta, ~5s) + hooks — optional, for live in-session advice later.
4. `~/.claude/telemetry/1p_failed_events.*` — supplemental retry/failure signal.

## Deferred (not in MVP)
`project`, `task` (session subdivision), `handoff` table, `cost_snapshot` table, multi-source `span` table, reasoning-classification.
