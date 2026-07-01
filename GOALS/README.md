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
| Compaction gate — phase 1 (gate the DROP path) | `compaction-gate-phase1.md` | Codex / either | **ready** | `context_rot` no longer leads with a destructive `handoff` w/o a disposability signal; `./scripts/test-backend.sh` green incl. new regime tests |
| Real in-the-wild ROI (cross-session linkage) | `roi-cross-session-linkage.md` | Codex / either | **ready** | `roi --measure` emits a non-degenerate acted-vs-ignored number (method B no longer all-"ignored") |
| Experiment closeout (speclib fixed-compact + reps) | `experiment-closeout.md` | Claude | **ready** (needs ~$3 of the $20) | speclib fixed-compact n≥2 recorded; `ROI-EXPERIMENT.md` RESULTS updated |
| 5B.2 — refresh the Nick note | `5b2-nick-note.md` | Claude draft, **Zach sends** | **ready** | `docs/HANDOFF-TO-NICK.md` matches the shipped v1 surface; two questions marked answered |
| K2 pane icon = Mr Token logo | _(brief TBD)_ | Claude | **BLOCKED** | no logo asset exists in-repo; source/create the logo, learn how K2 sets a pane icon, then wire it |

## Onboarding a new agent (e.g. Fable)
See **`ONBOARDING.md`** at the repo root — start-here + the trio's roles + **K2 collision-avoidance
for running Fable in a parallel pane on this workspace**. Dispatch a `ready` brief above to Fable the
same way as Codex (own branch/worktree, review, merge).

## Related
- `ROADMAP.md` — the master plan (these briefs are executable slices of it)
- `ORCHESTRATION.md` — the failover baton (current state + spend)
- `backend/docs/COMPACTION-GATE.md`, `backend/docs/ROI-EXPERIMENT.md` — the specs behind two briefs
