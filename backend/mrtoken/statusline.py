#!/usr/bin/env python3
"""MR Token — one-line HUD for Claude Code's statusLine setting.

Reads the current session's live transcript, computes context %, cost,
profile, and the highest-priority rule signal, then prints ONE line to stdout.

Typical output:
  mr · Opus 4.8·high · ctx 78% ⚠ · 5h 88%⚠ · ~$1.20 · code · ⚠ retry loop
  mr · Opus 4.8·medium · ctx 42% · 5h 30% · ~$0.18 · research
  mr · no session

Registered in Claude Code settings.json as `statusLine` (object form). NOTE:
statusLine is a TERMINAL-CLI feature — it renders in the bottom status line of
`claude` running in a terminal. The Claude desktop GUI app ignores it (no status
line to populate). Reads only, never writes. Must exit quickly.
"""
from __future__ import annotations
import json
import re

CONTEXT_TIERS = (200_000, 1_000_000)  # known Claude context windows
CONTEXT_WARN_PCT = 70                 # show ⚠ flag at this % of the window or above
PLAN_WARN_PCT = 85                    # flag the 5h plan window at this % used or above
WEEKLY_WARN_PCT = 80                  # surface the 7-day window only once it nears this


def _config_context_max() -> int | None:
    """Persistent per-user window override: ~/.mrtoken/config.json {"context_max": N}.
    Set this once if you know your window (e.g. 1000000 on a 1M-context model) and
    the inferred `ctx %` stays exact with no tier-flip."""
    import os, json
    try:
        with open(os.path.expanduser("~/.mrtoken/config.json"), encoding="utf-8") as fh:
            v = json.load(fh).get("context_max")
        return int(v) if v and int(v) > 0 else None
    except Exception:
        return None


def context_window(context_now: int) -> int:
    """The model's context window. Prefer an explicit override (env then config),
    else INFER from observed usage.

    The transcript records the model as e.g. 'claude-opus-4-8' WITHOUT the [1m]
    marker, so we can't read the window off the model id. Usage can't exceed the
    window, so the smallest known tier that fits is the window. Caveat: a 1M
    session looks like a near-full 200k one UNTIL it crosses 200k, which is the
    one-step jump you'd see without an override. Callers pass the session's MAX
    context (not the latest reading) so the window only ratchets UP, never flips
    back down after a compaction. Set MRTOKEN_CONTEXT_MAX or config.json to avoid
    the jump entirely."""
    import os
    env = os.environ.get("MRTOKEN_CONTEXT_MAX", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    cfg = _config_context_max()
    if cfg:
        return cfg
    for tier in CONTEXT_TIERS:
        if context_now <= tier:
            return tier
    return CONTEXT_TIERS[-1]

_SIGNAL_LABELS: dict[str, str] = {
    "huge_tool_output": "huge output",
    "retry_loop":       "retry loop",
    "context":          "compact soon",
}

# priority order — last item in this list wins when multiple signals fired
_SIGNAL_PRIORITY = ["context", "huge_tool_output", "retry_loop"]


def _top_signal(signals: list[str]) -> str | None:
    best: str | None = None
    for s in _SIGNAL_PRIORITY:
        if s in signals:
            best = s
    return best


def _model_label(model) -> str | None:
    """Compact model name for the HUD. Accepts the statusLine `model` object
    ({id, display_name}) OR a bare model-id string (from the transcript).
    Prefers a display name that already carries a version, else derives
    'Family M.m' from the id, e.g. 'claude-opus-4-8' -> 'Opus 4.8'."""
    if not model:
        return None
    if isinstance(model, str):
        mid, disp = model, None
    else:
        mid, disp = model.get("id"), model.get("display_name")
    if disp and any(c.isdigit() for c in disp):
        return disp
    if mid:
        m = re.match(r"(?:claude-)?([a-z]+)-(\d+)-(\d+)", mid)
        if m:
            return f"{m.group(1).capitalize()} {m.group(2)}.{m.group(3)}"
    return disp or mid


def _plan_segment(pct: int | None) -> str | None:
    """5-hour subscription window usage, e.g. '5h 88%⚠' (⚠ when near the limit).
    From the statusLine stdin payload's rate_limits.five_hour; absent otherwise."""
    if pct is None:
        return None
    return f"5h {pct}%{'⚠' if pct >= PLAN_WARN_PCT else ''}"


def _weekly_segment(pct: int | None) -> str | None:
    """7-day (weekly) window — surfaced ONLY when getting close. The weekly cap is
    the painful one (a multi-day lockout, not a 5h cooldown), so it warrants an
    early heads-up; below the threshold it stays hidden to keep the line clean.
    From rate_limits.seven_day."""
    if pct is None or pct < WEEKLY_WARN_PCT:
        return None
    return f"7d {pct}%⚠"


def build_statusline_text(session_arg: str | None = None,
                          transcript_path: str | None = None,
                          model=None, effort: str | None = None,
                          plan_5h: int | None = None,
                          plan_7d: int | None = None) -> str | None:
    """Return the HUD string, or None if no active session found.

    If transcript_path is given (the statusLine protocol hands us the exact
    file on stdin), use it directly — far more accurate than newest-mtime.

    `model` / `effort` come from the statusLine stdin payload (model object and
    effort.level). `model` falls back to the transcript's last assistant model
    when not supplied (so the name still shows in the Stop-hook HUD); `effort`
    has no transcript source, so it only appears when the stdin payload provides
    it (i.e. in the terminal statusLine).
    """
    import os
    from mrtoken.watch import resolve_path, LiveMonitor, _iter_new_lines

    path = transcript_path if (transcript_path and os.path.isfile(transcript_path)) \
        else resolve_path(session_arg)
    if not path:
        return None

    mon = LiveMonitor(emit=lambda _: None)  # silent — only need snapshot data
    lines, _ = _iter_new_lines(path, 0)
    last_model = None
    for ln in lines:
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        mon.feed(obj)
        if obj.get("type") == "assistant":
            mm = (obj.get("message") or {}).get("model")
            if mm:
                last_model = mm

    snap = mon.snapshot()
    ctx_now = snap["context_now"]
    win = context_window(snap.get("context_max") or ctx_now)  # sticky window
    ctx_pct = min(99, int(ctx_now / win * 100)) if ctx_now else 0

    parts = ["mr"]

    # identity: which brain is running + how hard it's reasoning. model from the
    # stdin payload (terminal) or the transcript (anywhere); effort from stdin only.
    label = _model_label(model or last_model)
    if label:
        parts.append(f"{label}·{effort}" if effort else label)

    if ctx_pct:
        flag = " ⚠" if ctx_pct >= CONTEXT_WARN_PCT else ""
        # lead-time trend: while still below the warn line but climbing toward it,
        # show projected turns ('ctx 58% ↗~5t') so you can act before you hit it
        ttw = snap.get("turns_to_warn")
        trend = f" ↗~{ttw}t" if (ttw and ctx_pct < CONTEXT_WARN_PCT and ttw <= 12) else ""
        parts.append(f"ctx {ctx_pct}%{flag}{trend}")

    plan = _plan_segment(plan_5h)  # 5h subscription window (terminal/stdin only)
    if plan:
        parts.append(plan)

    week = _weekly_segment(plan_7d)  # weekly window — only when getting close
    if week:
        parts.append(week)

    if snap["cum_cost"] >= 0.01:
        parts.append(f"~${snap['cum_cost']:.2f}")

    if snap["profile"]:
        parts.append(snap["profile"])

    signals = snap["signals_fired"]
    # "compact soon" is a live gauge of CURRENT fullness, not a historical event:
    # suppress it if context is no longer high (e.g. a 1M session that passed
    # through the 140–200k band, briefly looked like a full 200k window, and then
    # revealed its real 1M window). retry/huge-output signals are real events, kept.
    if ctx_pct < CONTEXT_WARN_PCT:
        signals = [s for s in signals if s != "context"]
    top = _top_signal(signals)
    if top:
        parts.append(f"⚠ {_SIGNAL_LABELS.get(top, top)}")

    return " · ".join(parts)


def statusline_hud(session_arg: str | None = None) -> int:
    """Entry point for the `statusLine` setting.

    Claude Code pipes a JSON payload on stdin describing the current session
    (session_id, transcript_path, cwd, model). We read transcript_path from it
    so the line reflects THIS session, not the newest file on disk.
    """
    import os, sys
    transcript_path = None
    model = None
    effort = None
    plan_5h = None
    plan_7d = None
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        if raw.strip():
            payload = json.loads(raw)
            transcript_path = payload.get("transcript_path")
            model = payload.get("model")
            eff = payload.get("effort")
            effort = eff.get("level") if isinstance(eff, dict) else None
            rl = payload.get("rate_limits") or {}
            plan_5h = (rl.get("five_hour") or {}).get("used_percentage")
            plan_7d = (rl.get("seven_day") or {}).get("used_percentage")
            cwd = (payload.get("cwd")
                   or (payload.get("workspace") or {}).get("current_dir"))
            if cwd and os.path.isdir(cwd):
                os.chdir(cwd)
    except Exception:
        pass

    print(build_statusline_text(session_arg, transcript_path, model, effort, plan_5h, plan_7d)
          or "mr · no session")
    return 0
