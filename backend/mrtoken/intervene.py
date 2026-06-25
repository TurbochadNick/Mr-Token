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
        return "offload", "a large tool output is sitting in context"
    if "re_read_loop" in signals or "repeated_context" in signals:
        return "offload", "the same content is being re-paid into context"
    if "context_rot" in signals:
        return "handoff", "the session is deep and context is degrading"
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
    action = "on the big output" if tool == "offload" else "to start fresh"
    msg = (f"⚠ context {ctx_pct}%{turns_note} and {why}. Use the `{tool}` tool {action} "
           f"(see the mr-context manual) so you don't run out of context on junk.")
    return {"severity": "warn", "tool": tool, "signals": sorted(junk),
            "ctx_pct": ctx_pct, "turns_to_full": turns_to_full, "message": msg}


def intervention_for_session(transcript_path: str | None = None,
                             session_arg: str | None = None) -> dict | None:
    """Build the live snapshot from a Claude transcript and evaluate it."""
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
    iv = evaluate(ctx_pct, snap.get("turns_to_warn"), snap.get("signals_fired"))
    if iv:
        from mrtoken.policy import autonomy  # per-tool autonomy / global kill switch
        level = autonomy(iv["tool"])
        if level == "off":
            return None
        iv["level"] = level  # tell | ask | do — the wiring acts on this (6.6/6.8)
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
