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
from mrtoken.datadir import resolve_db_path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK_SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "on_stop.py")
PROMPT_HOOK_SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "on_prompt_submit.py")
SKILLS_SRC = os.path.join(os.path.dirname(HERE), "skills")  # backend/skills/<name>/SKILL.md
HOOK_MARKER = "on_stop.py"             # idempotency sentinel for Stop hook
PROMPT_HOOK_MARKER = "on_prompt_submit.py"  # idempotency sentinel for UserPromptSubmit


def hook_command() -> str:
    """The exact command Claude Code will run on Stop."""
    return f"{sys.executable} {HOOK_SCRIPT}"


def prompt_hook_command() -> str:
    """The command Claude Code runs on UserPromptSubmit (per-turn HUD)."""
    return f"{sys.executable} {PROMPT_HOOK_SCRIPT}"


def install_skills(root: str) -> list[str]:
    """Copy bundled MR Token skills into <root>/.claude/skills/. Returns names installed."""
    if not os.path.isdir(SKILLS_SRC):
        return []
    dest_root = os.path.join(root, ".claude", "skills")
    installed = []
    for name in sorted(os.listdir(SKILLS_SRC)):
        src = os.path.join(SKILLS_SRC, name, "SKILL.md")
        if not os.path.isfile(src):
            continue
        dest_dir = os.path.join(dest_root, name)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src, os.path.join(dest_dir, "SKILL.md"))  # overwrite keeps it current
        installed.append(name)
    return installed


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


def _prompt_hook_already_installed(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("UserPromptSubmit", []) or []:
        for h in entry.get("hooks", []) or []:
            if PROMPT_HOOK_MARKER in str(h.get("command", "")):
                return True
    return False


def _add_prompt_hook(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    ups = hooks.setdefault("UserPromptSubmit", [])
    ups.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": prompt_hook_command()}],
    })
    return settings


def _add_hook(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    stop.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_command()}],
    })
    return settings


def init(project_root: str | None = None, settings_path: str | None = None,
         global_settings_path: str | None = None,
         dry_run: bool = False, emit=print) -> int:
    root = find_project_root(project_root)
    db_path = resolve_db_path(root)  # shared contract (per-project for real projects)
    settings_path = settings_path or os.path.join(root, ".claude", "settings.local.json")
    global_settings_path = global_settings_path or os.path.expanduser("~/.claude/settings.json")

    emit(f"mrtoken init ▸ project root: {root}")

    skills = sorted(
        n for n in (os.listdir(SKILLS_SRC) if os.path.isdir(SKILLS_SRC) else [])
        if os.path.isfile(os.path.join(SKILLS_SRC, n, "SKILL.md")))

    if dry_run:
        emit(f"  would create DB:            {db_path}")
        emit(f"  would edit settings:        {settings_path}")
        emit(f"  would add Stop hook:        {hook_command()}")
        emit(f"  would install skills:       {', '.join('/'+s for s in skills) or '(none)'}")
        emit(f"  would add per-turn HUD:     {global_settings_path}")
        emit(f"    UserPromptSubmit command: {prompt_hook_command()}")
        return 0

    # 1 + 2: create the shared DB (connect() makes the dir, tables, view)
    connect(db_path).close()
    emit(f"  ✓ database ready:      {db_path}")

    # 3: install bundled skills (idempotent — overwrite keeps them current)
    installed = install_skills(root)
    if installed:
        emit(f"  ✓ installed skills:    {', '.join('/'+s for s in installed)}")

    # 4: install the Stop hook, preserving everything
    settings = _load_settings(settings_path)
    if _already_installed(settings):
        emit("  ✓ Stop hook already installed")
    else:
        backup = _backup(settings_path)
        if backup:
            emit(f"  ✓ backed up settings:  {os.path.basename(backup)}")
        _add_hook(settings)
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")
        emit(f"  ✓ installed Stop hook: {settings_path}")

    # 5: add UserPromptSubmit HUD hook to global Claude Code settings (idempotent)
    global_settings = _load_settings(global_settings_path)
    # remove any stale statusLine key from earlier installs
    global_settings.pop("statusLine", None)
    if _prompt_hook_already_installed(global_settings):
        emit("  ✓ per-turn HUD hook already installed")
    else:
        backup = _backup(global_settings_path)
        if backup:
            emit(f"  ✓ backed up global settings: {os.path.basename(backup)}")
        _add_prompt_hook(global_settings)
        os.makedirs(os.path.dirname(global_settings_path), exist_ok=True)
        with open(global_settings_path, "w", encoding="utf-8") as fh:
            json.dump(global_settings, fh, indent=2)
            fh.write("\n")
        emit(f"  ✓ per-turn HUD hook set: {global_settings_path}")
        emit(f"    command: {prompt_hook_command()}")

    emit("\n  Use Claude Code normally — sessions are ingested on Stop.")
    emit("  When a session bloats, run /mr-handoff to start fresh cleanly.")
    return 0
