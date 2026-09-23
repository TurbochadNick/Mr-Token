#!/usr/bin/env python3
"""MR Token — one-line HUD for Claude Code's statusLine setting.

Reads the current session's live transcript, builds the provider-neutral HUD
fields (mrtoken.hud), and prints the one-line view to stdout. No cost is shown:
there is no billing ground truth (backend/docs/ACCURACY-VALIDATION-2026-09-23.md).

Typical output:
  mr · Opus 5 (1M context)·high · ctx 80% ⚠ · ~2.1M tok · cache 94% · 5h 45% · code · ⚠ compact soon
  mr · Opus 4.8·? · ctx 42% · ~310k tok · cache 88% · research      (no stdin: effort unknown)
  mr · no session

Registered in Claude Code settings.json as `statusLine` (object form). NOTE:
statusLine is a TERMINAL-CLI feature — it renders in the bottom status line of
`claude` running in a terminal. The Claude desktop GUI app ignores it (no status
line to populate). Reads only, never writes. Must exit quickly.
"""
from __future__ import annotations
import json
import re

from mrtoken.hud import (CONTEXT_WARN_PCT, HudFields, binding_limiter, ctx_field,  # noqa: F401
                         format_line, known, not_applicable, recommend, unknown)

CONTEXT_TIERS = (200_000, 1_000_000)  # known Claude context windows
# ⚠ threshold: ONE definition, in hud.py, re-exported here for existing importers


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
        # family-M[-m][-YYYYMMDD]: 'claude-opus-5' -> 'Opus 5', 'claude-opus-4-8' -> 'Opus 4.8'.
        # The minor is 1-2 digits, so a date suffix is never read as a version.
        m = re.match(r"(?:claude-)?([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$", mid)
        if m:
            minor = f".{m.group(3)}" if m.group(3) else ""
            return f"{m.group(1).capitalize()} {m.group(2)}{minor}"
    return disp or mid


def build_statusline_text(session_arg: str | None = None,
                          transcript_path: str | None = None,
                          model=None, effort: str | None = None,
                          plan_5h: int | None = None,
                          plan_7d: int | None = None,
                          context_window_size: int | None = None) -> str | None:
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
    return format_line(claude_hud_fields(snap, model or last_model, effort, plan_5h, plan_7d,
                                         context_window_size))


_WINDOW_IN_NAME = re.compile(r"\s*\((\d+(?:\.\d+)?)([KkMm]) context\)")


def claude_hud_fields(snap: dict, model, effort, plan_5h=None, plan_7d=None,
                      context_window_size=None) -> HudFields:
    """Fields for a Claude session from its live transcript snapshot (LiveMonitor),
    plus whatever the statusLine stdin payload supplies (model, effort, window,
    rate limits). On the Stop-hook and app paths there is no stdin payload, so
    effort is UNKNOWN there and the window falls back to inference."""
    f = HudFields()
    label = _model_label(model)
    if label:
        # the name may carry "(1M context)"; strip it so it is not shown twice. It is NOT
        # used as a window source: the window comes only from the measured value below.
        label = _WINDOW_IN_NAME.sub("", label)
        f.model = known(label, "statusLine model" if not isinstance(model, str) else "transcript model id")
    else:
        f.model = unknown("no model in the transcript yet")
    f.effort = known(effort, "statusLine effort.level") if effort else unknown(
        "effort is not recorded in the transcript")

    # The window must be MEASURED for this session, re-read every render (so a mid-session
    # /model or window change follows): the harness-reported context_window_size. A window
    # looked up from the model name or inferred from usage is a guess; it is kept only as a
    # labelled estimate, and ctx % over an unmeasured window is not a measurement either.
    ctx_now = snap["context_now"]
    if context_window_size:
        window = int(context_window_size)
        f.context_window = known(window, "statusLine context_window_size (harness-reported, this render)")
        if ctx_now:
            f.ctx_pct = ctx_field(min(99, int(ctx_now / window * 100)), "latest call's input side / reported window")
        else:
            f.ctx_pct = unknown("no model call yet")
    else:
        guess = context_window(snap.get("context_max") or ctx_now) if ctx_now else None
        f.context_window = unknown("window not reported on this surface", estimate=guess)
        f.ctx_pct = unknown("window not reported, so ctx % has no measured denominator",
                            estimate=min(99, int(ctx_now / guess * 100)) if guess else None)
    ttw = snap.get("turns_to_warn")
    f.ctx_turns_to_warn = known(ttw, "recent context growth") if ttw else not_applicable()

    t = snap.get("cum_tokens") or {}
    if snap.get("model_calls"):
        f.total_tokens = known(sum(t.values()),
                               "computed: fresh + cache read + cache write + output, once per API response")
        input_side = t.get("input", 0) + t.get("cache_read", 0) + t.get("cache_write", 0)
        f.cache_ratio = (known(t.get("cache_read", 0) / input_side, "cache read / (fresh + cache read + cache write)")
                         if input_side else unknown("no input yet"))
    else:
        f.total_tokens = unknown("no model call yet")
        f.cache_ratio = unknown("no model call yet")

    f.limiter = binding_limiter([(300, plan_5h), (10080, plan_7d)], "statusLine rate_limits")
    f.profile = known(snap["profile"], "session profile") if snap.get("profile") else not_applicable()

    # Recommendations come ONLY from direct readouts (hud.recommend): "compact soon" is
    # context fullness NOW. The live monitor's retry/huge-output heuristics are not shown.
    return recommend(f)


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
    context_window_size = None
    cwd = None
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
            context_window_size = (payload.get("context_window") or {}).get("context_window_size")
            cwd = (payload.get("cwd")
                   or (payload.get("workspace") or {}).get("current_dir"))
            if cwd and os.path.isdir(cwd):
                os.chdir(cwd)
    except Exception:
        pass

    # Stage-1 cohort gate: no always-on statusline outside the allowlisted cohort.
    # (build_statusline_text opens no database: it reads only the transcript.)
    from mrtoken.cohort import in_cohort
    if not in_cohort(cwd):
        return 0

    print(build_statusline_text(session_arg, transcript_path, model, effort, plan_5h, plan_7d,
                                context_window_size)
          or "mr · no session")
    return 0
