# Spend governance — dry-run vertical proof (customer-use-case slice)

**Status:** held for independent review. Adds `backend/mrtoken/spend_demo.py` (pure,
deterministic dry-run harness over the committed `spendpolicy.evaluate_spend`, `bb81b0e`)
+ 4 targeted tests. **No provider call, no live DB, no hook/config/allowlist, no push.**
Does not depend on the unreviewed Stage-3 artifact (the harness imports only
`spendpolicy`; verify with `grep -n import backend/mrtoken/spend_demo.py`).

## The user path this proves
A CTO/CFO persona: *"cap what one task may spend, compare the models that can do it,
recommend the cheapest suitable one, and give me an auditable allow / escalate / deny
with reasons."* Runnable: `python -m mrtoken.spend_demo` (or `run_all()` / `run_scenario()`
/ `render_decision()` from tests). Every input is injected — task, capability tiers,
candidate models, per-million prices — using fake vendor names so nothing leaks in from a
real roster or `prices.json`.

Bundled scenarios exercise all three verdicts (actual demo output):
| Scenario | Floor | Recommended | Projected | Verdict | Why |
|---|---|---|---|---|---|
| `cheap-task-allow` | tier ≥1 | `vendor-nano` | $0.013000 | **ALLOW** | cheapest eligible, ≤ escalate $0.50 |
| `premium-required-escalate` | tier ≥3 | `vendor-max` | $6.000000 | **ESCALATE** | floor excludes cheaper models; > escalate $3, ≤ budget $20 |
| `over-budget-deny` | tier ≥2 | `vendor-mini` | $22.500000 | **DENY** | cheapest suitable still > budget cap $10 |

Each record carries: the verdict, the recommended model + projected cost, the full
cheapest-first ranked candidate table with per-model eligibility, every reason string, and
the cost caveat. Output is byte-stable (no timestamp/randomness) — an audit record, not a
log line.

## Gap table — the demonstrated user path (implemented / partial / absent)

Honest against what the code on this branch actually does. Do not imply beyond this.

| Capability in the target need | Status | Evidence / note |
|---|---|---|
| Cap per-task **spend** (USD) → allow/escalate/deny | **IMPLEMENTED** | `evaluate_spend` `max_task_usd`/`escalate_usd`; demo `over-budget-deny`, `…-escalate` |
| Cap per-task **tokens** (direct token ceiling) | **PARTIAL** | governed *indirectly* — est tokens × injected rate = projected cost, capped in USD; there is no first-class `max_task_tokens` policy field yet |
| Compare eligible models for a task | **IMPLEMENTED** | capability-floor filter + cheapest-first `ranked[]` with per-model eligibility |
| Recommend a lower-cost suitable model | **IMPLEMENTED** | cheapest model meeting the floor; demo `cheap-task-allow` picks `vendor-nano` over pricier capable ones |
| Auditable allow/escalate/deny **reasons** | **IMPLEMENTED** | distinct reasons for capability- vs budget-denial; ranked table; `render_decision` audit record |
| Deterministic **dry-run entry surface** | **IMPLEMENTED** | `python -m mrtoken.spend_demo`, byte-stable output |
| Numeric-safety (reject negative/non-finite) | **IMPLEMENTED** | `_collect_invalid` / `project_task_cost` raise; regression tests |
| Provider neutrality | **IMPLEMENTED** | injected prices/models; demo uses fake vendors, no `prices.json` dependence |
| **Enforce** the verdict against a live agent (block/route) | **ABSENT** | advisory only — returns a record; nothing blocks or routes a real call |
| Persist / log decisions for an audit trail over time | **ABSENT** | record is returned, not stored; no decision store |
| Session-/project-/team-level budget aggregation | **ABSENT** | one task at a time; no rollup across tasks/sessions |
| Live or streaming prices | **ABSENT** | prices are injected static rates (hand-maintained metadata elsewhere) |
| Real capability benchmarking of models | **ABSENT** | `capability` is an operator-assigned ordinal tier, not measured |
| CFO/CTO console / UI for this control | **ABSENT** | CLI/programmatic dry-run only |

## Why Stage-3 is not folded in
The target need is a *forward* advisory control; Stage-3 is a *backward* measured-benefit
experiment on the automatic surfaces. The harness needs neither `measure` nor any Stage-3
symbol — it imports only `spendpolicy` (itself pure but for a lazy `ingest.price_for` in an
unused bridge). Folding Stage-3 in was considered and rejected as not required for this
vertical proof; the unreviewed `STAGE3-VALIDATION-PROTOCOL.md` stays out of this slice.
