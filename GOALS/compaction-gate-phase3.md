# GOAL: Compaction gate — phase 3 (remaining-runway gate) — completes the gate

**Lane:** Codex / Fable (backend Python) — **design-heaviest of the three; if the runway signal can't
be derived honestly, stop and flag it** (a bad proxy is worse than none). · **Status:** ready after
phase 2 · **Est:** M–L · **Budget:** $0

**Loop exit (done-criteria):**
1. `evaluate()` (in `backend/mrtoken/intervene.py`) takes a **progress/runway** input and **suppresses
   the reset nudge when the task looks near-done** — even under pressure and even on disposable context
   — because with little runway left, `summary + re-establish` cost exceeds the per-turn carry saved
   (the speclib late-burst case, `docs/ROI-EXPERIMENT.md`).
2. Composes with phase 2: a lead-`handoff` DROP now requires **disposable target AND runway remaining**;
   otherwise `offload`/advisory; near-done → suppress entirely.
3. Default-None input preserves phase-1/2 behaviour (no regression when the caller doesn't pass it).
   `evaluate()` stays pure. `./scripts/test-backend.sh` green.
4. Unit tests for the runway logic (near-done → suppress; mid-session + disposable → drop allowed;
   pressure without runway data → falls back to phase-2 behaviour).

## Why (root cause / spec)

`docs/COMPACTION-GATE.md` Gate 2. The regime map shows the reset benefit scales with
`turns_remaining`; the speclib fixture crossed the threshold late (turn ~32 of ~53) with little runway
left, which is part of why reset didn't pay there. `turns_to_full` (context wall) ≠ `turns_to_task_done`
(runway) — the engine has the former, lacks the latter. This gate adds a conservative runway proxy so
the engine won't nudge a reset when the agent is ~one fix from done. **This is the last gate: once it
lands, 6.8 (L3 auto-act) can proceed — auto-drop ONLY in the disposable ∧ runway-remaining case.**

## Runway proxies (pick defensible ones; they're all imperfect — bias toward NOT suppressing real wins)

- **Progress trend** (best signal): tests going red→green, diagnostic/error count falling, edits/writes
  accumulating (durable artifacts landing) → likely near done → suppress. Derivable from the transcript
  the engine already parses (tool_call outcomes over recent turns).
- **Session trajectory**: very early/mid → runway long. Crude but cheap.
- **Optional explicit**: let the `mr-context` skill / a toolbox call report "N items left" so the agent
  can override the proxy. Highest precision when available.

Since runway is fundamentally uncertain, **ship this warn-only** and gate auto-act (6.8) behind
real-session validation via `outcomes.py` (6.7) — a suppression that costs a win should show up there.

## Steps
1. Read `docs/COMPACTION-GATE.md` (Gate 2) + `intervene.py` (`evaluate`, `intervention_for_session`).
   Confirm what recent-turn progress info is cheaply available (tool_call results, test outcomes).
   State it before coding.
2. Implement a conservative `near_done` / runway signal; thread `progress` into `evaluate()` (kwarg,
   default None). Suppress the reset nudge when near-done.
3. Unit tests per Loop-exit. Run `./scripts/test-backend.sh`; paste the tail.
4. Commit on a branch off current `main`; Claude/Zach reviews.

## Verify
```bash
cd <repo> && ./scripts/test-backend.sh 2>&1 | tail -15
```

## Constraints
- Inherit `GOALS/README.md`. `evaluate()` pure; default-None keeps phase-1/2 behaviour intact.
- **Privacy:** derive runway from metadata (tool outcomes, counts) — never prompt/content.
- One root cause per change; don't touch phase-1/2 routing. Bias the proxy toward *under*-suppressing
  (missing a suppression is cheap; suppressing a real win is the costly error).

## Out of scope
- 6.8 L3 auto-act itself (separate; this unblocks it). Changing what the detectors emit.

## Notes
- If recent-turn progress can't be read cheaply/honestly from the transcript, **stop and say so** —
  propose what capture would be needed rather than shipping a proxy that can't tell near-done from mid-task.
