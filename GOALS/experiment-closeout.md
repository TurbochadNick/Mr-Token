# GOAL: Experiment closeout — confirm the regime map's two soft spots

**Lane:** Claude (interactive; live agent runs, budget-sensitive) · **Status:** done ·
**Est:** S · **Budget:** closed at $17.46 of the $20 cap

**Loop exit (done-criteria):**
1. Done: `debug-speclib` has fixed real-reset compact row id25 (`$1.209`, peak 104k),
   confirming compact is a wash versus continue (`$1.237`) on load-bearing context.
2. Done: `debug-scanlib` still shows real-reset compact winning on disposable context
   (mean `$1.029`, about -28% versus continue).
3. Done: `backend/docs/ROI-EXPERIMENT.md` RESULTS + `ORCHESTRATION.md` baton updated.
4. Done: no budget breach; `results.db` total is `$17.46`.

## Why (root cause, stated)

The regime map's high-pressure/load-bearing verdict used to rest on `handoff` (+20%), because the
first speclib `compact` row (id17) was run before the compact-arm harness fix. Row id25 closed
that gap with the real-reset compact arm: load-bearing context still ties/loses, while disposable
context still wins. The current product implication is unchanged: reset only pays when context is
reclaimable and unlikely to be re-read.

## Steps

No further loop work. Do not spend more experiment budget here unless Zach explicitly reopens the
study for tighter magnitudes.

## Verify (commands)

```bash
cd backend/experiments
sqlite3 -header -column results/results.db \
  "SELECT arm, COUNT(*) n, printf('$%.3f',AVG(est_cost_usd)) mean, SUM(completed) done \
   FROM run WHERE task_id='debug-speclib' AND (notes LIKE '%real reset%' OR arm!='compact') GROUP BY arm;"
```

## Constraints
- Inherit `GOALS/README.md`. **Budget is a hard $20 cap** — check before every run; stop with margin.
- DB is the experiment `results.db` (local, gitignored). This goal is now read-only unless Zach
  explicitly reopens it; any manual DELETE/UPDATE still needs Zach's OK.
- Report faithfully: if a run doesn't complete or doesn't cross threshold, say so with the row.

## Out of scope
- New fixtures or arms. Re-running the low-pressure (hugelib) matrix (already n=4, done).

## Notes
- `phase1_turns` is per-fixture calibrated (speclib=35, scanlib=18); don't change without re-deriving
  from a continue transcript's 100k-crossing turn (see how it was done in the baton history).
