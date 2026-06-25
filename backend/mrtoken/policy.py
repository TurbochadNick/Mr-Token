#!/usr/bin/env python3
"""MR Token — intervention policy (ROADMAP 6.5): per-tool autonomy + kill switch.

Governs how the PROC ENGINE surfaces a tool (not whether the agent can call it —
that's MCP availability, see toolbox.MRTOKEN_TOOLS_OFF). Four levels:

  off  — the proc engine never fires for this tool
  tell — L1: a prominent nudge (the default; warn-only out of the box)
  ask  — L2: propose + wait for approval (with AFK timeout) — wired in 6.6
  do   — L3: auto-remediate — wired in 6.8, gated on 6.7's measurement

Config: ~/.mrtoken/config.json {"interventions": {"enabled": true, "default": "tell",
"tools": {"offload": "ask", ...}}}. Env overrides: MRTOKEN_INTERVENE=off (global kill
switch), MRTOKEN_TOOLS_OFF=offload,handoff (force those off). Defaults to warn-only so
nothing acts unasked until you opt in.
"""
from __future__ import annotations
import json, os

LEVELS = ("off", "tell", "ask", "do")
DEFAULT_LEVEL = "tell"


def _config_path() -> str:
    return os.path.expanduser("~/.mrtoken/config.json")


def _load() -> dict:
    try:
        with open(_config_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(cfg: dict) -> None:
    p = _config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")


def kill_switch_on() -> bool:
    """False = interventions globally silenced (env MRTOKEN_INTERVENE=off, or config)."""
    if os.environ.get("MRTOKEN_INTERVENE", "").strip().lower() in ("0", "off", "false", "no"):
        return False
    return bool(_load().get("interventions", {}).get("enabled", True))


def autonomy(tool: str) -> str:
    """The proc-engine autonomy level for `tool`: off | tell | ask | do."""
    if not kill_switch_on():
        return "off"
    off_env = {t.strip() for t in os.environ.get("MRTOKEN_TOOLS_OFF", "").split(",") if t.strip()}
    if tool in off_env:
        return "off"
    iv = _load().get("interventions", {})
    lvl = (iv.get("tools") or {}).get(tool, iv.get("default", DEFAULT_LEVEL))
    return lvl if lvl in LEVELS else DEFAULT_LEVEL


def set_autonomy(tool: str, level: str) -> None:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    cfg = _load()
    cfg.setdefault("interventions", {}).setdefault("tools", {})[tool] = level
    _save(cfg)


def set_enabled(on: bool) -> None:
    cfg = _load()
    cfg.setdefault("interventions", {})["enabled"] = bool(on)
    _save(cfg)


def summary() -> dict:
    iv = _load().get("interventions", {})
    return {"enabled": kill_switch_on(), "default": iv.get("default", DEFAULT_LEVEL),
            "tools": iv.get("tools", {})}
