# ROI Experiment Design — does MR Token's advice actually save tokens?

*Status: DESIGNED. The run is gated on a pilot signal (see "When to run"). This
doc is the spec so the run is push-button when we decide to spend the budget.*

## The claim we are testing

"Acting on MR Token's reset advice cuts the tokens a task costs, **at equal task
quality**, and **beats the free built-in alternative (`/compact`)**."

Two phrases carry all the weight:
- **At equal quality.** A cheaper run that does a worse job proves nothing. Every
  comparison is gated on an objective completion oracle. No oracle, no data point.
- **Beats `/compact`.** The honest competitor is not "do nothing," it is Claude
  Code's built-in compaction. If compact wins, the wedge shifts from "the handoff
  mechanism" to "knowing *when* to reset" (the trigger), which is still valuable
  but a different pitch. We design to find that out.

## Two experiments, isolated (do not muddle)

- **Experiment 1 — handoff effect.** At a FIXED reset point, compare three arms:
  continue / compact / handoff. Answers: does a well-placed handoff beat compact
  and continue, at equal quality? (The mechanism question.)
- **Experiment 2 — trigger timing.** Gated on Exp 1 showing reset can help. Holds
  the mechanism fixed, varies the reset POINT (MR Token's trigger vs early / late
  / random). Answers: does MR Token pick good moments? (The trigger question.)

Running both at once tells you nothing clean: you cannot tell whether a result
came from the handoff or from when it fired. Prove the mechanism first.

---

## Experiment 1 — handoff effect

### Arms (same task, same everything except the intervention)
1. **continue** — run straight through in one session, never reset (baseline).
2. **compact** — at the reset point, invoke `/compact`, continue the same session.
3. **handoff** — at the reset point, run `mrtoken-transcript handoff`, start a
   FRESH session seeded with the handoff text + original task prompt, continue.

### Fixed reset point
To isolate the mechanism from trigger timing, all arms reset at the SAME
pre-set point. Default: when cumulative input-side context first crosses
**100k tokens** (measured live from the transcript, which we already do in
`watch`). Continue never resets; compact and handoff reset exactly there.

### Test agent (the "dummy") — LOCKED
- **Sonnet at MEDIUM reasoning effort** (pin the exact model id). Capable enough
  that completion is not gated by model weakness (a weak model that fails a lot
  would confound the equal-quality comparison), far cheaper than Opus, and medium
  effort is the realistic default for cost-sensitive agent usage. Pin model id,
  temperature, and effort=medium identically across ALL arms and reps.
- **Optional replication: Haiku.** Cheap, and tells us whether the effect holds
  on a weaker model (which may bloat differently). Secondary because higher
  non-completion muddies the quality gate.
- **What actually matters: the model is FIXED across arms.** The comparison is
  within-model. Pin model id, temperature, and thinking/reasoning effort (it
  swings token counts hard) identically across all arms and reps.

### Tasks (the crux — each needs a hard oracle and reliable context bloat)
Each task is a seed git repo at a fixed commit + a fixed initial prompt + a
hidden pass/fail oracle (a command that returns 0/1). Candidates:

| Task | Bloats context via | Oracle (objective completion) |
|---|---|---|
| T1 Multi-file refactor | reading/editing many files | existing test suite still passes |
| T2 Debug failing suite | repeated reads + test runs | seeded-bug suite goes green |
| T3 Implement feature to spec | reading + building across files | hidden acceptance tests pass |

Start with **T1 and T2** (cleanest oracles). Tasks must be reproducible from the
seed commit and must reliably exceed the reset threshold (pilot each once to
confirm it bloats past 100k).

### Reps
K = 5 per (task × arm) to start, to average agent stochasticity. Raise to 10 if
variance is high. Interleave runs across arms (do not run all-continue then
all-handoff) to avoid any time-based drift.

### Metrics
- **Completion (gate):** oracle pass/fail. Compare tokens ONLY among completed
  runs. Report completion rate per arm separately — a cheaper arm that fails more
  is not a win, it is a regression.
- **Primary:** total tokens to completion (input + output + cache) and est cost.
  Measured exactly from transcripts by the backend (our existing strength).
- **Secondary:** wall-clock, step count, tool-error/retry count.

### Analysis + decision rule
Per task, compare the DISTRIBUTION (median + spread, not a single mean) of
tokens-to-completion across arms, among completed runs.

- **Wedge validated** if handoff reduces tokens-to-completion by a meaningful
  margin (pre-register the threshold, e.g. >=20%) vs BOTH continue AND compact,
  at equal-or-better completion rate.
- **Reposition** if compact ≈ handoff: value becomes the trigger ("knowing when"),
  not the mechanism. Lead the pitch with that instead.
- **Sharpen trigger** if handoff helps only past some context size, or hurts below
  it: the `fresh_handoff` rule should only fire past that size.

### Possible outcomes (this must be falsifiable)
Designed so it CAN disprove the wedge. Handoff can lose context, cause rework,
and cost more, or lower completion. If that is the truth, we want to learn it now,
cheaply, not after pitching it. An experiment that can only confirm is theater.

### Cost
Exp 1 = 2 tasks x 3 arms x 5 reps = 30 runs (or 45 with 3 tasks). At Sonnet rates,
order of magnitude a few million tokens total, roughly tens of dollars. Set a hard
budget cap in the harness and abort if exceeded.

---

## Experiment 2 — trigger timing (sketch, gated on Exp 1)

Hold the handoff mechanism fixed. Vary only the reset point policy:
MR Token's `fresh_handoff` trigger vs reset-early / reset-late / reset-at-random.
Same tasks, same metrics. Question: does MR Token's trigger beat naive policies on
tokens-to-completion at equal quality? This validates the trigger, which (if
compact won Exp 1) may be the actual product value.

---

## Harness — mechanism LOCKED: headless `claude -p`

Driver is the **`claude` CLI in headless `-p` mode** (not a separate SDK):
- `--model claude-sonnet-4-6`, pinned temperature/effort, identical across arms.
- `--max-budget-usd <cap>` — built-in hard budget cap per run (abort if exceeded).
- `--output-format json` — returns `session_id` + usage/cost per run.
- session persistence ON → writes the transcript JSONL that the backend already
  parses, so **measurement reuses our existing instrument** (mrtoken ingest).
- Auth = the user's subscription (no API key needed).

Intervention at the reset point uses a **phased** approach (a single `-p` call
runs to completion and can't be paused mid-run):
- **continue**: one `claude -p` to completion.
- **handoff**: phase 1 `claude -p --max-turns K` (K calibrated so context nears
  100k), then `mrtoken-transcript handoff` on phase-1's transcript, then a FRESH
  `claude -p` seeded with the handoff + original prompt to completion.
- **compact**: phase 1 as above, then continue the SAME session via `--resume`
  with context compaction, to completion.

UNKNOWNS to settle with a 1-run smoke test (cheap, not the full matrix): does
headless honor compaction; does `--resume` chain cleanly; what K reaches ~100k
per task. The runner is built + mock-validated first so only these remain.

### Build steps

1. **runner**: drive the test agent headless to completion (`claude -p`), detect
   the reset point from the transcript (reuse `watch`'s tracking), apply the arm's
   intervention via the phased approach above.
2. **task fixtures**: seed repos + oracle commands + prompts, version-controlled
   under `backend/experiments/tasks/`.
3. **recorder**: per-run row (task, arm, rep, model, completed?, tokens, cost,
   wall-clock, steps, errors) into a results SQLite, measured from the transcript.
4. **analysis**: aggregate to the per-task arm comparison + distributions, with the
   decision rule applied. Reuse the backend's measurement code.

The measurement instrument already exists (we read transcripts for exact tokens).
The new build is the runner + fixtures + oracle plumbing.

## Locked decisions
- **Tasks:** start with **T1 (multi-file refactor)** and **T2 (debug failing
  suite)**, both with real test-suite oracles.
- **Reset point:** **fixed 100k tokens** of input-side context (faithful to
  "context got big"; not a step count).
- **Pre-registered win thresholds (tiered):** **>=5% token reduction = success
  signal** (worth pursuing); **>=10-15% = real victory** (the pitch-worthy number).
  Decided before running so we cannot move the goalposts. Reported vs BOTH the
  continue and compact arms, gated on equal-or-better completion rate.
- **Test agent:** Sonnet, medium reasoning effort, pinned across all arms.

## Pilot 1 results (2026-06-04) — continue vs handoff, short task

First real run. Harness validated end to end with live Sonnet agents (spawn ->
solve -> oracle -> measure exact tokens). Fixture: `debug-widgetlib` (3 modules,
7 seeded bugs, ~14 turns to solve, ~5-10k tokens — a SHORT, non-bloated task).
Handoff reset at a turn-count midpoint (phase1 = 7 of ~14 turns) as a proxy for
the 100k token threshold. 3 reps per arm.

| arm | runs | completed | median tokens |
|---|---|---|---|
| continue | 3 | 3/3 | 9,337 |
| handoff | 3 | 3/3 | 10,720 |

**Result: handoff cost ~15% MORE than continue, at equal completion (3/3 both).**

This does NOT refute the wedge — it maps its boundary, honestly. On a short,
non-bloated task there is little carried context to shed, so the reset+handoff
overhead (generating the handoff + re-establishing context in a fresh session)
outweighs the carry savings. This is exactly why the `fresh_handoff` rule only
fires on DEEP/bloated sessions, and it is a useful guardrail: do not hand off
short tasks. It would have been easy to pick a bloated task and "confirm" the
wedge; the pilot instead shows where the handoff does and does not pay.

**What this proves / what it does not:** proven — the harness measures real
causal token deltas at equal quality, and short-task handoff is a net loss.
NOT yet tested — the regime the wedge actually claims (a session bloated past
~100k, where carry cost dominates). That needs a genuinely bloating fixture (or a
real long session), which is the next, larger build. Pilot 1 is the boundary; the
wedge-confirming run is still ahead.

## Pilot 2 results (2026-06-05) — continue vs handoff, larger task

Fixture: `debug-largelib` (5 modules, 19 functions, 17 seeded bugs). Bigger than
pilot 1. Handoff reset at a turn-count midpoint (phase1 = 12). 3 reps per arm.

| arm | completed | tokens | median | spread |
|---|---|---|---|---|
| continue | 3/3 | 11.3k / 12.4k / 53.2k | 12.4k | 4.7x |
| handoff | 3/3 | 12.1k / 32.4k / 35.7k | 32.4k | 3.0x |

**Inconclusive, and the setup structurally cannot confirm the wedge yet.** Three
reasons, all useful findings:

1. **The task does not reliably bloat.** Continue solved it in ~12k tokens twice
   and only reached 53k once; peak CARRIED context was ~34k, never near 100k.
   Agents are efficient and do not hoard context unless the task forces it.
2. **Handoff has a fixed overhead floor** (~20k: regenerate context in a fresh
   session). It can only pay when the context it sheds exceeds that floor, i.e.
   well above ~34k. On the common ~12k path the reset is pure overhead.
3. **A fixed turn-count reset is miscalibrated under this variance.** phase1=12
   was set from a 23-turn outlier, but most runs finish in ~12 turns, so the
   reset fired at/after completion and phase 2 was redundant.

**Refined claim:** the handoff is NOT a general token saver; it can only pay for
genuinely bloated sessions, and the crossover is well above what these fixtures
reach. This matches why `fresh_handoff` only fires on deep/bloated sessions, and
it is an honest guardrail against over-claiming.

**What a conclusive pilot 3 needs (a design change, not more reps):**
- a fixture that RELIABLY pushes carried context past ~100k (forced large reads:
  big files the task must consult, or a much larger bug set), OR a real long
  session replayed;
- a TOKEN-threshold reset (reset when context crosses 100k), not a turn count —
  needs mid-run control the headless `-p` flow lacks, so likely the Agent SDK
  with a turn loop, or a transcript-watching reset;
- more reps (>=5-10) to beat the 3-5x path variance.

Stopping paid runs on the current setup: it answers the boundary, not the claim.

## When to run
Design now (done). **Run gated on a pilot signal**: if the BYU TTO pilot says
"interesting, but does it actually save money," we run it and return with a causal
number. That spends the token budget exactly when it converts a maybe into a yes.

---

## Observational estimate — `roi --measure` (no budget; runs on the corpus)

The controlled trial above is the gold standard but costs budget. As a free
complement that runs on already-captured sessions, `mrtoken-transcript roi
--measure` gives a before/after ESTIMATE for `fresh_handoff`. It is NOT causal and
does not replace Exp 1 — it is the cheap "is this even worth a trial" read.

Two methods, both honestly labelled (ROADMAP 2.1):

- **C — counterfactual projection (headline; no behaviour assumed, no selection
  bias).** For each session where `fresh_handoff` fired, project the next-`horizon`
  calls at the session's late-stage per-call burn vs a **lean-restart baseline** =
  mean est cost over the opening 5 calls across the whole corpus. Saving =
  `max(0, late_per_call − lean_per_call) × horizon`, summed. It is a *marginal*
  number (a fresh session re-accumulates), not a forever saving.
- **B — acted vs ignored (corroboration; OBSERVATIONAL, selection-biased).** Split
  fired sessions into "acted" (ended soon after the signal) vs "ignored"
  (continued) and compare late-stage per-call cost.

**First run on the 153-session backfill corpus (2026-06-23):** C projected
~$40.70 across 20 fired sessions (lean baseline ~$0.057/call). **B was degenerate:
all 20 fell in "ignored", zero "acted"** — because `fresh_handoff` only fires once
a session is already deep, so a within-session midpoint split can never yield an
"acted-early" cohort. **Refinement needed:** a real B must detect that a *separate
fresh session* started in the same project shortly after the fire (cross-session
linkage, ROADMAP backlog), not split a single session. Until then, treat C as the
estimate and B as not-yet-informative.
