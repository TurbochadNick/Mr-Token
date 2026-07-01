#!/usr/bin/env python3
"""MR Token — the proc engine (ROADMAP 6.4): the in-the-moment trigger.

At a turn boundary, decide whether to intervene. Fire only when BOTH:
  - pressure:      context is filling toward the wall (ctx % high, or few turns left), and
  - reclaimability: it's filling with junk a tool can FIX (a reclaimable signal fired).

Pressure alone is just a quiet HUD; pressure + fixable junk is a real nudge that
points the agent at the right toolbox tool + the mr-context manual. `evaluate()` is
pure (agent-agnostic, fully testable); `intervention_for_session()` feeds it from a
Claude transcript via LiveMonitor. Thresholds are constants now; 6.5 makes them
config. L1 "tell" only — 6.6 adds ask, 6.8 adds do.
"""
from __future__ import annotations
import json, os

# Reclaimable = junk a tool can actually fix (offload/handoff), not real work.
RECLAIMABLE = {"huge_tool_output", "re_read_loop", "repeated_context", "context_rot"}
PRESSURE_PCT = 70        # ctx % at/above this = pressure
PRESSURE_TURNS = 4       # this few projected turns-to-full = pressure
DEBOUNCE_BAND = 10       # only re-fire after ctx climbs another 10 points


def _tool_for(signals: set) -> tuple[str, str]:
    if "huge_tool_output" in signals:
        return "offload", "a large tool output already hit context; do not rerun it normally"
    if "re_read_loop" in signals or "repeated_context" in signals:
        return "offload", "the same content is being re-paid into context"
    if "context_rot" in signals:
        return "handoff", "we've done a lot this session and context is getting full"
    return "offload", "reclaimable context"


def evaluate(ctx_pct, turns_to_full, signals_fired, *,
             pressure_pct: int = PRESSURE_PCT, pressure_turns: int = PRESSURE_TURNS) -> dict | None:
    """Pure decision: return an intervention dict, or None. Agent-agnostic."""
    pressure = (ctx_pct is not None and ctx_pct >= pressure_pct) or \
               (turns_to_full is not None and 0 < turns_to_full <= pressure_turns)
    junk = {s for s in (signals_fired or []) if s in RECLAIMABLE}
    if not (pressure and junk):
        return None
    tool, why = _tool_for(junk)
    turns_note = f", ~{turns_to_full} turns to full" if turns_to_full else ""
    if tool == "offload":
        action = ("redirect future noisy commands to a file and inspect narrow slices; "
                  "use `offload` for saved bulk you must keep")
    else:
        action = ("we can continue this work more efficiently in a new session. "
                  "Do you want me to run `handoff` now?")
    msg = f"⚠ context {ctx_pct}%{turns_note} and {why}. {action}"
    if tool == "offload":
        msg += " (see the mr-context manual)."
    return {"severity": "warn", "tool": tool, "signals": sorted(junk),
            "ctx_pct": ctx_pct, "turns_to_full": turns_to_full, "message": msg}


def intervention_for_session(transcript_path: str | None = None,
                             session_id: str = "", session_arg: str | None = None) -> dict | None:
    """Build the live snapshot from a Claude transcript, evaluate, apply policy +
    debounce + ask-phase. Returns the intervention to surface, or None.

    Owns the full decision so the hook just renders iv['message']:
      evaluate → autonomy gate → debounce → ask-phase (first-ask vs AFK-escalation)."""
    from mrtoken.watch import resolve_path, LiveMonitor, _iter_new_lines
    from mrtoken.statusline import context_window
    path = transcript_path if (transcript_path and os.path.isfile(transcript_path)) \
        else resolve_path(session_arg)
    if not path:
        return None
    mon = LiveMonitor(emit=lambda _: None)
    lines, _ = _iter_new_lines(path, 0)
    for ln in lines:
        try:
            mon.feed(json.loads(ln))
        except json.JSONDecodeError:
            continue
    snap = mon.snapshot()
    ctx_now = snap.get("context_now") or 0
    win = context_window(snap.get("context_max") or ctx_now)
    ctx_pct = min(99, int(ctx_now / win * 100)) if (ctx_now and win) else 0
    return decide(session_id, ctx_pct, snap.get("turns_to_warn"), snap.get("signals_fired"))


def decide(session_id: str, ctx_pct, turns_to_full, signals) -> dict | None:
    """Agent-agnostic decision core: evaluate → autonomy gate → debounce →
    measure-don't-degrade → ask-phase. Reused by Claude (transcript snapshot) and
    Codex (rollout-derived ctx %). Returns the intervention to surface, or None."""
    iv = evaluate(ctx_pct, turns_to_full, signals)
    if not iv:
        return None
    from mrtoken.policy import autonomy  # per-tool autonomy / global kill switch
    level = autonomy(iv["tool"])
    if level == "off" or not should_fire(session_id, iv["ctx_pct"]):
        return None
    iv["level"] = level
    # measure-don't-degrade (6.7): did the PRIOR recommendation for this session help?
    if session_id:
        try:
            from mrtoken import outcomes
            prior = _read_ask(session_id)
            if prior and prior.get("tool"):
                outcomes.record(prior["tool"],
                                outcomes.helped_from_ctx(prior.get("ctx_pct", 0), iv["ctx_pct"]),
                                session_id)
                outcomes.enforce()
                if autonomy(iv["tool"]) == "off":   # this tool just auto-disabled
                    return None
        except Exception:
            pass
    if level in ("ask", "do"):
        iv = apply_ask_policy(session_id, iv)  # first-ask vs AFK-escalation (+ act in 6.8)
    return iv


# ── L2 ask + AFK escalation (ROADMAP 6.6) ───────────────────────────────────────
# When a tool's autonomy is "ask", the first fire PROPOSES the action and waits for
# approval (the user's reply). If context stays critical on a later turn (the user
# didn't act = AFK), we ESCALATE: with the default warn-only that's a firmer nudge;
# when a tool is at "do" (6.8), escalation is where the auto-action plugs in.

def _ask_path(session_id: str) -> str:
    from mrtoken.datadir import central_default
    return os.path.join(central_default(), "state", f"ask-{session_id}.json")


def _read_ask(session_id: str) -> dict:
    try:
        with open(_ask_path(session_id)) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_ask(session_id: str, data: dict) -> None:
    p = _ask_path(session_id)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def apply_ask_policy(session_id: str, iv: dict, *, improved_drop: int = 5) -> dict:
    """Decide first-ask vs AFK-escalation for an ask/do-level intervention, and set
    iv['phase'] + iv['message'] accordingly. Persists ask-state per session."""
    tool, ctx = iv["tool"], iv.get("ctx_pct") or 0
    prior = _read_ask(session_id) if session_id else {}
    inaction = bool(prior and prior.get("tool") == tool
                    and ctx >= prior.get("ctx_pct", 0) - improved_drop)
    if inaction:
        iv["phase"] = "escalate"
        if tool == "offload":
            next_step = "Do the narrow-output plan now"
        else:
            next_step = "I can run `handoff` now so the work continues in a fresh session"
        iv["message"] = (f"⚠ STILL critical — context {ctx}% and the {tool}-able junk is unaddressed. "
                         f"{next_step} (see the mr-context manual).")
        if iv.get("level") == "do":
            iv["message"] += "  [auto-action pending — ROADMAP 6.8]"
    else:
        iv["phase"] = "ask"
        if tool == "handoff":
            iv["message"] = (f"{iv['message']}  → Reply `go` and I will run `handoff`; "
                             "otherwise we can keep going here.")
        else:
            iv["message"] = (f"{iv['message']}  → Reply `go` to run `{tool}` for the saved bulk, "
                             "or it escalates next turn if context stays critical.")
    _write_ask(session_id, {"tool": tool, "ctx_pct": ctx})
    return iv


# ── debounce: fire once per rising pressure band, not every turn ────────────────

def _state_path(session_id: str) -> str:
    from mrtoken.datadir import central_default
    return os.path.join(central_default(), "state", f"proc-{session_id}.json")


def should_fire(session_id: str, ctx_pct: int) -> bool:
    """True if we haven't already fired for this session at this pressure band.
    Persists the last-fired band so a steady-state high ctx doesn't nag every turn."""
    if not session_id:
        return True
    p = _state_path(session_id)
    last = -999
    try:
        with open(p) as fh:
            last = json.load(fh).get("last_fired_pct", -999)
    except (OSError, json.JSONDecodeError):
        pass
    if ctx_pct < last + DEBOUNCE_BAND:
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump({"last_fired_pct": ctx_pct}, fh)
    except OSError:
        pass
    return True
