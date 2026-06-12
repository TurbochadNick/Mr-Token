#!/usr/bin/env python3
"""MR Token — one-line HUD for Claude Code's statusLine setting.

Reads the current session's live transcript, computes context %, cost,
profile, and the highest-priority rule signal, then prints ONE line to stdout.

Typical output:
  mr · ctx 78% ⚠ · ~$1.20 · code · ⚠ retry loop
  mr · ctx 42% · ~$0.18 · research
  mr · no session

Registered in Claude Code settings.json as `statusLine` — runs on every turn.
Reads only, never writes. Must exit quickly.
"""
from __future__ import annotations
import json

CONTEXT_MAX = 200_000   # current Claude context window (Sonnet/Opus/Haiku)
CONTEXT_WARN_PCT = 70   # show ⚠ flag at this % or above

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


def statusline_hud(session_arg: str | None = None) -> int:
    from mrtoken.watch import resolve_path, LiveMonitor, _iter_new_lines

    path = resolve_path(session_arg)
    if not path:
        print("mr · no session")
        return 0

    mon = LiveMonitor(emit=lambda _: None)  # silent — only need snapshot data
    lines, _ = _iter_new_lines(path, 0)
    for ln in lines:
        try:
            mon.feed(json.loads(ln))
        except json.JSONDecodeError:
            pass

    snap = mon.snapshot()
    ctx_now = snap["context_now"]
    ctx_pct = min(99, int(ctx_now / CONTEXT_MAX * 100)) if ctx_now else 0

    parts = ["mr"]

    if ctx_pct:
        flag = " ⚠" if ctx_pct >= CONTEXT_WARN_PCT else ""
        parts.append(f"ctx {ctx_pct}%{flag}")

    if snap["cum_cost"] >= 0.01:
        parts.append(f"~${snap['cum_cost']:.2f}")

    if snap["profile"]:
        parts.append(snap["profile"])

    top = _top_signal(snap["signals_fired"])
    if top:
        parts.append(f"⚠ {_SIGNAL_LABELS.get(top, top)}")

    print(" · ".join(parts))
    return 0
