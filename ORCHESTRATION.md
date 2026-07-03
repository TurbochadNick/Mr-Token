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
- **Fable 5 (`claude-fable-5`) — conditional peak-coding executor.** Reinstated 2026-07-01 (export
  controls lifted). If Zach runs it, he'll launch it in a **second K2 pane on this workspace**; treat
  it like Codex — hand it a scoped `GOALS/` brief on its own branch/worktree, review the diff, merge.
  **A/B before adopting** (the ~95% SWE-bench is pre-suspension). Full setup + K2 collision-avoidance:
  `ONBOARDING.md`. Decision to use it is Zach's.

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
- **State (2026-07-02):** v0.5.8. This session's work is **MERGED to `main`** via PR #18
  (merge commit `24cef87`): 5A regime-map experiment (DONE), compaction-gate spec + **phase 1**
  (Fable) + **phase-2 brief**, ROI `--measure` cross-session linkage (Fable), `GOALS/` loop briefs,
  5B.1 (`UI-INTEGRATION.md`) + 5B.2 (`HANDOFF-TO-NICK.md` refreshed — ⏳ Zach forwards to Nick), and
  Fable enablement (`ONBOARDING.md` + K2 coordination). Global (not in-repo): `/which-model`
  snapshot updated for Fable's 2026-07-01 reinstatement. Experiment spend **$17.46/$20**.
- **`disposable_confirmed` channel BUILT (Claude, 2026-07-03, PR #20).** The explicit path to 6.8 L3:
  `confirm_disposable` MCP tool → session-scoped, metadata-only confirmation (call-index + ts, TTL
  10 calls / 30 min); `intervention_for_session` merges a FRESH one so `decide()` can escalate; stale/
  absent → proxy tell-only (fail-closed). Skill doc updated; 92 tests green. **Routing note:** kept
  in-house rather than dispatched — Fable is a scarce cross-project contractor, and this was
  de-risked + handleable, so not worth a contractor hour (see memory `fable-is-a-scarce-contractor`).
- **Compaction gate COMPLETE + MERGED (Fable built, Claude reviewed 2026-07-03): PR #19 → `main`
  merge commit `9131691`.** Gate 1 disposability (`8b61165`) + Gate 2 runway (`1208c6b`); 91 backend
  tests green; default-None inputs keep old callers byte-identical. Claude review: code correct,
  `evaluate→decide` contract verified, the falsification independently reproduced (below). Merge-safe
  because it enables NO auto-act (proxy capped at tell).
- **⚠ Gate 1 proxy FALSIFIED at the real reset point (Fable, 2026-07-02, evidence on PR #19).**
  Built the 5D.3 replay oracle (`backend/experiments/replay_gate.py`, `a3804fd`) and ran the
  real 5A phase-1 transcripts through the gate: scanlib → drop ✓, but speclib `2whh9wno` →
  93% disposable share → drop **in the +20% lose regime**; the other speclib run says offload
  purely on 1–2 calls of read-timing jitter. Recency can't see future re-need. Stopped per the
  phase-2 brief; no classifier tweak committed (early-singleton variant tried + reverted).
  **Option 1 IMPLEMENTED (`b9a52c6`):** proxy-unlocked drop = consent question, capped at L1
  tell in decide(); only an explicit `disposable_confirmed` (mr-context/toolbox channel, not
  yet built) escalates — the hard line for 6.8 L3. Open follow-ups: huge-block-only unlock
  (needs more fixture regimes), 6.7 outcomes learning, golden fixtures once contract reviewed.
- **Reconciled:** Adopt build-work (5C.1/5C.2) was already done by Codex —
  `BETA-TESTER-NOTE.md` (one-pager), `BYU-TTO-PILOT.md` (TTO framing), `BETA-TESTING.md`,
  `beta.py`/`beta_evidence.py`. Marked done in ROADMAP. Remaining Adopt = **Zach's outreach**
  (contact testers per `INTERVIEW-KIT.md`) — not a loop task.
- **Experiment (5A.4/5A.5) — DONE. Spend $16.75 of $20.** Full write-up in
  `backend/docs/ROI-EXPERIMENT.md` → "RESULTS — the regime map". Results DB (gitignored):
  `backend/experiments/results/results.db`, table `run`. Cost = cache-weighted burn (honest metric).
  - **THE REGIME MAP (continue vs reset arms, all at equal completion):**

    | Regime | Fixture | Thr | continue | handoff | compact | Verdict |
    |---|---|---|---|---|---|---|
    | Low pressure | debug-hugelib (n=4) | 30k | **$0.327** | +26% | +20% | reset LOSES |
    | High, load-bearing | debug-speclib (n≈1) | 100k | $1.237 | +20% | ≡cont¹ | reset TIES/LOSES |
    | High, disposable | debug-scanlib (n=2) | 100k | $1.423 | −22% | **−28%** | reset **WINS ~30%** |

    ¹ speclib compact = pre-fix degenerate arm; load-bearing verdict rests on handoff (+20%).
  - **ANSWER:** early reset pays when accumulated context is **DISPOSABLE** (reclaimable, low
    re-read_risk) with work remaining — NOT when merely large. Decisive term = `re-read_risk`, not
    raw size. A size-only "compact at 100k" rule helps on scanlib, hurts on speclib. Validates the
    working model below. **Product:** gate the "compact now" nudge on reclaimable-junk × remaining-runway.
  - **HARNESS FIX:** the `compact` arm used to `--resume` (reloads full context; no reclaim below the
    ~200k window → compact ≡ continue). Now a REAL reset (fresh session + summary) in `runner.py`. That
    fix produced the scanlib compact win. Headless `claude -p` has no `/compact`.
  - **COMMITTED + PUSHED:** branch `experiment/compaction-regime-map` (`a6ed8ae`: runner compact fix
    + both fixtures + ROI RESULTS + ROADMAP/baton) is on origin; PR not opened. Mock row id19 deleted.
    New fixtures `tasks/debug-speclib` (load-bearing) + `tasks/debug-scanlib` (disposable) are tracked.
  - **NEXT BUILD — the compaction gate (`docs/COMPACTION-GATE.md` spec; `GOALS/compaction-gate-phase1.md`
    brief):** turns the regime map into a proc-engine fix. CORRECTED root cause: `intervene.py` already
    routes re_read/repeated/huge → `offload` (safe); the real gap is the lone DROP path `context_rot →
    handoff`, which fires on a generic pressure signal carrying no disposability info. Phase 1 = make that
    drop safe-by-default; phases 2–3 = disposability + runway gates. Fixtures are the acceptance test
    (fire-drop on scanlib, suppress-drop on speclib). ROADMAP 6.8-pre. The roadblock to 6.8 L3.
  - **`GOALS/` created — loop-ready task briefs** (README + 3 briefs: compaction-gate-phase1,
    roi-cross-session-linkage, experiment-closeout). Each is self-contained for `/loop` or a Codex
    hand-off. Uncommitted with the 5B.1 draft.
  - **Closeout DONE:** real-reset compact on speclib (id25, $1.209, peak 104k) ≈ continue ($1.237) —
    confirms with the fixed compact arm that early reset doesn't pay on load-bearing (was resting on
    handoff +20% alone). Same real-compact wins −28% on disposable scanlib. Spend **$17.46/$20**.
    Open follow-up: (b) more reps for tighter magnitudes. Work is on PR **#18** (→ main, not merged).
- **5B.1 (Nick data-surface spec) — DRAFT, looping.** `docs/UI-INTEGRATION.md` now specs the full v1
  surface (summary + `session_detail.v1` timeline + export `--detail`/`--since`/`--redact`/`--codex` +
  `is_low_activity` + join + stability). Both prior open questions were already built; the doc catches up
  to code. Uncommitted — refine then commit. **Next in Claude's lane: 5B.2** = refresh the STALE
  `docs/HANDOFF-TO-NICK.md` (still lists the two questions as open) into the "here's what's ready" note.
- **Open research thread (Zach):** *when does compacting early have benefits?* Working model —
  early compaction pays iff `reclaimable_tokens × per-turn-carry-cost × turns_remaining >
  summary_cost + re-establish_cost + re-read_risk`. Three gates: reclaimable-junk (engine has it),
  pressure (engine has it), and **remaining runway = turns-to-*task-done*** (engine LACKS it —
  candidate proc-engine refinement so it won't nag "compact!" when one fix from done).
