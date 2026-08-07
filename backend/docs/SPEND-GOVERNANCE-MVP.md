# Spend governance — MVP slice 1 (advisory task-spend policy)

**Status:** first bounded execution slice. Adds `backend/mrtoken/spendpolicy.py` (pure,
provider-neutral, advisory) + 6 tests. **No enforcement, no routing, no live pricing, no
hook/CLI/MCP wiring** — those are explicitly out of scope and NOT built. Read the matrix
below before claiming any capability.

## 1. Capability matrix (repo evidence, 2026-08-07)

Grounded in the code on `experiment/compaction-regime-map` @ `d7bee35`. Honest labels:
CURRENT = shipped and tested; PARTIAL = pieces exist, the CFO-facing capability does not;
ABSENT = not built (do **not** imply it exists).

| Capability target (from Caleb/Dave/Nick thread) | Status | Repo evidence |
|---|---|---|
| Measure real tokens/cost per session | **CURRENT** | `ingest.est_cost`, `measure.measured_task_tokens`, `session_summary` view |
| Model **pricing metadata** + coverage/freshness guardrails | **CURRENT** | `prices.json`, `pricing.uncovered_models`/`freshness_warning` |
| Post-hoc cost attribution + ROI | **CURRENT** | `roi.py`, `savings.py` (Repair-1 attribution), `report.py`, `why.py` |
| Per-**tool** autonomy policy + global kill switch | **CURRENT** | `policy.autonomy` (off/tell/ask/do), `MRTOKEN_INTERVENE` |
| Context-pressure nudge engine | **CURRENT** | `intervene.evaluate/decide`, `autoact` (freemium, default-off) |
| Cohort gating of automatic surfaces | **CURRENT** | `cohort.in_cohort` (Stage 1, `27c01aa`) — inert until an allowlist is set |
| **Model selection by task** | **PARTIAL → this slice** | prices let you *compare* models; no evaluator recommended one until `spendpolicy.evaluate_spend` |
| **Cheaper-model recommendation** | **PARTIAL → this slice** | `why.py` shows where cost *went*; forward "use the cheaper capable model" added here |
| **Task-level budget** | **PARTIAL → this slice** | cost measured per session/trace; no per-task *budget policy* object until this slice (advisory) |
| **Guardrails against runaway spend** | **PARTIAL** | `policy` kill switch + `intervene` gate *context*, not spend; this slice adds an advisory spend verdict, **not** a live block |
| Codex/GPT spend visibility | **PARTIAL** | `ingest_codex.py` + gpt rows in `prices.json`; some views still show Codex at 0.00M |
| **Enforcement** against a live agent (hard stop / block a call) | **ABSENT** | evaluator is advisory; nothing blocks or routes a live call |
| Live provider API / real-time price feeds | **ABSENT** | `prices.json` is hand-maintained metadata (`pricing.py` docstring) |
| Real billing / entitlement | **ABSENT** | `autoact.entitled_paid` is a stub; "real billing is a separate later project" |
| CFO/CTO reporting console / dashboard | **ABSENT** | only local `web/` UI + CLI reports exist |
| Cross-provider normalized capability tiers | **ABSENT** | capability is an injected int here; not modeled in-repo |

## 2. MVP contract + discovery questions

### MVP contract — Advisory Task-Spend Policy (ATSP) v0
- **In:** a task's forward token estimate; candidate models (each with an **injected**
  price row + a capability tier); a budget policy (per-task cap, escalate threshold,
  min capability).
- **Out:** an auditable decision — **recommend the cheapest model meeting the capability
  floor**, and gate it **allow / escalate / deny** against the budget — with
  human-readable `reasons[]` and a cheapest-first `ranked[]` audit table.
- **Guarantees:** pure & provider-neutral (no live API, no hardcoded rates); **advisory**
  (never blocks/routes a live agent); metadata-only (estimates + rates + tiers, never task
  content); projection uses the same per-million math as `ingest.est_cost`.
- **Non-goals (v0, on purpose):** enforcement, routing, live pricing, dashboard, real
  billing. Do not describe ATSP v0 as any of these.

### Five customer-discovery questions (for the target CFO/CTO users)
1. **Granularity:** which budget do you'd actually set a *hard cap* on — per task, per
   agent/session, per project, or per team/month?
2. **Over-budget action:** when a task's projected cost exceeds budget, what should happen —
   block, require a named human approver, auto-downgrade to a cheaper model, or log + alert?
3. **Capability rule:** how do you decide a task needs a premium model today — a written
   rule, or tribal judgment? (This defines "min capability.")
4. **Blind spots:** whose spend is invisible to you now (Codex/GPT, local agents, CI), and
   what dollar figure are you most afraid of not seeing?
5. **The board number:** the one report you'd put in front of your CFO/board — cost per
   completed task, spend-vs-budget by team, or savings from model downgrades — and how often?

## 3. The code slice (deliverable 3)
`backend/mrtoken/spendpolicy.py`:
- `project_task_cost(price, task) -> float` — pure per-million projection, mirrors `est_cost`.
- `evaluate_spend(task, candidates, policy) -> dict` — the auditable
  `allow`/`escalate`/`deny` + recommendation with `reasons[]`/`ranked[]`.
- `candidates_from_prices(prices, specs, at=None)` — optional bridge that reuses
  `ingest.price_for` over an **injected** table (no hardcoded rate, no fetch).

Decision order: no candidates → deny; none meets capability → deny (distinct reason);
else recommend the cheapest capable model, then cost > `max_task_usd` → deny, cost >
`escalate_usd` → escalate, else allow. Every branch appends a reason.

Tests (deliverable 4), in `backend/tests/test_backend.py`: `test_spendpolicy_*` (6) — allow/
recommend-cheapest, escalate-between-thresholds, deny-over-budget, deny-no-capability
(distinct from budget denial), provider-neutral + downgrade note, injected-price bridge.
Plus the full existing suite.

## 4. Stage-3 non-contamination (deliverable 5)
The evaluator **cannot** contaminate the Stage-3 measured-benefit experiment
(`STAGE3-VALIDATION-PROTOCOL.md`):
- **Zero runtime footprint.** It is a pure function: no DB write, no hook, no nudge, no
  transcript touch. Importing or testing it does not engage the cohort gate, the proc
  engine, or any store — so it appears in neither the ON nor the OFF arm's behavior.
- **Zero token footprint.** No provider call, no live pricing read → it adds no tokens to
  any session, so it cannot move the measured-token outcome in either arm.
- **Not wired.** This slice does not register it in `intervene`/`autoact`/hooks (out of
  scope). Stage-3's ON arm therefore behaves exactly as `d7bee35` defines; the evaluator
  is dark.
- **Estimator discipline.** Its projected cost is an *estimate* and must never feed the
  Stage-3 outcome — that stays `measure.measured_task_tokens` (actuals), same rule as
  Repair 3 (the estimator must not grade itself). ATSP output belongs to the
  *addressable/diagnostic* side only.
- **Future wiring is already covered.** If spend-governance is later wired to nudge (gated),
  it becomes a new `tool` under `policy.autonomy` (default `tell`, cohort-gated); Stage-3's
  ON-arm nudge surface + OFF-arm `mr-*` prohibition already cover it. A new run would only
  add one pre-registered arm variable ("spend-nudge on/off") — no protocol rewrite.
