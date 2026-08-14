#!/usr/bin/env python3
"""MR Token — advisory task-spend policy (spend-governance MVP core).

The forward-looking counterpart to pricing/measure. Given a TASK's token estimate, a
set of CANDIDATE models (each with an injected price row + a capability tier), and a
BUDGET POLICY, return an auditable governance decision: recommend the cheapest model
that meets the required capability, and gate it allow / escalate / deny against the
task budget — with human-readable reasons and a ranked table for the audit trail.

Deliberately provider-neutral and hermetic:
  * NO live provider API, NO network — inputs are injected structured dicts.
  * NO hardcoded rates — prices come from `candidates` (a caller MAY build them from
    prices.json via candidates_from_prices(), but nothing here bakes a rate in).
  * ADVISORY only — this returns a recommendation/verdict; it never blocks, routes, or
    enforces against a live agent. Enforcement, routing, and live pricing are NOT built.
  * Metadata only — token estimates + rates + tier ints; never prompt/task content.

The projection math mirrors ingest.est_cost (tokens ÷ 1e6 × per-million rate) so a
projected cost is comparable to a measured est_cost. Estimates are a TARGETING
heuristic only: never feed a projected cost into a measured-outcome number — same
discipline as measure Repair 3 (the estimator must not grade itself).
"""
from __future__ import annotations
import math
from typing import Iterable

from mrtoken.pricing import COST_CAVEAT

ALLOW = "allow"
ESCALATE = "escalate"
DENY = "deny"

_PER_M = 1_000_000.0
_PRICE_FIELDS = ("input", "output", "cache_read", "cache_write")


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_TASK_TOKEN_FIELDS = ("est_input_tokens", "est_output_tokens",
                      "est_cache_read_tokens", "est_cache_write_tokens")


def _bad_number(v) -> bool:
    """True if a SUPPLIED value is an unusable number: non-numeric, non-finite (nan/inf),
    or negative. None/absent is NOT bad — it defaults to 0 downstream. This is the
    numeric-safety predicate: a negative estimate makes projected cost negative and slips
    under a budget cap; a nan makes every '>' comparison False and also slips under."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return True
    return (not math.isfinite(f)) or f < 0


def _collect_invalid(task: dict, candidates: list, policy: dict) -> list:
    """Auditable list of the invalid numeric inputs (empty => all clear). Covers every
    numeric that feeds the cost projection or the budget gate: task token estimates +
    min_capability, each candidate's capability + price rates, and the policy thresholds."""
    bad = []
    for f in _TASK_TOKEN_FIELDS:
        if _bad_number(task.get(f)):
            bad.append(f"task.{f}={task.get(f)!r}")
    if _bad_number(task.get("min_capability")):
        bad.append(f"task.min_capability={task.get('min_capability')!r}")
    for i, c in enumerate(candidates):
        label = c.get("model") or f"candidate[{i}]"
        if _bad_number(c.get("capability")):
            bad.append(f"{label}.capability={c.get('capability')!r}")
        price = c.get("price") or {}
        for k in _PRICE_FIELDS:
            if _bad_number(price.get(k)):
                bad.append(f"{label}.price.{k}={price.get(k)!r}")
    for f in ("min_capability", "max_task_usd", "escalate_usd", "max_task_tokens"):
        if _bad_number(policy.get(f)):
            bad.append(f"policy.{f}={policy.get(f)!r}")
    return bad


def project_task_cost(price: dict, task: dict) -> float:
    """Projected USD for one model priced by `price` (a per-million rate row shaped like
    prices.json / ingest.price_for) running `task` (its estimated token demand). Pure
    math, mirrors ingest.est_cost. Missing rates or estimates contribute 0.

    Numeric-safety: raises ValueError on any negative or non-finite (nan/inf) rate or
    token estimate. A negative estimate would yield a NEGATIVE cost that slips under a
    budget cap and a nan would make every budget comparison False — both bypass the gate,
    so garbage numerics must fail loudly here rather than become a silently-wrong cost."""
    price = price or {}
    task = task or {}
    for k in _PRICE_FIELDS:
        if _bad_number(price.get(k)):
            raise ValueError(f"price.{k} must be finite and non-negative, got {price.get(k)!r}")
    for f in _TASK_TOKEN_FIELDS:
        if _bad_number(task.get(f)):
            raise ValueError(f"task.{f} must be finite and non-negative, got {task.get(f)!r}")
    return round(
        _int(task.get("est_input_tokens"))        / _PER_M * _float(price.get("input"))
        + _int(task.get("est_output_tokens"))      / _PER_M * _float(price.get("output"))
        + _int(task.get("est_cache_read_tokens"))  / _PER_M * _float(price.get("cache_read"))
        + _int(task.get("est_cache_write_tokens")) / _PER_M * _float(price.get("cache_write")),
        6,
    )


def evaluate_spend(task: dict, candidates: Iterable[dict], policy: dict) -> dict:
    """Advisory governance decision for running `task` under `policy`.

    task      : {"id"?, "est_input_tokens", "est_output_tokens",
                 "est_cache_read_tokens"?, "est_cache_write_tokens"?,
                 "min_capability"?}  — a forward estimate (provider-neutral).
    candidates: iterable of {"model", "capability" (int tier; higher = more capable),
                 "price": {input, output, cache_read?, cache_write?}}  — INJECTED prices.
    policy    : {"max_task_usd"?, "escalate_usd"?, "min_capability"?,
                 "max_task_tokens"?}  — the budget rule. max_task_tokens is an OPTIONAL
                 provider-neutral ceiling on the SUM of the task's estimated token fields
                 (_TASK_TOKEN_FIELDS); absent => no token gate, behaviour unchanged.

    Returns an auditable dict: decision (allow|escalate|deny), recommended_model,
    projected_cost_usd, reasons[], ranked[] (every candidate, cheapest-first, with
    eligibility), the echoed policy, advisory=True, and the cost caveat. Pure; no I/O.
    """
    policy = policy or {}
    task = task or {}
    cand_list = list(candidates or [])

    # Numeric-safety gate (fixes the negative/non-finite budget-bypass): reject invalid
    # numerics up front with an auditable DENY verdict rather than projecting a cost from
    # garbage — a negative estimate -> negative cost under the cap; a nan -> every '>'
    # comparison False -> also under the cap. Covers task estimates, candidate capability
    # + price rates, and the policy floor/thresholds (every numeric feeding the gate).
    invalid = _collect_invalid(task, cand_list, policy)
    if invalid:
        return {
            "decision": DENY, "recommended_model": None, "projected_cost_usd": None,
            "reasons": ["invalid input rejected (each numeric must be finite and "
                        f"non-negative): {', '.join(invalid)} -> deny."],
            "ranked": [],
            "policy": {"min_capability": policy.get("min_capability", task.get("min_capability")),
                       "max_task_usd": policy.get("max_task_usd"),
                       "escalate_usd": policy.get("escalate_usd")},
            "advisory": True, "caveat": COST_CAVEAT,
        }

    # Optional provider-neutral per-task TOKEN cap (max_task_tokens). Absent => this branch
    # is never entered and behaviour is byte-identical to before. Present => compare the SUM
    # of the same estimated token fields cost projection uses (_TASK_TOKEN_FIELDS) against
    # the cap; STRICTLY over-cap is its own auditable DENY, distinct from capability- and
    # $-budget denial. Invalid/non-finite/negative caps AND token estimates already failed
    # closed above through _collect_invalid/_bad_number, so this sum is a clean non-negative
    # integer and the comparison cannot be bypassed.
    max_tokens = policy.get("max_task_tokens")
    if max_tokens is not None:
        est_tokens = sum(_int(task.get(f)) for f in _TASK_TOKEN_FIELDS)
        if est_tokens > _float(max_tokens):
            return {
                "decision": DENY, "recommended_model": None, "projected_cost_usd": None,
                "reasons": [f"estimated {est_tokens} task tokens exceed the per-task token "
                            f"cap {max_tokens} -> deny (token ceiling, distinct from "
                            "capability and $-budget denial)."],
                "ranked": [],
                "policy": {"min_capability": policy.get("min_capability",
                                                        task.get("min_capability")),
                           "max_task_usd": policy.get("max_task_usd"),
                           "escalate_usd": policy.get("escalate_usd"),
                           "max_task_tokens": max_tokens},
                "advisory": True, "caveat": COST_CAVEAT,
            }

    min_cap = _int(policy.get("min_capability", task.get("min_capability", 0)))
    max_usd = _float(policy["max_task_usd"]) if policy.get("max_task_usd") is not None else None
    esc_usd = _float(policy["escalate_usd"]) if policy.get("escalate_usd") is not None else None

    ranked = []
    for c in cand_list:
        cap = _int(c.get("capability", 0))
        cost = project_task_cost(c.get("price") or {}, task)
        ranked.append({"model": c.get("model"), "capability": cap,
                       "projected_cost_usd": cost, "eligible": cap >= min_cap})
    # cheapest first; on a cost tie prefer the MORE capable model (stable, auditable)
    ranked.sort(key=lambda r: (r["projected_cost_usd"], -r["capability"]))

    reasons: list[str] = []
    result = {
        "decision": DENY, "recommended_model": None, "projected_cost_usd": None,
        "reasons": reasons, "ranked": ranked,
        "policy": {"min_capability": min_cap, "max_task_usd": max_usd, "escalate_usd": esc_usd},
        "advisory": True, "caveat": COST_CAVEAT,
    }

    if not ranked:
        reasons.append("no candidate models supplied — nothing to recommend.")
        return result

    eligible = [r for r in ranked if r["eligible"]]
    if not eligible:
        best_cap = max(r["capability"] for r in ranked)
        reasons.append(f"no candidate meets required capability >={min_cap} "
                       f"(best available tier is {best_cap}) -> deny.")
        return result

    pick = eligible[0]                       # cheapest that meets the capability floor
    cost = pick["projected_cost_usd"]
    result["recommended_model"] = pick["model"]
    result["projected_cost_usd"] = cost
    reasons.append(f"cheapest model meeting capability >={min_cap} is '{pick['model']}' "
                   f"(tier {pick['capability']}) at ~${cost:.6f}.")

    # surface a cheaper-but-ineligible option (the downgrade-guidance signal)
    cheaper_blocked = next((r for r in ranked
                            if not r["eligible"] and r["projected_cost_usd"] < cost), None)
    if cheaper_blocked:
        reasons.append(
            f"a cheaper option '{cheaper_blocked['model']}' "
            f"(~${cheaper_blocked['projected_cost_usd']:.6f}) was excluded: capability tier "
            f"{cheaper_blocked['capability']} < {min_cap}.")

    if max_usd is not None and cost > max_usd:
        reasons.append(f"projected ~${cost:.6f} exceeds the per-task budget ${max_usd:.6f} "
                       "-> deny (no capable model fits the cap).")
        return result                        # decision stays DENY
    if esc_usd is not None and cost > esc_usd:
        result["decision"] = ESCALATE
        tail = f" (<= budget ${max_usd:.6f})" if max_usd is not None else ""
        reasons.append(f"projected ~${cost:.6f} exceeds the escalate threshold "
                       f"${esc_usd:.6f}{tail} -> escalate for human sign-off.")
        return result

    result["decision"] = ALLOW
    if esc_usd is not None:
        tail = f" (<= escalate ${esc_usd:.6f})"
    elif max_usd is not None:
        tail = f" (<= budget ${max_usd:.6f})"
    else:
        tail = " (no budget set)"
    reasons.append(f"projected ~${cost:.6f}{tail} -> allow.")
    return result


def candidates_from_prices(prices: dict, specs: Iterable[tuple], at=None) -> list[dict]:
    """Build candidate dicts from a LOADED prices table (injected — not fetched) and a
    caller-supplied list of (model_id, capability_tier). Reuses ingest.price_for so rate
    resolution (incl. effective/intro windows) matches the measured side. Provider-neutral:
    the caller chooses which models and how to rank capability; nothing is hardcoded here."""
    from mrtoken.ingest import price_for
    out = []
    for model, cap in specs:
        row = price_for(prices, model, at)
        out.append({"model": model, "capability": _int(cap),
                    "price": {k: row.get(k) for k in _PRICE_FIELDS}})
    return out
