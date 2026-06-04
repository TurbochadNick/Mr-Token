#!/usr/bin/env python3
"""MR Token — pilot auto-install.

`mrtoken-transcript init` sets up the backend in a project with zero manual
steps, mirroring the TypeScript `init` flow so a pilot evaluator gets accurate
transcript-derived token data automatically:

  1. resolve the project root (git / package.json / pyproject.toml)
  2. create .token-tithe/token-tithe.db (the SHARED DB the TS CLI also uses)
  3. install a project-local Stop hook into .claude/settings.local.json that
     ingests each finished session into that DB and runs the rule engine

Safe by design: backs up an existing settings file first, preserves all existing
settings and hooks, and is idempotent (won't add our hook twice).
"""
from __future__ import annotations
import json, os, shutil, sys
from datetime import datetime, timezone

from mrtoken.ingest import connect, find_project_root

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK_SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "on_stop.py")
HOOK_MARKER = "on_stop.py"   # how we recognise our own hook for idempotency


def hook_command() -> str:
    """The exact command Claude Code will run on Stop."""
    return f"{sys.executable} {HOOK_SCRIPT}"


def _backup(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = f"{path}.mrtoken-bak.{stamp}"
    shutil.copy2(path, dest)
    return dest


def _load_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _already_installed(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("Stop", []) or []:
        for h in entry.get("hooks", []) or []:
            if HOOK_MARKER in str(h.get("command", "")):
                return True
    return False


def _add_hook(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    stop.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_command()}],
    })
    return settings


def init(project_root: str | None = None, settings_path: str | None = None,
         dry_run: bool = False, emit=print) -> int:
    root = find_project_root(project_root)
    db_path = os.path.join(root, ".token-tithe", "token-tithe.db")
    settings_path = settings_path or os.path.join(root, ".claude", "settings.local.json")

    emit(f"mrtoken init ▸ project root: {root}")

    if dry_run:
        emit(f"  would create DB:       {db_path}")
        emit(f"  would edit settings:   {settings_path}")
        emit(f"  would add Stop hook:   {hook_command()}")
        return 0

    # 1 + 2: create the shared DB (connect() makes the dir, tables, view)
    connect(db_path).close()
    emit(f"  ✓ database ready:      {db_path}")

    # 3: install the Stop hook, preserving everything
    settings = _load_settings(settings_path)
    if _already_installed(settings):
        emit("  ✓ Stop hook already installed — nothing to do")
        return 0

    backup = _backup(settings_path)
    if backup:
        emit(f"  ✓ backed up settings:  {os.path.basename(backup)}")

    _add_hook(settings)
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    emit(f"  ✓ installed Stop hook: {settings_path}")
    emit("\n  Use Claude Code normally — each session is ingested on Stop.")
    emit("  Inspect with:  mrtoken-transcript report   |   mrtoken-transcript fleet")
    return 0
