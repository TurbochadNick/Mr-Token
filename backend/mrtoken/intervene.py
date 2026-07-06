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
import glob, json, os, time
from datetime import datetime, timezone

# Reclaimable = junk a tool can actually fix (offload/handoff), not real work.
RECLAIMABLE = {"huge_tool_output", "re_read_loop", "repeated_context", "context_rot"}
PRESSURE_PCT = 70        # ctx % at/above this = pressure
PRESSURE_TURNS = 4       # this few projected turns-to-full = pressure
DEBOUNCE_BAND = 10       # only re-fire after ctx climbs another 10 points


# Runway gate (COMPACTION-GATE Gate 2) thresholds. Near-done needs POSITIVE
# evidence on every axis — missing a suppression is cheap, suppressing a real
# win is the costly error, so anything ambiguous counts as runway-remaining.
NEAR_DONE_MIN_CALLS = 8          # too early in a session to call it near-done
NEAR_DONE_MIN_WINDOW = 6        # need most of the error window populated
NEAR_DONE_MAX_LATE_ERRORS = 1   # late half must be (nearly) green


def _near_done(progress: dict | None) -> bool:
    """Conservative runway proxy: the task looks near-done only when errors are
    trending down to (nearly) green AND durable artifacts landed recently."""
    if not progress:
        return False
    if progress.get("calls", 0) < NEAR_DONE_MIN_CALLS:
        return False
    if (progress.get("window") or 0) < NEAR_DONE_MIN_WINDOW:
        return False
    e1, e2 = progress.get("errors_first_half"), progress.get("errors_second_half")
    if e1 is None or e2 is None:
        return False
    improving = e2 < e1 and e2 <= NEAR_DONE_MAX_LATE_ERRORS
    landing = (progress.get("recent_writes") or 0) >= 1
    return improving and landing


def _disposable_source(disposability: dict | None) -> str | None:
    """Where the disposable verdict came from. 'disposable' is the recency
    PROXY (LiveMonitor); 'disposable_confirmed' is an EXPLICIT confirmation
    (reserved for the mr-context/toolbox channel). The distinction matters:
    the proxy cannot tell the win regime from the lose regime at pressure time
    (falsified on the 5A reset points — PR #19), so only explicit may escalate."""
    if not disposability:
        return None
    vals = set(disposability.values())
    if "disposable_confirmed" in vals:
        return "explicit"
    if "disposable" in vals:
        return "proxy"
    return None


def _tool_for(signals: set, *, disposable: bool = False) -> tuple[str, str]:
    if "huge_tool_output" in signals:
        return "offload", "a large tool output already hit context; do not rerun it normally"
    if "re_read_loop" in signals or "repeated_context" in signals:
        return "offload", "the same content is being re-paid into context"
    if "context_rot" in signals:
        # context_rot alone can't tell disposable context (a reset wins) from
        # load-bearing (a reset loses ~+20% — docs/COMPACTION-GATE.md). Gate 1:
        # only a block classified disposable unlocks the destructive drop;
        # otherwise nudge the reversible tool with handoff as an advisory option.
        if disposable:
            return "handoff", "we've done a lot this session and context is getting full"
        return "offload", "we've done a lot this session and context is getting full"
    return "offload", "reclaimable context"


def evaluate(ctx_pct, turns_to_full, signals_fired, *, disposability: dict | None = None,
             progress: dict | None = None,
             pressure_pct: int = PRESSURE_PCT, pressure_turns: int = PRESSURE_TURNS) -> dict | None:
    """Pure decision: return an intervention dict, or None. Agent-agnostic.
    `disposability` maps block ids to 'disposable'|'load_bearing' (Gate 1);
    `progress` carries recent-turn error/write metadata (Gate 2). None for
    either (the default) means unknown and keeps the prior-phase behaviour."""
    pressure = (ctx_pct is not None and ctx_pct >= pressure_pct) or \
               (turns_to_full is not None and 0 < turns_to_full <= pressure_turns)
    junk = {s for s in (signals_fired or []) if s in RECLAIMABLE}
    if not (pressure and junk):
        return None
    if _near_done(progress):
        # Gate 2: with little runway left, summary + re-establish costs more
        # than the remaining turns' carry — even on disposable context. Say
        # nothing and let the agent finish.
        return None
    src = _disposable_source(disposability)
    tool, why = _tool_for(junk, disposable=src is not None)
    turns_note = f", ~{turns_to_full} turns to full" if turns_to_full else ""
    if tool == "offload" and junk == {"context_rot"}:
        # Advisory handoff mention only — clearly optional, agent's judgement.
        action = ("use `offload` for saved bulk you must keep; a `handoff` to a fresh "
                  "session is optional and only pays if the loaded context is no "
                  "longer needed for the remaining work")
    elif tool == "offload":
        action = ("redirect future noisy commands to a file and inspect narrow slices; "
                  "use `offload` for saved bulk you must keep")
    elif src == "proxy":
        # Proxy-unlocked drop: the recency signal can't see future re-need, so
        # frame it as a question the agent answers, with the reversible out.
        action = ("some large context looks droppable (read once, untouched for "
                  "several turns) — only you can tell if it's truly done with. If "
                  "none of it is needed again, `handoff` to a fresh session pays; "
                  "if you'll need those refs, use `offload` instead. Run `handoff`?")
    else:
        action = ("we can continue this work more efficiently in a new session. "
                  "Do you want me to run `handoff` now?")
    msg = f"⚠ context {ctx_pct}%{turns_note} and {why}. {action}"
    if tool == "offload":
        msg += " (see the mr-context manual)."
    return {"severity": "warn", "tool": tool, "signals": sorted(junk),
            "ctx_pct": ctx_pct, "turns_to_full": turns_to_full, "message": msg,
            **({"disposability_source": src} if tool == "handoff" else {})}


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
    disp = snap.get("disposability") or {}
    # Explicit disposability channel: a FRESH agent confirmation (confirm_disposable)
    # unlocks an escalating drop the recency proxy alone cannot authorize (PR #19).
    if session_id and _fresh_disposable_confirmation(session_id, snap.get("model_calls") or 0):
        disp = {**disp, "explicit:session": "disposable_confirmed"}
    return decide(session_id, ctx_pct, snap.get("turns_to_warn"), snap.get("signals_fired"),
                  disposability=disp, progress=snap.get("progress"))


def decide(session_id: str, ctx_pct, turns_to_full, signals, *,
           disposability: dict | None = None, progress: dict | None = None) -> dict | None:
    """Agent-agnostic decision core: evaluate → autonomy gate → debounce →
    measure-don't-degrade → ask-phase. Reused by Claude (transcript snapshot) and
    Codex (rollout-derived ctx %). Returns the intervention to surface, or None."""
    iv = evaluate(ctx_pct, turns_to_full, signals,
                  disposability=disposability, progress=progress)
    if not iv:
        return None
    from mrtoken.policy import autonomy  # per-tool autonomy / global kill switch
    level = autonomy(iv["tool"])
    if level == "off" or not should_fire(session_id, iv["ctx_pct"]):
        return None
    # The recency proxy can't distinguish the drop-wins regime from the
    # drop-loses one at pressure time (falsified on the 5A reset points —
    # PR #19). A proxy-unlocked drop may TELL (a consent question), but only
    # an explicit disposability confirmation may escalate to ask/do.
    if iv.get("disposability_source") == "proxy" and level in ("ask", "do"):
        level = "tell"
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


# ── explicit disposability channel (GOALS/disposable-confirmed-channel.md) ──────
# The recency proxy can't tell the win regime from the lose regime at pressure time
# (falsified on the 5A reset points — PR #19), so it's capped at "tell". Only the
# agent — the one party that knows whether the FUTURE work re-needs the loaded
# context — can authorize an escalating drop, via the `confirm_disposable` tool. A
# confirmation expires (context changes, so an old "yes, drop it" must not authorize
# a later drop): valid within CONFIRM_TTL_CALLS more model calls AND CONFIRM_TTL_MIN
# minutes, whichever is tighter. Stale/absent → the drop stays proxy-capped.
CONFIRM_TTL_CALLS = 10
CONFIRM_TTL_MIN = 30
AMBIGUOUS_SESSION_WINDOW_S = 10 * 60


class AmbiguousSessionError(Exception):
    """Raised when a no-arg tool call cannot be bound to one live session."""


def _disposable_path(session_id: str) -> str:
    from mrtoken.datadir import central_default
    return os.path.join(central_default(), "state", f"disposable-{session_id}.json")


def _caller_session_env() -> str | None:
    return os.environ.get("MRTOKEN_SESSION") or os.environ.get("CLAUDE_CODE_SESSION_ID")


def _cwd_project_transcripts() -> list[str]:
    from mrtoken import watch
    cwd = os.getcwd()
    escaped = cwd.replace("/", "-").replace(".", "-")
    return glob.glob(os.path.join(watch.PROJECTS, escaped, "*.jsonl"))


def _recent_project_transcripts(candidates: list[str] | None = None,
                                now: float | None = None) -> list[str]:
    """Recent transcripts in this cwd's Claude project bucket.

    A no-arg MCP tool call has no reliable caller identity. If more than one
    transcript in the same project was written recently, newest-mtime is a race,
    so the caller must pass an explicit session id instead.
    """
    now = time.time() if now is None else now
    recent: list[str] = []
    for path in (candidates if candidates is not None else _cwd_project_transcripts()):
        try:
            if now - os.path.getmtime(path) <= AMBIGUOUS_SESSION_WINDOW_S:
                recent.append(path)
        except OSError:
            continue
    return sorted(recent, key=os.path.getmtime, reverse=True)


def _session_calls(session_arg: str | None) -> tuple[str | None, int]:
    """Resolve the current session's transcript → (session_id, model_calls). The id is
    the transcript filename. Metadata only — nothing from the content is persisted."""
    from mrtoken.watch import resolve_path, LiveMonitor, _iter_new_lines
    if not session_arg and not _caller_session_env():
        candidates = _cwd_project_transcripts()
        if not candidates:
            return None, 0
        recent = _recent_project_transcripts(candidates)
        if len(recent) > 1:
            raise AmbiguousSessionError(
                "multiple active sessions here — nothing recorded. Re-call with "
                "`session: <your session id>` (Bash: `echo $CLAUDE_CODE_SESSION_ID`)."
            )
        path = max(candidates, key=os.path.getmtime)
    else:
        path = resolve_path(session_arg)
    if not path:
        return None, 0
    mon = LiveMonitor(emit=lambda _: None)
    lines, _ = _iter_new_lines(path, 0)
    for ln in lines:
        try:
            mon.feed(json.loads(ln))
        except json.JSONDecodeError:
            continue
    sid = os.path.basename(path).rsplit(".", 1)[0]
    return sid, mon.snapshot().get("model_calls", 0)


def record_disposable_confirmation(session_arg: str | None = None) -> tuple[str | None, int]:
    """Persist an explicit 'the loaded context is no longer needed' confirmation for the
    current session. Returns (session_id, call_index) or (None, 0). Stores ONLY the call
    index + a timestamp — never content. Called by the `confirm_disposable` toolbox tool."""
    sid, calls = _session_calls(session_arg)
    if not sid:
        return None, 0
    p = _disposable_path(sid)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump({"confirmed_at_call": calls,
                       "confirmed_at_ts": datetime.now(timezone.utc).isoformat()}, fh)
    except OSError:
        return None, 0
    return sid, calls


def _fresh_disposable_confirmation(session_id: str, current_calls: int) -> bool:
    """True iff a still-valid confirmation exists (within BOTH the call and time TTLs).
    Stale or absent → False, so the drop stays capped at the proxy's tell-only level."""
    try:
        with open(_disposable_path(session_id)) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    if current_calls - int(data.get("confirmed_at_call", -10 ** 9)) > CONFIRM_TTL_CALLS:
        return False
    ts = data.get("confirmed_at_ts")
    if not ts:
        return False
    try:
        age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 60
    except ValueError:
        return False
    return age_min <= CONFIRM_TTL_MIN
