#!/usr/bin/env python3
"""MR Token — L3 auto-act executor (ROADMAP 6.8), freemium + default-off.

The proc engine's `do`-level seam. When policy puts a tool at `do` AND the full
6.8-pre safety contract is satisfied, this may EXECUTE the remediation instead of
only nudging. v1 wires exactly one tool — `handoff` — and only the mildest action:
deterministically GENERATE the handoff text (no new session, no /compact, no
deletion, no network). Every other tool stays advisory.

Monetization (Zach's decision, 2026-07-06 — GOALS/6.8-l3-do-contract.md): auto-act
is a paid/freemium feature.
  • 3 free auto-acts, LIFETIME per install (a metadata-only counter in central state).
  • After the free uses: degrade to a manual prompt (the escalate nudge already tells
    the user how to run it) + an upsell line. Never hard-block, never break the flow.
  • Free uses double as the 6.7 evidence base — an executed handoff still writes
    ask-state, so the next turn's measure-don't-degrade pass records did-it-help.
  • "Paid" = a stubbed entitlement flag (MRTOKEN_LICENSE env / config `entitlement.paid`).
    Real billing (Stripe / license server) is a separate, later project.

Nothing here fires by default: a tool only reaches `do` if explicitly configured, and
the whole path sits ON TOP of the 6.8-pre gates enforced upstream in intervene.decide()
(explicit disposable_confirmed + runway-remains + AFK escalation; proxy-disposable is
capped at tell before it ever gets here; a negative 6.7 trend auto-disables the tool).
Privacy invariant: the meter stores counts + timestamps only, never content.
"""
from __future__ import annotations
import json, os

FREE_USES = 3
AUTO_ACT_TOOLS = {"handoff"}   # the only tool wired to EXECUTE in v1; all others advisory

_PENDING = "  [auto-action pending — ROADMAP 6.8]"
_UPSELL = (
    "  [Auto-handoff is a paid feature and your 3 free runs are used up — it's still "
    "one manual `handoff` away above. To keep hands-free auto-handoff, add a license "
    "(MRTOKEN_LICENSE); to silence this, set `handoff=ask`.]")


def _meter_path() -> str:
    from mrtoken.datadir import central_default
    return os.path.join(central_default(), "state", "autoact-meter.json")


def _read_meter() -> dict:
    try:
        with open(_meter_path()) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def free_uses_left() -> int:
    return max(0, FREE_USES - int(_read_meter().get("used", 0)))


def _spend_free_use(session_id: str, tool: str) -> None:
    from mrtoken.ingest import now_iso
    m = _read_meter()
    m["used"] = int(m.get("used", 0)) + 1
    m["last_tool"], m["last_session"], m["last_ts"] = tool, session_id, now_iso()
    p = _meter_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump(m, fh)
    except OSError:
        pass


def entitled_paid() -> bool:
    """Stubbed paid entitlement. Real billing is a separate later project — for now a
    license key via env, or config `{"entitlement": {"paid": true}}`, flips it on."""
    if os.environ.get("MRTOKEN_LICENSE", "").strip():
        return True
    from mrtoken.policy import _load
    return bool(_load().get("entitlement", {}).get("paid", False))


def access() -> tuple[bool, str]:
    """(may_auto_act, reason): paid → always; else trial while free uses remain; else spent."""
    if entitled_paid():
        return True, "paid"
    if free_uses_left() > 0:
        return True, "trial"
    return False, "spent"


def maybe_auto_act(session_id: str, iv: dict) -> dict:
    """The `do`-level executor gate. Returns iv (mutated). Only `handoff` at
    do+escalate+explicit-disposability may EXECUTE; everything else is advisory.

    Called from intervene.decide() after apply_ask_policy, only when iv['level'] == 'do'
    (so the upstream proxy→tell cap and runway/AFK gates have already been applied)."""
    if iv.get("level") != "do":
        return iv
    wired = (iv.get("tool") in AUTO_ACT_TOOLS
             and iv.get("phase") == "escalate"
             and iv.get("disposability_source") == "explicit")
    if not wired:
        # other do-level tools, or handoff before escalation / without explicit
        # consent, stay advisory — never a silent auto-action.
        if iv.get("phase") == "escalate":
            iv["message"] += _PENDING
        return iv

    may, reason = access()
    if not may:
        # freemium: degrade to manual — never hard-block. The escalate message already
        # tells the user how to run `handoff`; just append the upsell.
        iv["auto_act"] = {"acted": False, "reason": "spent"}
        iv["message"] += _UPSELL
        return iv

    try:
        from mrtoken.handoff import build_handoff
        text = build_handoff(None, session_id)
    except Exception as e:   # fail closed: never let the executor break the nudge
        iv["auto_act"] = {"acted": False, "reason": "builder_failed"}
        iv["message"] += ("  [tried to auto-generate a handoff but hit an error — run "
                          f"`handoff` yourself. ({e})]")
        return iv
    if not text.startswith("# Handoff"):
        # build_handoff returns a plain "no transcript" string rather than raising;
        # treat any non-handoff result as a failure and DON'T spend a free use.
        iv["auto_act"] = {"acted": False, "reason": "builder_failed"}
        iv["message"] += "  [couldn't resolve a transcript to hand off — run `handoff` yourself.]"
        return iv

    note = ""
    if reason == "trial":
        _spend_free_use(session_id, iv["tool"])
        left = free_uses_left()
        note = (f"\n\n_(free auto-handoff — {left} of {FREE_USES} left; "
                "after that it stays one manual tap)_")
    iv["auto_act"] = {"acted": True, "reason": reason}
    iv["message"] += ("\n\n— Mr Token auto-generated this handoff; review it, then paste "
                      "into a fresh session:\n\n" + text + note)
    return iv
