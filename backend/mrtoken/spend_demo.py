#!/usr/bin/env python3
"""MR Token — spend-governance dry-run harness (customer-use-case vertical proof).

The smallest provider-neutral, runnable demonstration of the CTO/CFO control on top of
spendpolicy.evaluate_spend: define a per-task budget + capability floor, hand it the
candidate models with INJECTED prices, and get back a recommended lower-cost suitable
model plus an auditable allow / escalate / deny record with reasons.

Deterministic and hermetic:
  * Every input is injected — task, capability tiers, candidate models, prices. The
    bundled examples use FAKE vendor names + prices so the demo cannot accidentally
    depend on prices.json or a real model roster.
  * NO provider call, NO network, NO live DB, NO config/hook/allowlist read.
  * Byte-stable output — no timestamps, no randomness — so a render is reproducible and
    diffable (an audit record, not a log line).

`python -m mrtoken.spend_demo` prints the audit records for the bundled example set; the
same functions are unit-tested. This DEMONSTRATES the evaluator — it does not enforce,
route, or block a live agent. Enforcement/routing/live-pricing are NOT built.
"""
from __future__ import annotations
from typing import Iterable

from mrtoken.spendpolicy import evaluate_spend

# Provider-neutral fake roster: capability is an ordinal tier the operator assigns
# (higher = more capable); prices are injected per-million rates, not from any table.
_DEMO_CANDIDATES = [
    {"model": "vendor-nano", "capability": 1, "price": {"input": 0.5,  "output": 1.5}},
    {"model": "vendor-mini", "capability": 2, "price": {"input": 3.0,  "output": 15.0}},
    {"model": "vendor-max",  "capability": 3, "price": {"input": 10.0, "output": 50.0}},
]

# Three bundled scenarios chosen to exercise every verdict: allow (cheap task, low floor),
# escalate (premium floor forces the pricey model, over the escalate line but within
# budget), deny (task so large the cheapest suitable model still blows the budget cap).
DEMO_SCENARIOS = [
    {
        "name": "cheap-task-allow",
        "task": {"id": "summarize-ticket", "est_input_tokens": 20_000,
                 "est_output_tokens": 2_000, "min_capability": 1},
        "candidates": _DEMO_CANDIDATES,
        "policy": {"min_capability": 1, "escalate_usd": 0.50, "max_task_usd": 2.00},
    },
    {
        "name": "premium-required-escalate",
        "task": {"id": "migrate-service", "est_input_tokens": 300_000,
                 "est_output_tokens": 60_000, "min_capability": 3},
        "candidates": _DEMO_CANDIDATES,
        "policy": {"min_capability": 3, "escalate_usd": 3.00, "max_task_usd": 20.00},
    },
    {
        "name": "over-budget-deny",
        "task": {"id": "whole-repo-audit", "est_input_tokens": 5_000_000,
                 "est_output_tokens": 500_000, "min_capability": 2},
        "candidates": _DEMO_CANDIDATES,
        "policy": {"min_capability": 2, "escalate_usd": 5.00, "max_task_usd": 10.00},
    },
]


def run_scenario(scenario: dict) -> dict:
    """Deterministic dry-run of ONE scenario: bind its injected task/candidates/policy,
    evaluate, and return the evaluator's auditable record enriched with the scenario name
    and task id. Pure — delegates to spendpolicy.evaluate_spend; no I/O."""
    scenario = scenario or {}
    result = evaluate_spend(scenario.get("task") or {},
                            scenario.get("candidates") or [],
                            scenario.get("policy") or {})
    return {"name": scenario.get("name"),
            "task_id": (scenario.get("task") or {}).get("id"), **result}


def run_all(scenarios: Iterable[dict] | None = None) -> list:
    """Dry-run every scenario (bundled DEMO_SCENARIOS by default), in deterministic order."""
    return [run_scenario(s) for s in (DEMO_SCENARIOS if scenarios is None else scenarios)]


_DECISION_MARK = {"allow": "ALLOW", "escalate": "ESCALATE", "deny": "DENY"}


def _usd(v) -> str:
    return "-" if v is None else f"${float(v):.6f}"


def render_decision(row: dict) -> str:
    """One auditable, deterministic text record for a dry-run row — the CFO/CTO-readable
    audit line: verdict, recommended model + projected cost, the ranked candidate table,
    every reason, and the cost caveat. No timestamps/randomness, so it is byte-stable."""
    policy = row.get("policy") or {}
    lines = [
        f"-- spend-policy dry-run: {row.get('name')} (task {row.get('task_id')!r}) --",
        f"  decision:   {_DECISION_MARK.get(row.get('decision'), row.get('decision'))}",
        f"  recommend:  {row.get('recommended_model') or '(none eligible)'}"
        f"  proj {_usd(row.get('projected_cost_usd'))}",
        f"  policy:     min_cap>={policy.get('min_capability')}  "
        f"escalate<={_usd(policy.get('escalate_usd'))}  budget<={_usd(policy.get('max_task_usd'))}",
        "  candidates (cheapest first):",
    ]
    for r in row.get("ranked") or []:
        elig = "eligible" if r.get("eligible") else "excluded"
        lines.append(f"    - {r.get('model')}  tier {r.get('capability')}  "
                     f"{_usd(r.get('projected_cost_usd'))}  [{elig}]")
    if not (row.get("ranked") or []):
        lines.append("    (none)")
    lines.append("  reasons:")
    for why in row.get("reasons") or []:
        lines.append(f"    * {why}")
    lines.append(f"  note: {row.get('caveat')} (advisory — not enforced against a live agent)")
    return "\n".join(lines)


def demo(scenarios: Iterable[dict] | None = None) -> str:
    """Full rendered demo (all bundled scenarios by default) as one deterministic string."""
    return "\n\n".join(render_decision(r) for r in run_all(scenarios))


if __name__ == "__main__":   # runnable dry-run entry surface: `python -m mrtoken.spend_demo`
    print(demo())
