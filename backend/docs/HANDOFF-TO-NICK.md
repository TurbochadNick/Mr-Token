# 👋 Handoff — accurate token data is ready for the UI (v1 surface complete)

*2026-07-02 · from the Python backend side · **Zach: forward this to Nick.***

@TurbochadNick — the backend writes accurate, transcript-derived token data into the
**same** `.token-tithe/token-tithe.db` your TS CLI uses, joinable to `events` on
`session_id`. The **v1 data surface is now complete** — including the two things you were
asked about (both shipped, see below). **Full guide: [`UI-INTEGRATION.md`](./UI-INTEGRATION.md).**

## What you can consume now
- **`session_summary` SQL view** (one row/session): real input/output/cache tokens,
  `total_tokens`, `est_cost_usd` (*estimate*, not a bill), `cache_hit_ratio`, `profile`,
  `tool_errors`, recommendation counts — **plus new `is_low_activity`** (1 = near-empty/aborted
  session; gray out or filter).
- **`mrtoken-transcript export [session]`** → `{schema:"mrtoken.session_summary.v1", sessions:[...]}`;
  returns `{sessions:[]}` on a TS-only DB (never crashes).

## Both of your open questions are answered (shipped)
1. **Incremental refresh** → `export --since <iso>` returns only sessions started at/after that time.
2. **Drill-down timeline** → new **`session_detail` view** + `export <session> --detail`
   (`mrtoken.session_detail.v1`): one row per model call — `timestamp, model, input/output/cache
   tokens, reasoning_tokens, est_cost_usd, tool_calls, tool_errors`. Cumulative `input+cache_read`
   → context-growth curve; `est_cost_usd` → per-turn cost sparkline. Metadata only, no content.

Also handy: `export --redact` (drops `project_path`/`title` — safe to share) and `--codex`
(reads the central Codex DB).

## The join the dashboard wants
```sql
SELECT e.session_id,
       SUM(e.estimated_tokens) AS estimated_tokens,  -- your events
       s.total_tokens          AS actual_tokens,      -- backend (real)
       s.est_cost_usd, s.cache_hit_ratio, s.profile, s.high_recommendations
FROM events e
LEFT JOIN session_summary s ON s.session_id = e.session_id
GROUP BY e.session_id;
```
Show **actual** when the row exists, fall back to **estimated** otherwise.

## Stability
Schemas `mrtoken.session_summary.v1` + `mrtoken.session_detail.v1` — version bumps only on
breaking changes; **additive columns won't** (`is_low_activity` was added without a bump, so select
columns by name). View names + `session_id` join key are stable. Metadata-only guarantee holds.

Rule-trust FYI (precision proxy across a 55-session fleet, via `mrtoken-transcript validate`):
huge_tool_output 91% · retry_loop 100% · fresh_handoff 94% · low_cache 100%. Ping me with anything
you want reshaped for the UI (e.g. a per-project or per-day rollup for a landing page).
