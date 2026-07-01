# GOAL: Experiment closeout — confirm the regime map's two soft spots

**Lane:** Claude (interactive; live agent runs, budget-sensitive) · **Status:** ready ·
**Est:** S · **Budget:** ~$3 of the $20 cap (confirm remaining spend first)

**Loop exit (done-criteria):**
1. `debug-speclib` has **fixed-compact n≥2** recorded (the current speclib compact row is the
   PRE-fix degenerate arm; re-run with today's real-reset compact to confirm real-compact **also
   loses/ties on load-bearing**, not just handoff).
2. Optionally, `debug-scanlib` gets 1–2 more reps per arm for tighter magnitudes (only if budget allows).
3. `backend/docs/ROI-EXPERIMENT.md` RESULTS + `ORCHESTRATION.md` baton updated with the new rows.
4. No budget-cap breach (stop before $20 total across `results.db`).

## Why (root cause, stated)

The regime map's high-pressure/load-bearing verdict currently rests on `handoff` (+20%), because the
one speclib `compact` row (id17) was run **before** the compact-arm harness fix — it's the degenerate
`--resume` version, so it can't speak to real compaction on load-bearing context. One fixed-compact
run closes that gap and makes the "reset loses on load-bearing" claim symmetric (both reset arms).
Everything else about the experiment is done and committed.

## Steps

1. Confirm spend headroom (read-only):
   `sqlite3 backend/experiments/results/results.db "SELECT printf('$%.2f', SUM(est_cost_usd)) FROM run;"`
   If ≥ ~$17, STOP and ask Zach before spending.
2. Run fixed-compact on speclib (phase1=35 is already set in its manifest), 1–2 reps:
   ```bash
   cd backend/experiments && python3 runner.py tasks/debug-speclib --arm compact --budget-usd 2 --reps 1
   ```
   Run in the background; wait for completion (a fresh session won't get the notification — poll the
   `run` table). Repeat once if budget allows and the first result is ambiguous.
3. (Optional, budget permitting) add scanlib reps:
   `python3 runner.py tasks/debug-scanlib --arm <continue|compact|handoff> --budget-usd 2 --reps 1`
4. Recompute per-arm means; update the ROI RESULTS table + baton. Expectation to test: fixed-compact
   on speclib ≈ continue or worse (load-bearing → reset doesn't pay). If it WINS, that's a surprise —
   flag it, don't bury it.

## Verify (commands)

```bash
cd backend/experiments
sqlite3 -header -column results/results.db \
  "SELECT arm, COUNT(*) n, printf('$%.3f',AVG(est_cost_usd)) mean, SUM(completed) done \
   FROM run WHERE task_id='debug-speclib' AND notes LIKE '%real reset%' OR (task_id='debug-speclib' AND arm!='compact') GROUP BY arm;"
```

## Constraints
- Inherit `GOALS/README.md`. **Budget is a hard $20 cap** — check before every run; stop with margin.
- DB is the experiment `results.db` (local, gitignored) — inserts by the runner are fine; any manual
  DELETE/UPDATE needs Zach's OK (e.g. the earlier mock-row cleanup).
- Report faithfully: if a run doesn't complete or doesn't cross threshold, say so with the row.

## Out of scope
- New fixtures or arms. Re-running the low-pressure (hugelib) matrix (already n=4, done).

## Notes
- `phase1_turns` is per-fixture calibrated (speclib=35, scanlib=18); don't change without re-deriving
  from a continue transcript's 100k-crossing turn (see how it was done in the baton history).
