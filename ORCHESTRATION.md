# Mr Token — how Claude + Codex work this repo (operating model)

*Partners, not rivals or fallbacks. This is how we run the ROADMAP on a loop and hand
off cleanly. Last set 2026-07-01.*

## Roles (default, override per task)
- **Claude — lead on Mr Token** (TTO/work-adjacent: co-built with Nick, a BYU TTO pilot).
  Owns: planning, decomposition, judgment calls, code review, merges, long-horizon
  coherence, and talking with Zach. Drives the loop.
- **Codex — partner + failover.** Owns scoped, async, well-specified, test-checkable work
  (a spec'd feature, a mechanical refactor, a long diagnostic) and strong structured output.
  Either agent consults the other for a second opinion when the other's strengths fit.

## The bus is git
- **`ROADMAP.md`** is the shared, loop-able task list. Each open task is owner-tagged:
  - `[claude]` — Claude leads it.
  - `[codex]` — hand to Codex (scoped/async/test-heavy). Brief lives in the task line.
  - `[zach-gated]` — needs Zach: budget, trust, or an outward action. The loop STOPS here.
- Work happens on a branch; the other reviews the diff and merges. `/mr-handoff` optional.

## Running the loop
Each tick: pick the first unchecked task → if `[codex]`, hand it off (branch brief, note, or
live `codex exec`); if `[claude]`, do it → test → review → commit on a branch → update the
ROADMAP checkbox + the **Handoff note** below → next. Stop at `[zach-gated]`.

## Credit-out failover (Claude → Codex, don't stall)
If Claude runs low/out of credits mid-loop, Codex takes over by reading `ROADMAP.md` + the
Handoff note and continuing the next `[claude]`/`[codex]` task. The plan is self-describing,
so no live relay is required. Same in reverse.

## Safety gates (unchanged; do NOT change hands)
Confirm with Zach before anything **destructive, outward-facing, secret-touching, or
live-database** — whoever is driving. `[zach-gated]` tasks always pause for Zach.

## Standing decisions
- **Experiment (5A.4) budget: $20 cap** (greenlit 2026-07-01). The loop may run it within that
  cap; a single run passes `--budget-usd` and stops before exceeding. Re-confirm to raise.
- **This phase's focus: Adopt (beta)** — pilot one-pager + TTO framing + onboarding + evidence;
  the experiment is the fast-follow now that it's funded.

## Handoff note (keep current — the failover baton)
- **State (2026-07-01):** v0.5.8 on `main`, clean, all PRs merged.
- **Reconciled:** Adopt build-work (5C.1/5C.2) was already done by Codex —
  `BETA-TESTER-NOTE.md` (one-pager), `BYU-TTO-PILOT.md` (TTO framing), `BETA-TESTING.md`,
  `beta.py`/`beta_evidence.py`. Marked done in ROADMAP. Remaining Adopt = **Zach's outreach**
  (contact testers per `INTERVIEW-KIT.md`) — not a loop task.
- **Experiment (5A.4) — IN PROGRESS. Spend ~$5.4 of $20** (est.; confirm from `results.db`).
  Latest commits: `fccd33a` (harness fix), `89325c4` (30k config). Results DB (gitignored):
  `backend/experiments/results/results.db`, table `run`.
  - **Harness fixed** (`experiments/runner.py`): `_peak_carried_tokens` = MAX per-turn carried
    context (was a cumulative SUM that crossed any threshold trivially); the `continue` arm now
    records `peak_input_tokens`/`crossed_threshold`. **Cost (cache-weighted) is the honest burn
    metric**; `total_tokens` (in+out) is cache-blind — secondary only.
  - **Fixture decision (Zach, 2026-07-01):** the confirm-pilot proved `debug-hugelib` peaks ~45k
    and finishes in ~10 turns (refs are filler, tests hardcode outputs → agent skips the reading).
    Rather than rebuild, Zach chose to **lower the threshold** (`reset_threshold_tokens` 100k→30k,
    `handoff_phase1_turns` 16→5) and study the **low-pressure quadrant** now, accepting a weak signal.
  - **LOW-PRESSURE RESULT (30k config, crossed_threshold=1 rows):** all arms 100% complete
    (quality held). continue **$0.33** (n=4, peak 69k) < compact **$0.39 +21%** (n=4, peak 78k)
    < handoff **$0.47 +45%** (n=3, peak 88k). Reps mattered: at n=1 handoff read as +278%
    (a $0.72 outlier rollout); n=4 collapsed it to +45%. Conclusion: at low pressure / short
    runway, resetting costs modestly more (no wall to avoid) — the "compaction loses" quadrant,
    as predicted. ⚠ **handoff needs 1 more rep for n=4** — top off:
    `cd backend/experiments && python3 runner.py tasks/debug-hugelib --arm handoff --budget-usd 4 --reps 1`
- **Next (after reps):** consolidate mean cost ± spread + completed/crossed rates → that's the
  low-pressure data point. THEN the interesting half of the question: **build a load-bearing
  fixture** (per-module reference holds the ONLY concrete behavior; property-based tests, not
  hardcoded examples; distinct per-module logic; sized to cross 100k) to reach the regime where
  **early compaction wins**. Good [codex] hand-off (scoped; done-criteria = confirm-pilot shows
  `crossed_threshold=1`).
- **Open research thread (Zach):** *when does compacting early have benefits?* Working model —
  early compaction pays iff `reclaimable_tokens × per-turn-carry-cost × turns_remaining >
  summary_cost + re-establish_cost + re-read_risk`. Three gates: reclaimable-junk (engine has it),
  pressure (engine has it), and **remaining runway = turns-to-*task-done*** (engine LACKS it —
  candidate proc-engine refinement so it won't nag "compact!" when one fix from done).
