# GOAL: Compaction gate — phase 1 (make the one DROP nudge safe-by-default)

**Lane:** Codex or Claude (scoped, test-checkable — good Codex hand-off) · **Status:** ready ·
**Est:** S–M · **Budget:** $0 (no live agent runs)

**Loop exit (done-criteria):**
1. In `backend/mrtoken/intervene.py`, a `context_rot`-driven nudge **no longer leads with a
   destructive `handoff`** when there is no disposability signal — it defaults to the reversible
   path (`offload`) or an explicitly *advisory* "consider `handoff`" message.
2. `re_read_loop` / `repeated_context` / `huge_tool_output` behaviour is **unchanged** (they already
   route to `offload` — the safe choice; do not touch).
3. New unit tests encode the two regimes and pass; `./scripts/test-backend.sh` is green.
4. The change is behind existing `policy.py` toggles and keeps `evaluate()` pure/agent-agnostic.

## Why (root cause, stated)

The 5A regime map (`backend/docs/ROI-EXPERIMENT.md` → RESULTS) shows a reset **wins** on disposable
context and **loses (+20%)** on load-bearing. Per `backend/docs/COMPACTION-GATE.md`, `_tool_for()`
already routes the re-read/repeat/huge signals to `offload` correctly. The **only destructive nudge**
is `context_rot → handoff`, and `context_rot` is a *generic* "session ran long / filling up" signal
that carries **no** disposable-vs-load-bearing information. So the sole DROP recommendation fires on a
signal that can't tell the win regime from the lose regime. It's L1 "tell" today (low stakes), but it
is the exact path that must not reach L3 auto-act (6.8) ungated. Phase 1 makes it safe-by-default now;
phases 2–3 (disposability recency, runway proxy) add the real gates later.

## Steps

1. Read `backend/mrtoken/intervene.py` (`_tool_for`, `evaluate`) and `backend/docs/COMPACTION-GATE.md`.
2. Change the `context_rot` branch so that, **without** a disposability signal, it does NOT emit a
   plain `handoff` action. Pick the cleanest of:
   - return `offload` with a message noting a full handoff may help if the loaded context is no
     longer needed; **or**
   - keep `tool="handoff"` but mark it advisory and reword so it doesn't read as "drop now" (it must
     be clearly optional, agent's judgement).
   Prefer the reversible framing (`offload`) when uncertain — dropping is destructive.
3. Add unit tests in the backend test suite:
   - **disposable regime** (scanlib-like): signals `{huge_tool_output}` under pressure → `offload`
     nudge fires (unchanged).
   - **load-bearing regime** (speclib-like): `{re_read_loop}` / `{repeated_context}` → `offload`, and
     `{context_rot}` alone → **not** a lead-with-drop `handoff` (assert the new behaviour).
   - pressure without any reclaimable signal → still `None` (unchanged).
4. Run `./scripts/test-backend.sh` and paste the pass/fail tail.
5. Commit on a branch; if extending the pushed `experiment/compaction-regime-map`, add a new commit.

## Verify (commands)

```bash
cd <repo> && ./scripts/test-backend.sh 2>&1 | tail -15
```

## Constraints
- Inherit `GOALS/README.md` global rules. Root-cause-first; done = tests run + output shown.
- Do NOT change `offload` routing for huge/re_read/repeated. One root cause per change.
- No new capture; privacy-invariant (signals only, no content).

## Out of scope (later phases / other briefs)
- Gate 1 disposability recency (per-block turns-since-access) and Gate 2 runway proxy — separate briefs.
- 6.8 L3 auto-act. Transcript-replay golden using the fixtures (nice, but not required for phase 1).

## Notes
- If you decide the `context_rot` semantics genuinely need `handoff` (not `offload`), that's a
  judgement call — implement the *advisory* variant and note the reasoning in the commit; don't stall.
