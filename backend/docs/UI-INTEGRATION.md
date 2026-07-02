# UI Integration — surfacing accurate token data in the dashboard

**For:** TurbochadNick (TS side) · **From:** Python backend

The Python backend writes accurate, transcript-derived metrics into the **same**
`.token-tithe/token-tithe.db` the TS CLI uses. The `events` table (estimated,
char-counted) and the backend tables (real API token counts) coexist and are
**joinable on `session_id`**. This doc is everything you need to show the real
numbers in the dashboard / Doctor.

---

## Two ways to consume (pick one)

### Option A — read the SQL view directly (recommended for the UI)

The backend maintains a view called **`session_summary`** in the shared DB. One
row per session, already aggregated:

```sql
SELECT * FROM session_summary WHERE session_id = ?;
```

It's a plain view — no extra process needed, your existing `better-sqlite3`/
`node:sqlite` connection can query it. If the view is missing (a DB that has only
ever seen the TS side), run any backend command once (`mrtoken-transcript export`)
or have the backend's `connect()` open it — both create the view idempotently.

### Option B — shell out to the export command (good for Doctor / one-shot)

```bash
mrtoken-transcript export [session-prefix] --db <path-to-shared-db>
```

Emits:

```json
{
  "schema": "mrtoken.session_summary.v1",
  "sessions": [ { ...one object per session, with a "recommendations" array... } ]
}
```

Safe on any DB: if the backend tables don't exist yet it returns
`{"schema": "...", "sessions": []}` rather than erroring.

---

## `session_summary` columns

| column | type | meaning |
|---|---|---|
| `trace_id` | int | backend primary key |
| `session_id` | text | **join key** ↔ `events.session_id` |
| `parent_session_id` | text | set for subagent sessions (else NULL) |
| `source` | text | `claude_code` or `claude_code_subagent` |
| `profile` | text | `code` / `research` / `agent` / `benchmark` (Eco-Mode classifier) |
| `profile_confidence` | real | 0..1 |
| `project_path` | text | cwd at session start |
| `title` | text | session title if present |
| `started_at`, `ended_at` | text | ISO8601 |
| `model_calls` | int | assistant turns |
| `is_low_activity` | int | 1 if the session has too few model calls to be meaningful (near-empty / aborted) — gray out or filter in the UI |
| `input_tokens` | int | **real** (non-cached input) |
| `output_tokens` | int | **real** |
| `cache_read_tokens` | int | **real** |
| `cache_write_tokens` | int | **real** |
| `total_tokens` | int | input + output |
| `est_cost_usd` | real | API-equivalent estimate — **label as estimate, not a bill** |
| `cache_hit_ratio` | real | 0..1, NULL if no input-side tokens |
| `tool_calls` | int | |
| `tool_errors` | int | |
| `recommendation_count` | int | rows in `recommendation` for this session |
| `high_recommendations` | int | severity = high |

Per-session recommendations live in the `recommendation` table (or the
`recommendations` array of the export JSON):
`rule, severity (high|warn|info), message, est_savings_tokens`.

---

## Estimated ↔ actual join (the upgrade the dashboard wants)

```sql
SELECT
  e.session_id,
  SUM(e.estimated_tokens)  AS estimated_tokens,   -- TS events (char-counted)
  s.total_tokens           AS actual_tokens,       -- backend (real API usage)
  s.est_cost_usd,
  s.cache_hit_ratio,
  s.profile,
  s.high_recommendations
FROM events e
LEFT JOIN session_summary s ON s.session_id = e.session_id
GROUP BY e.session_id;
```

Suggested UI treatment: show **actual** when `session_summary` has the row, fall
back to **estimated** when it doesn't (session not yet ingested by the Stop hook).
A small "estimated → actual" delta is a nice trust signal for evaluators.

---

## Sample row (real session)

```json
{
  "session_id": "1699bea2-…",
  "profile": "code",
  "profile_confidence": 0.679,
  "model_calls": 2227,
  "input_tokens": 10601,
  "output_tokens": 1700650,
  "cache_read_tokens": 202497411,
  "cache_write_tokens": 7924762,
  "total_tokens": 1711251,
  "est_cost_usd": 116.008622,
  "cache_hit_ratio": 0.9623,
  "tool_calls": 1335,
  "tool_errors": 57,
  "recommendation_count": 7,
  "high_recommendations": 4
}
```

---

## `session_detail` — per-model-call timeline (the drill-down panel)

Both of the earlier open questions are now **shipped**: there's a `session_detail`
view (one row per model call, for a drill-down / timeline panel) and a `--since`
filter on `export` (for incremental refresh). Metadata only — token/cost/tool counts
per call, **no prompt or content** (privacy invariant holds).

```sql
SELECT timestamp, model, input_tokens, output_tokens, cache_read_tokens,
       cache_write_tokens, reasoning_tokens, est_cost_usd, tool_calls, tool_errors
FROM session_detail
WHERE session_id = ?          -- prefix match with LIKE ? || '%' also fine
ORDER BY timestamp;           -- the view is unordered; always ORDER BY timestamp
```

| column | type | meaning |
|---|---|---|
| `session_id` | text | **join key** ↔ `events.session_id` |
| `trace_id` | int | backend trace PK (same as `session_summary.trace_id`) |
| `model_call_id` | int | per-call PK; stable tiebreaker for equal timestamps |
| `timestamp` | text | ISO8601 of the model call — the x-axis for a timeline |
| `model` | text | model id for this call |
| `input_tokens` | int | **real** non-cached input for THIS call |
| `output_tokens` | int | **real** output for THIS call |
| `cache_read_tokens` | int | **real**, this call |
| `cache_write_tokens` | int | **real**, this call |
| `reasoning_tokens` | int | extended-thinking tokens (0/NULL when none) |
| `est_cost_usd` | real | per-call API-equivalent estimate — **label as estimate** |
| `tool_calls` | int | tool calls attributed to this model call |
| `tool_errors` | int | of which errored |

**Drill-down uses:** cumulative-sum `input+cache_read` per row to draw the
context-growth curve; `est_cost_usd` per row for a cost-per-turn sparkline;
`tool_errors` to mark trouble spots. Roll up to the session with `session_summary`;
expand a session into this timeline on click.

---

## Export command reference (Option B surface)

```bash
mrtoken-transcript export [session-prefix] [--db PATH]     # session_summary.v1 (one obj/session)
mrtoken-transcript export <session-prefix> --detail        # session_detail.v1 (per-call timeline)
mrtoken-transcript export --since 2026-07-01T00:00:00       # only sessions started at/after (incremental)
mrtoken-transcript export <session-prefix> --redact        # drop project_path + title (safe to share)
mrtoken-transcript export [...] --codex                     # read the central Codex DB instead
```

`--detail` requires a session prefix (it's a single-session timeline). `--since`
filters `started_at`; combine with a prefix to page. Detail JSON:

```json
{ "schema": "mrtoken.session_detail.v1", "tool_version": "0.5.x",
  "session_prefix": "…", "calls": [ { …one object per model call… } ] }
```

---

## Stability contract

- **Schemas:** `mrtoken.session_summary.v1` and `mrtoken.session_detail.v1`. I bump the
  version only if a column changes meaning or is removed; **additive columns won't bump it**
  (e.g. `is_low_activity` was added to summary without a bump — code defensively, select
  columns by name, don't assume position).
- The view names `session_summary` / `session_detail` and the join key `session_id` are stable.
- `est_cost_usd` is an API-equivalent **estimate**, not a bill — always label it as such.
- Metadata-only guarantee: no view or export field carries prompt text, source, or secrets.
- Both open questions are now answered (see above) — nothing left pending from my side for v1.
  Ping me if you want an aggregate/rollup view (e.g. per-project or per-day) for the landing page.
