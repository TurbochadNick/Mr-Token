# GOAL: A real in-the-wild ROI number (cross-session linkage for `roi --measure`)

**Lane:** Codex or Claude (spec + build, test-checkable) · **Status:** ready · **Est:** M ·
**Budget:** $0 (runs on already-captured transcripts)

**Loop exit (done-criteria):**
1. `mrtoken-transcript roi --measure` produces a **non-degenerate method B** — i.e. it can populate
   an "acted" cohort, not 100% "ignored" — by detecting that a *separate fresh session* started in
   the same project shortly after a `fresh_handoff` fired (cross-session linkage), instead of
   splitting a single session at its midpoint.
2. The headline counterfactual (method C) is unchanged/still reported; B is now corroborating, not
   degenerate.
3. Tests cover the linkage logic on a synthetic corpus; `./scripts/test-backend.sh` green.
4. `backend/docs/ROI-EXPERIMENT.md` "Observational estimate" section updated with the new B result.

## Why (root cause, stated)

`ROI-EXPERIMENT.md` records: on the 153-session backfill, method C projected ~$40.70, but **method B
was degenerate — all 20 fired sessions fell in "ignored", zero "acted"** — because `fresh_handoff`
only fires once a session is already deep, so a within-session midpoint split can never yield an
"acted-early" cohort. The fix the doc already names: **detect a separate fresh session started in the
same project shortly after the fire** (cross-session linkage), and treat that as "acted." Until then
the in-the-wild ROI has no honest corroboration — the credibility gap for the pitch.

## Steps

1. Read `backend/mrtoken/roi.py` (the `--measure` path, methods B and C) and the ROI doc's
   "Observational estimate" section. State the current B logic in one line before changing it.
2. Design the linkage: for each session where `fresh_handoff` fired at time T in `project_path` P,
   look for another trace with the same `project_path` and `started_at` within a window (e.g. ≤ N
   minutes/hours after T) → classify the fired session as **acted**; else **ignored**. Use only
   `session_summary`/`trace` fields already available (started_at, project_path, session_id).
3. Implement it behind the existing `--measure` command; keep C as the headline, B as corroboration.
   Label B honestly (still observational / selection-biased).
4. Add tests on a **synthetic** corpus that includes both an acted (fresh follow-on session) and an
   ignored (long single session) case; assert B classifies each correctly and the number is finite.
5. Run `./scripts/test-backend.sh`; paste the tail. Update the ROI doc with the refreshed B result.

## Verify (commands)

```bash
cd <repo> && ./scripts/test-backend.sh 2>&1 | tail -15
# and, on a real/backfill DB if handy (read-only):
mrtoken-transcript roi --measure --db <path> 2>&1 | tail -20
```

## Constraints
- Inherit `GOALS/README.md` global rules. Read-only against real DBs (SELECT/EXPLAIN only) — no writes.
- Don't overclaim: B stays labelled observational + selection-biased. C remains the headline.
- Linkage window is a judgement knob — pick a defensible default, make it a constant, note it.

## Out of scope
- The controlled trial (that's 5A, done). Any change to method C's projection math.
- Dashboard surfacing of the number (separate 5B work).

## Notes
- The window default and "same project" definition are the two decisions; if a real corpus is
  available, sanity-check the window by eyeballing a couple of linked pairs before finalizing.
