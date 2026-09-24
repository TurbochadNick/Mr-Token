"""One advisory Savings Decision Card for status and why.

This is deliberately a pure/read-only presentation layer: rules provide the
measured signal, an optional caller supplies routing inputs, and the card never
routes, records savings, or changes policy.
"""
from __future__ import annotations

import json


_ACTIONS = (
    ("fresh_handoff", "handoff", "handoff/compact experiment candidate",
     "Compare continue, compact, and handoff at equal completion before calling it a saving."),
    ("huge_tool_output", "offload", "prevent next bulky output",
     "Preserve the task oracle while comparing targeted output with the full-output baseline."),
    ("retry_loop", "savings", "stop and re-plan",
     "Use a bounded retry baseline and require equal completion before claiming less spend."),
)
_ROUTING_FIELDS = ("baseline", "candidate", "capability_floor", "budget", "oracle")


def _details(raw) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _suppression(rule: str | None, tool: str | None) -> str | None:
    if not tool:
        return None
    return f"mrtoken-transcript config --intervene {tool}=off"


def _card(action: str, rule: str | None, tool: str | None, evidence: dict,
          quality_gate: str, measured: str, estimated: str) -> dict:
    return {
        "action": action,
        "rule": rule,
        "evidence": evidence,
        "quality_gate": quality_gate,
        "provenance": {"measured": measured, "estimated": estimated},
        "suppression": _suppression(rule, tool),
        "not_now": "Ignore this advisory for this run; no state is changed.",
        "advisory": True,
    }


def build_savings_card(recommendations, *, routing: dict | None = None,
                       suppressed=()) -> dict:
    """Choose one advisory card from rule records plus explicit routing inputs.

    ``suppressed`` contains rule or policy-tool names whose card must not surface.
    Routing is eligible only when every required field is supplied by the caller.
    """
    blocked = set(suppressed or ())
    by_rule = {r.get("rule"): r for r in (recommendations or [])}
    for rule, tool, action, gate in _ACTIONS:
        rec = by_rule.get(rule)
        if rec and rule not in blocked and tool not in blocked:
            return _card(
                action, rule, tool,
                {"rule": rule, "message": rec.get("message", ""),
                 "details": _details(rec.get("evidence_json"))},
                gate,
                "Current-session rule evidence is measured metadata.",
                "Any addressable-token or cost projection is estimated, not realized savings.",
            )
    if routing and "routing" not in blocked and "savings" not in blocked and all(
            routing.get(k) not in (None, "") for k in _ROUTING_FIELDS):
        return _card(
            "routing experiment candidate", None, "savings",
            {"routing_inputs": {k: routing[k] for k in _ROUTING_FIELDS}},
            "Run the supplied baseline and candidate against the supplied oracle at the capability floor and budget.",
            "No current-session routing measurement was inferred.",
            "Candidate cost is projected; routing is advisory and no provider is switched.",
        )
    return _card(
        "continue", None, None,
        {"reason": "no supported, unsuppressed decision signal"},
        "Keep the completion oracle; do not call a lower cost a saving without a matched comparison.",
        "No supported measured action signal fired.",
        "No projected savings are realized savings.",
    )


def card_for_session(conn, tid: int, *, routing: dict | None = None) -> dict:
    """Read existing metadata and current suppression policy; never writes either."""
    from mrtoken.rules import advice_on  # rule-derived card content is switched off
    rows = [] if not advice_on() else conn.execute(
        "SELECT rule, severity, message, evidence_json FROM recommendation WHERE trace_id=?", (tid,)
    ).fetchall()
    recommendations = [
        {"rule": r[0], "severity": r[1], "message": r[2], "evidence_json": r[3]}
        for r in rows
    ]
    from mrtoken.policy import autonomy
    suppressed = {tool for _, tool, _, _ in _ACTIONS + (("routing", "savings", "", ""),)
                  if autonomy(tool) == "off"}
    return build_savings_card(recommendations, routing=routing, suppressed=suppressed)


def render_savings_card(card: dict, *, indent: str = "  ") -> list[str]:
    """Stable terminal rendering shared by status and why."""
    rule = f"[{card['rule']}] " if card.get("rule") else ""
    lines = [f"{indent}next: {rule}{card['action']} (advisory; no auto-action)"]
    evidence = card["evidence"]
    if evidence.get("message"):
        lines.append(f"{indent}evidence: {evidence['message']}")
    else:
        lines.append(f"{indent}evidence: {evidence.get('reason', 'supplied routing inputs')}")
    lines.append(f"{indent}quality gate: {card['quality_gate']}")
    lines.append(f"{indent}provenance: measured — {card['provenance']['measured']}")
    lines.append(f"{indent}provenance: estimated — {card['provenance']['estimated']}")
    if card.get("not_now"):
        lines.append(f"{indent}not now: {card['not_now']}")
    if card.get("suppression"):
        lines.append(f"{indent}never suggest this: {card['suppression']}")
    return lines
