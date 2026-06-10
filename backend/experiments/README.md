# MR Token — ROI experiment harness

Implements the experiment in `../docs/ROI-EXPERIMENT.md`: does acting on MR
Token's reset advice cut tokens at equal quality, and beat `/compact`?

## Layout

```
experiments/
  runner.py              # drives a task through an arm, records exact tokens
  tasks/<task-id>/
    manifest.json        # task config (oracle, reset threshold, immutable files)
    TASK.md              # the prompt handed to the test agent
    oracle.sh            # exit 0 iff the task is correctly complete
    seed/                # the starting repo state (copied fresh per run)
  results/results.db     # one row per run (created on first run)
```

## Fixture contract

A task is **reproducible** (fresh copy of `seed/` per run), has an **objective
oracle** (`oracle.sh` returns 0/1, no judgment), and lists **immutable files**
the agent must not edit (usually the test file — stops the agent "passing" by
deleting tests). The oracle must check immutability too.

**Sizing caveat:** a task must reliably bloat past the reset threshold (default
100k input-side tokens) before it completes, or the reset/compact/handoff arms
never trigger and the run is wasted. The bundled `debug-stringkit` task is small
(it validates the oracle + recorder plumbing); real measurement tasks must be
sized to bloat (a larger codebase) or sourced from a real repo at a known commit.
Pilot each task once and confirm it crosses the threshold before running the full
matrix.

## Arms (Experiment 1)

- `continue` — run straight through, never reset (baseline)
- `compact`  — at the reset point, compact context, continue same session
- `handoff`  — at the reset point, `mrtoken-transcript handoff`, start fresh with
  the handoff + original prompt

All arms: Sonnet, medium effort, pinned identically. K reps each, interleaved.

## Status

Scaffold + fixture format + recorder are here. The **live agent runner** (driving
Sonnet headless to completion and applying the intervention at the reset point) is
the integration seam marked `drive_agent()` in `runner.py` — wiring it to the
Claude Agent SDK / headless `claude` is the next build step.
