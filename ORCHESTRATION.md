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
- **Next (loop):** the **funded experiment** (5A.4, $20 cap) — start with ONE cheap
  `--arm continue` confirm-pilot on `debug-hugelib` (does it cross 100k?), report, then PAUSE
  for results before the full matrix. Alternative [claude] task if deferring spend: 5B.1 Nick
  data-surface spec.
