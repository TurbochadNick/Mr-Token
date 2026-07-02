# GOAL: Compaction gate — phase 2 (disposability gate)

**Lane:** Codex / Fable (backend Python, test-checkable) — but **map the signal path first** (below);
if the data source is unclear, stop and ask Claude to spec it. · **Status:** ready (phase 1 done, `0d92e55`) ·
**Est:** M · **Budget:** $0

**Loop exit (done-criteria):**
1. `evaluate()` (in `backend/mrtoken/intervene.py`) accepts a **disposability** input and only lets a
   `context_rot`-driven nudge **lead with the destructive `handoff`** when a reclaimable block is
   classified **disposable**; otherwise it keeps phase-1 behaviour (reversible `offload`, handoff advisory).
2. A block is **disposable** = read once (or early) and **not re-accessed for ≥K turns**; **load-bearing**
   = re-accessed recently or flagged by `re_read_loop`/`repeated_context`. Computed from the transcript
   `intervention_for_session()` already parses — **metadata only** (per-block last-seen turn; no content).
3. New unit tests: disposable → `handoff` may lead; load-bearing → stays `offload`; `evaluate()` stays pure.
   `./scripts/test-backend.sh` green (mod the known threshold-drift test, if still open).
4. If feasible, a transcript-replay check on the two fixtures: `debug-scanlib` (disposable notes) →
   classifies disposable → drop allowed; `debug-speclib` (load-bearing refs) → load-bearing → offload.
   Add to the 5D.3 golden set. If replay plumbing doesn't exist yet, note it and cover via unit tests.

## Why (root cause / spec)

Phase 1 (`0d92e55`) made the lone DROP path safe-by-default by never leading with `handoff` on
`context_rot`. But that also means the engine now **never** recommends a reset even when one would win
(the disposable regime, ~30% cheaper — `docs/ROI-EXPERIMENT.md` RESULTS). Phase 2 restores the *useful*
drop, but **gated on disposability** — the term `docs/COMPACTION-GATE.md` calls Gate 1 (re-read_risk).
This is the first of the two real gates; phase 3 adds remaining-runway.

## Steps

1. **Map the signal path FIRST** (don't guess): find where the reclaimable signals
   (`huge_tool_output`, `re_read_loop`, `repeated_context`, `context_rot`) are *detected* from the
   transcript — start at `intervention_for_session()` in `intervene.py` and the detectors in
   `backend/mrtoken/rules.py` / `validate.py` / `watch`. Confirm what per-block info is available
   (block id/hash, first-seen turn, last-seen turn). State it before coding.
2. Compute a per-block disposability classification from last-access recency (pick K, make it a named
   constant). Load-bearing if `re_read_loop`/`repeated_context` implicate the block.
3. Thread `disposability` into `evaluate()` as a new keyword input (default None = phase-1 behaviour, so
   nothing regresses when the caller doesn't pass it). Only a disposable target unlocks a lead-`handoff`.
4. Tests (unit + fixtures per Loop-exit). Run `./scripts/test-backend.sh`; paste the tail.
5. Commit on the branch; Claude/Zach reviews the diff.

## Verify

```bash
cd <repo> && ./scripts/test-backend.sh 2>&1 | tail -15
```

## Constraints
- Inherit `GOALS/README.md`. `evaluate()` stays **pure**; default-None keeps phase-1 behaviour intact.
- **Privacy:** per-block last-seen turn / hashes / sizes only — never block content.
- Do NOT touch the phase-1 `offload` routing for huge/re_read/repeated. One root cause per change.

## Out of scope
- Phase 3 (remaining-runway / near-done suppression) — separate brief.
- 6.8 L3 auto-act. Any change to what the detectors themselves emit.

## Notes
- If the transcript doesn't expose per-block last-access cheaply, the honest move is to **stop and flag
  it** — the disposability gate is only as good as that signal. Don't fake it with a proxy that can't
  tell scanlib from speclib.
