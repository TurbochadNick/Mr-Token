#!/usr/bin/env python3
"""MR Token — external token-saver module registry (ROADMAP 7.2, groundwork).

Rosson's "plug-and-play hub": let a user register an external token-saver (e.g.
`headroomlabs-ai/headroom` — an MCP server that compresses tool outputs before the
LLM) as a Mr Token *module* that flows through the SAME machinery we already have:
  - toggle:  enabled flag here (+ policy autonomy by the module's name)
  - measure: savings.record(<module>, …) / outcomes.record(<module>, …) key by name,
             so a module's savings show up in `mrtoken-transcript savings` once a
             measurement shim reports them.

This is the registry + registration helper only. It does NOT vendor, run, or trust
any external code — actually wiring + measuring headroom/ponytail is the gated 7.3
(dependency/trust review). Stored in ~/.mrtoken/config.json under "modules", sharing
the config file with the intervention policy.
"""
from __future__ import annotations

from mrtoken import policy

KINDS = ("mcp", "guidance")  # an MCP server, or a guidance/manual module (like ponytail)


def list_modules() -> list[dict]:
    return policy._load().get("modules", [])


def _save(mods: list[dict]) -> None:
    cfg = policy._load()
    cfg["modules"] = mods
    policy._save(cfg)


def get_module(name: str) -> dict | None:
    return next((m for m in list_modules() if m.get("name") == name), None)


def add_module(name: str, kind: str = "mcp", command: str | None = None,
               args: list | None = None, note: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    if kind == "mcp" and not command:
        raise ValueError("an mcp module needs a command (how to launch its server)")
    mod = {"name": name, "kind": kind, "command": command, "args": args or [],
           "enabled": True, "note": note}
    _save([m for m in list_modules() if m.get("name") != name] + [mod])  # replace if exists
    return mod


def remove_module(name: str) -> None:
    _save([m for m in list_modules() if m.get("name") != name])


def set_enabled(name: str, on: bool) -> None:
    mods = list_modules()
    for m in mods:
        if m.get("name") == name:
            m["enabled"] = bool(on)
    _save(mods)


def mcp_registration(name: str) -> dict | None:
    """The agent-registration config for an mcp module (Claude `claude mcp add` /
    Codex `[mcp_servers]`). None for non-mcp or unknown modules."""
    m = get_module(name)
    if not m or m.get("kind") != "mcp":
        return None
    return {"command": m.get("command"), "args": m.get("args") or []}
