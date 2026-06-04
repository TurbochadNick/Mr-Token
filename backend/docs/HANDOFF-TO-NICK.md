# 👋 Handoff — accurate token data is ready for the UI

*2026-06-04 · from the Python backend side*

@TurbochadNick — the backend now writes accurate, transcript-derived token data
into the **same** `.token-tithe/token-tithe.db` your TS CLI uses, joinable to the
`events` table on `session_id`. Everything to surface it in the dashboard/Doctor
is in place. **Full integration guide: [`UI-INTEGRATION.md`](./UI-INTEGRATION.md).**

## TL;DR — what you can consume now
- **`session_summary` SQL view** (shared DB): real input/output/cache tokens,
  `total_tokens`, `est_cost_usd` (label as *estimate*), `cache_hit_ratio`,
  `profile`, `tool_errors`, `recommendation_count`, `high_recommendations`.
- **`mrtoken-transcript export [session]`** → `{schema:"mrtoken.session_summary.v1", sessions:[...]}`,
  recommendations attached. Returns `{sessions:[]}` (never crashes) on a TS-only DB.
- **`mrtoken-transcript init`** installs our Stop hook *alongside* your TS hooks
  (project-local, backed up, idempotent) so accurate data flows automatically.

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
`schema: mrtoken.session_summary.v1` — version bumps only on breaking changes;
additive columns won't. `session_summary` name + `session_id` join key are stable.

## Two questions for you
1. Want a `--since <iso>` filter on `export` (incremental dashboard refresh)?
2. Want a `session_detail` view (per-model-call timeline) for a drill-down panel?

Ping me on either and I'll add it. Rule trust FYI (precision proxy across a
55-session fleet, via `mrtoken-transcript validate`): huge_tool_output 91% ·
retry_loop 100% · fresh_handoff 94% · low_cache 100%.
