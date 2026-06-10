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

## When to run
Design now (done). **Run gated on a pilot signal**: if the BYU TTO pilot says
"interesting, but does it actually save money," we run it and return with a causal
number. That spends the token budget exactly when it converts a maybe into a yes.
