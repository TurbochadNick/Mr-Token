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

## Stability contract

- `schema: "mrtoken.session_summary.v1"` — I'll bump the version if columns change
  meaning or are removed. Additive columns won't bump it.
- The view name `session_summary` and the join key `session_id` are stable.
- Open questions for you: do you want a `--since <iso>` filter on `export`, and/or
  a `session_detail` view (per-model-call timeline) for a drill-down panel? Say
  the word and I'll add them.
