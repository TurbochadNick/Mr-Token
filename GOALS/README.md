# GOALS — loop-ready task briefs

Each file here is a **self-contained mission** an agent can execute to a defined exit
condition **without back-and-forth** — so Zach can point `/loop` (or a fresh session, or
Codex) at one and walk away. If a brief needs a decision only Zach can make, that decision
is called out up front so the loop stops and asks instead of guessing.

## How to dispatch a loop

- **Self-paced loop:** `/loop — execute GOALS/<slug>.md to its "Loop exit" criteria, then stop.`
- **Codex hand-off:** give Codex the file path; it runs on a branch and commits (git is the bus).
- **Fresh session:** paste the file as the opening prompt.

## Every brief inherits (don't restate, do obey)

- `~/.claude/CLAUDE.md` safety rules: **DB writes need explicit confirmation**; big/irreversible/
  outward-facing actions confirm first; state the **root cause before editing**; **"done" = the
  command was run and its output is shown**; no weakening tests / no mocks-to-pass / no silent
  fallbacks; touch only what the task needs.
- Repo guide `CLAUDE.md`: TS = `pnpm build` / `pnpm test`; Python = `pip install -e backend/`,
  tests via `./scripts/test-backend.sh`. Privacy invariant: metadata only.
- Experiments **spend real money** — respect the `$20` cap (see `ORCHESTRATION.md` for spend).

## Index

| Goal | File | Lane | Status | Loop exit (1-line) |
|---|---|---|---|---|
| Compaction gate — phase 1 (gate the DROP path) | `compaction-gate-phase1.md` | Codex / either | **done** (Fable, commit 0d92e55) | met, except full-green blocked by a PRE-EXISTING drift: `test_experiment_runner_groundwork` asserts the 100k threshold 89325c4 changed to 30k — needs Zach's call |
| Real in-the-wild ROI (cross-session linkage) | `roi-cross-session-linkage.md` | Codex / either | **done** (Fable) | met: on the live 76-session corpus B = acted n=3 / ignored n=12 (was 0/20); C headline unchanged; doc updated |
| Compaction gate — phase 2 (disposability gate) | `compaction-gate-phase2.md` | Codex / Fable | **done** (Fable) | met: `evaluate(disposability=)` gates the drop; LiveMonitor classifies per-read-target recency (K=5, hash-only); 88 tests green. No replay plumbing exists yet — regimes covered by synthetic unit tests, golden fixtures still open for 5D.3 |
| Compaction gate — phase 3 (remaining-runway gate) | `compaction-gate-phase3.md` | Codex / Fable | **done** (Fable) | met: near-done (errors→green + writes landing, positive evidence on every axis) suppresses the nudge; drop = disposable ∧ ¬near-done; default-None = phase-2; 90 tests green. On the phase-2 branch (phase 3 builds on it) — one PR reviews both. **Gate complete → 6.8 L3 unblocked.** |
| Experiment closeout (speclib fixed-compact + reps) | `experiment-closeout.md` | Claude | **done** | real-compact on speclib (id25) $1.209 ≈ continue — confirms reset loses on load-bearing with the fixed arm; RESULTS + baton updated; spend $17.46/$20 |
| 5B.2 — refresh the Nick note | `5b2-nick-note.md` | Claude draft, **Zach sends** | **done (draft)** | `docs/HANDOFF-TO-NICK.md` rewritten to the v1 surface (session_detail + --since/--detail/--redact/--codex + is_low_activity), both questions marked answered, points to UI-INTEGRATION.md. ⏳ Zach forwards to Nick. |
| Explicit disposability channel (`disposable_confirmed`) | `disposable-confirmed-channel.md` | **Claude** (kept in-house — not worth scarce Fable time) | **done** (PR #20) | `confirm_disposable` MCP tool records a session-scoped, metadata-only confirmation (call-index + ts); `intervention_for_session` merges a FRESH one as `disposable_confirmed` → escalation unlocked; stale by CONFIRM_TTL_CALLS(10)/MIN(30) → back to proxy tell-only; skill doc + 92 tests green. **The explicit path to 6.8 L3 now exists end-to-end.** ⚠ Fable review (2026-07-03) found a cross-session misdirect at the MCP boundary → fix brief below. |
| Bind `confirm_disposable` to the calling session | `confirm-disposable-session-binding.md` | Codex / Claude / Fable | **done** (Codex) | met: ambiguous no-arg calls fail closed; explicit `session` and single-session no-arg still work; 94 backend tests green |
| 6.8 L3 `do` contract | `6.8-l3-do-contract.md` | Zach-gated, then Codex / Claude | **implemented, inert** | structure built for `handoff` only: do+escalate+explicit confirmation generates handoff text; defaults stay warn-only; live enablement + real billing remain future decisions |
| K2 pane icon = Mr Token logo | _(brief TBD)_ | Claude | **BLOCKED** | no logo asset exists in-repo; source/create the logo, learn how K2 sets a pane icon, then wire it |

## Onboarding a new agent (e.g. Fable)
See **`ONBOARDING.md`** at the repo root — start-here + the trio's roles + **K2 collision-avoidance
for running Fable in a parallel pane on this workspace**. Dispatch a `ready` brief above to Fable the
same way as Codex (own branch/worktree, review, merge).

## Related
- `ROADMAP.md` — the master plan (these briefs are executable slices of it)
- `ORCHESTRATION.md` — the failover baton (current state + spend)
- `backend/docs/COMPACTION-GATE.md`, `backend/docs/ROI-EXPERIMENT.md` — the specs behind two briefs
