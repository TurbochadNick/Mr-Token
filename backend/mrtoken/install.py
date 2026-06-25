#!/usr/bin/env python3
"""MR Token — pilot auto-install.

`mrtoken-transcript init` sets up the backend in a project with zero manual
steps, mirroring the TypeScript `init` flow so a pilot evaluator gets accurate
transcript-derived token data automatically:

  1. resolve the project root (git / package.json / pyproject.toml)
  2. create .token-tithe/token-tithe.db (the SHARED DB the TS CLI also uses)
  3. install the Stop hook into GLOBAL ~/.claude/settings.json — the same place
     the statusLine, per-turn/PreCompact hooks, and skills go — so it fires for
     sessions started from ANY folder (the desktop app runs sessions from many
     directories). on_stop.py resolves the correct per-project DB from the
     session payload's cwd, so global registration still lands data per project.

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
COMPACT_HOOK_SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "on_pre_compact.py")
SKILLS_SRC = os.path.join(os.path.dirname(HERE), "skills")  # backend/skills/<name>/SKILL.md
HOOK_MARKER = "on_stop.py"                  # idempotency sentinel for Stop hook
PROMPT_HOOK_MARKER = "on_prompt_submit.py"  # idempotency sentinel for UserPromptSubmit
COMPACT_HOOK_MARKER = "on_pre_compact.py"   # idempotency sentinel for PreCompact


def hook_command() -> str:
    """The exact command Claude Code will run on Stop."""
    return f"{sys.executable} {HOOK_SCRIPT}"


def prompt_hook_command() -> str:
    """The command Claude Code runs on UserPromptSubmit (per-turn HUD)."""
    return f"{sys.executable} {PROMPT_HOOK_SCRIPT}"


def compact_hook_command() -> str:
    """The command Claude Code runs on PreCompact."""
    return f"{sys.executable} {COMPACT_HOOK_SCRIPT}"


def statusline_command() -> str:
    """The command the statusLine setting runs each refresh (ambient HUD bar)."""
    exe = shutil.which("mrtoken-transcript")
    if exe:
        return f"{exe} statusline"
    # No console script (e.g. installed from source without pip). Run the cli
    # MODULE with the package dir on PYTHONPATH so it imports from any cwd. Note
    # `-m mrtoken` only prints help; the runnable entry is `-m mrtoken.cli`.
    pkg_parent = os.path.dirname(HERE)  # dir containing the mrtoken package
    return f'PYTHONPATH="{pkg_parent}" {sys.executable} -m mrtoken.cli statusline'


def statusline_block() -> dict:
    """The statusLine value in the object form Claude Code expects."""
    return {"type": "command", "command": statusline_command(), "padding": 0}


def install_skills(skills_root: str) -> list[str]:
    """Copy bundled MR Token skills into <skills_root>/<name>/SKILL.md. Installed
    GLOBALLY (~/.claude/skills) so /mr-* and the Stop-hook flywheel work in every
    project, matching the global hooks — not just where init was run. Returns names."""
    if not os.path.isdir(SKILLS_SRC):
        return []
    installed = []
    for name in sorted(os.listdir(SKILLS_SRC)):
        src = os.path.join(SKILLS_SRC, name, "SKILL.md")
        if not os.path.isfile(src):
            continue
        dest_dir = os.path.join(skills_root, name)
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


def _compact_hook_already_installed(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("PreCompact", []) or []:
        for h in entry.get("hooks", []) or []:
            if COMPACT_HOOK_MARKER in str(h.get("command", "")):
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


def _add_compact_hook(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreCompact", [])
    pre.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": compact_hook_command()}],
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


def _strip_hooks(settings: dict, event: str, marker: str) -> int:
    """Remove only the hooks for `event` whose command contains `marker`,
    preserving any unrelated hooks. Drops a now-empty event. Returns count removed."""
    events = settings.get("hooks", {})
    entries = events.get(event)
    if not entries:
        return 0
    removed, kept = 0, []
    for entry in entries:
        hs = entry.get("hooks", []) or []
        keep = [h for h in hs if marker not in str(h.get("command", ""))]
        removed += len(hs) - len(keep)
        if keep:
            entry["hooks"] = keep
            kept.append(entry)
    if kept:
        events[event] = kept
    else:
        events.pop(event, None)
    return removed


def uninstall(project_root: str | None = None, settings_path: str | None = None,
              global_settings_path: str | None = None, remove_skills: bool = True,
              emit=print) -> int:
    """Reverse of init: remove MR Token's hooks + statusLine (and the /mr-* skills)
    from the project-local and global Claude Code settings. Backs up each file
    first and preserves all your other settings. Leaves the local .token-tithe
    data in place (delete it with `rm -rf .token-tithe`)."""
    root = find_project_root(project_root)
    settings_path = settings_path or os.path.join(root, ".claude", "settings.local.json")
    global_settings_path = global_settings_path or os.path.expanduser("~/.claude/settings.json")

    # project-local: a legacy Stop hook (newer installs register it globally below)
    settings = _load_settings(settings_path)
    if _already_installed(settings):
        _backup(settings_path)
        _strip_hooks(settings, "Stop", HOOK_MARKER)
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2); fh.write("\n")
        emit(f"  ✓ removed Stop hook: {settings_path}")
    else:
        emit("  · no project Stop hook found")

    # global: Stop + statusLine + UserPromptSubmit + PreCompact
    g = _load_settings(global_settings_path)
    changed = bool(_strip_hooks(g, "Stop", HOOK_MARKER))
    if changed:
        emit("  ✓ removed global Stop hook")
    if statusline_command() in json.dumps(g.get("statusLine") or ""):
        g.pop("statusLine", None); changed = True
        emit("  ✓ removed statusLine HUD bar")
    changed = bool(_strip_hooks(g, "UserPromptSubmit", PROMPT_HOOK_MARKER)) or changed
    changed = bool(_strip_hooks(g, "PreCompact", COMPACT_HOOK_MARKER)) or changed
    if changed:
        _backup(global_settings_path)
        with open(global_settings_path, "w", encoding="utf-8") as fh:
            json.dump(g, fh, indent=2); fh.write("\n")
        emit(f"  ✓ removed global hooks: {global_settings_path}")
    else:
        emit("  · no global hooks found")

    if remove_skills:
        skills_root = os.path.join(os.path.dirname(global_settings_path), "skills")
        for name in ("mr-handoff", "mr-status", "mr-why"):
            d = os.path.join(skills_root, name)
            if os.path.isdir(d):
                shutil.rmtree(d); emit(f"  ✓ removed skill /{name}")

    emit("  done — other settings preserved; .token-tithe data left as-is "
         "(rm -rf .token-tithe to remove it).")
    return 0


def init(project_root: str | None = None, settings_path: str | None = None,
         global_settings_path: str | None = None, codex_skills_root: str | None = None,
         dry_run: bool = False, emit=print) -> int:
    root = find_project_root(project_root)
    db_path = resolve_db_path(root)  # shared contract (per-project for real projects)
    global_settings_path = global_settings_path or os.path.expanduser("~/.claude/settings.json")
    # The Stop INGEST hook defaults to GLOBAL settings now (see module docstring).
    # An explicit --settings still targets that file (legacy / advanced).
    stop_hook_path = settings_path or global_settings_path
    stop_hook_global = os.path.abspath(stop_hook_path) == os.path.abspath(global_settings_path)
    legacy_local = os.path.join(root, ".claude", "settings.local.json")

    emit(f"mrtoken init ▸ project root: {root}")

    skills = sorted(
        n for n in (os.listdir(SKILLS_SRC) if os.path.isdir(SKILLS_SRC) else [])
        if os.path.isfile(os.path.join(SKILLS_SRC, n, "SKILL.md")))
    # skills go next to the global settings (~/.claude/skills) so /mr-* shows up
    # in every project, not only where init ran — AND into ~/.codex/skills so the
    # Codex agent gets the same manual + tools (install only if Codex is present).
    skills_root = os.path.join(os.path.dirname(global_settings_path), "skills")
    codex_skills_root = codex_skills_root or os.path.expanduser("~/.codex/skills")
    install_codex_skills = os.path.isdir(os.path.dirname(codex_skills_root))  # ~/.codex exists

    if dry_run:
        emit(f"  would create DB:            {db_path}")
        emit(f"  would install skills:       {', '.join('/'+s for s in skills) or '(none)'} → {skills_root}")
        if install_codex_skills:
            emit(f"  would install Codex skills: {', '.join('/'+s for s in skills) or '(none)'} → {codex_skills_root}")
        emit(f"  would edit global settings: {global_settings_path}")
        emit(f"    Stop hook command:        {hook_command()}"
             + ("" if stop_hook_global else f"  (→ {stop_hook_path})"))
        emit(f"    statusLine command:       {statusline_command()}")
        emit(f"    UserPromptSubmit command: {prompt_hook_command()}")
        emit(f"    PreCompact command:       {compact_hook_command()}")
        if stop_hook_global and legacy_local != global_settings_path \
                and _already_installed(_load_settings(legacy_local)):
            emit(f"  would remove legacy project-local Stop hook: {legacy_local}")
        return 0

    # 1 + 2: create the shared DB (connect() makes the dir, tables, view)
    connect(db_path).close()
    emit(f"  ✓ database ready:      {db_path}")

    # 3: install bundled skills GLOBALLY (idempotent — overwrite keeps them current)
    installed = install_skills(skills_root)
    if installed:
        emit(f"  ✓ installed skills:    {', '.join('/'+s for s in installed)}  ({skills_root})")
    if install_codex_skills:
        c = install_skills(codex_skills_root)
        if c:
            emit(f"  ✓ installed Codex skills: {', '.join('/'+s for s in c)}  ({codex_skills_root})")

    # 4 (legacy override only): if --settings points at a non-global file, install
    # the Stop hook there, preserving everything. Default path is global (step 5).
    if not stop_hook_global:
        settings = _load_settings(stop_hook_path)
        if _already_installed(settings):
            emit("  ✓ Stop hook already installed")
        else:
            backup = _backup(stop_hook_path)
            if backup:
                emit(f"  ✓ backed up settings:  {os.path.basename(backup)}")
            _add_hook(settings)
            os.makedirs(os.path.dirname(stop_hook_path), exist_ok=True)
            with open(stop_hook_path, "w", encoding="utf-8") as fh:
                json.dump(settings, fh, indent=2)
                fh.write("\n")
            emit(f"  ✓ installed Stop hook: {stop_hook_path}")

    # 5: set the Stop hook (default), statusLine (ambient HUD bar), and the
    # UserPromptSubmit/PreCompact hooks in global Claude Code settings (idempotent)
    # so they fire for sessions started from any folder. statusLine is the primary
    # surface; the hooks are belt-and-suspenders for clients that render them.
    global_settings = _load_settings(global_settings_path)
    changed = False

    if stop_hook_global:
        if _already_installed(global_settings):
            emit("  ✓ Stop hook already installed (global)")
        else:
            _add_hook(global_settings)
            changed = True
            emit("  ✓ Stop hook → global settings (fires for sessions in any folder)")
        # migrate away a legacy project-local Stop hook so it can't double-fire
        if legacy_local != global_settings_path:
            local = _load_settings(legacy_local)
            if _already_installed(local):
                _backup(legacy_local)
                _strip_hooks(local, "Stop", HOOK_MARKER)
                with open(legacy_local, "w", encoding="utf-8") as fh:
                    json.dump(local, fh, indent=2); fh.write("\n")
                emit(f"  ✓ removed legacy project-local Stop hook (now global): {legacy_local}")

    desired_sl = statusline_block()
    existing_sl = global_settings.get("statusLine")
    if existing_sl != desired_sl:
        # warn before clobbering a status bar the user already had — the whole
        # settings file is backed up just below, so the old one is recoverable
        if existing_sl and statusline_command() not in json.dumps(existing_sl):
            emit("  ⚠ replacing your existing statusLine with MR Token's HUD "
                 "(restore it from the .mrtoken-bak backup written below)")
        global_settings["statusLine"] = desired_sl  # object form (string form is ignored)
        changed = True
        emit("  ✓ statusLine HUD bar set (object form)")
    else:
        emit("  ✓ statusLine already set")

    if _prompt_hook_already_installed(global_settings):
        emit("  ✓ per-turn HUD hook already installed")
    else:
        _add_prompt_hook(global_settings)
        changed = True
    if _compact_hook_already_installed(global_settings):
        emit("  ✓ PreCompact hook already installed")
    else:
        _add_compact_hook(global_settings)
        changed = True
    if changed:
        backup = _backup(global_settings_path)
        if backup:
            emit(f"  ✓ backed up global settings: {os.path.basename(backup)}")
        os.makedirs(os.path.dirname(global_settings_path), exist_ok=True)
        with open(global_settings_path, "w", encoding="utf-8") as fh:
            json.dump(global_settings, fh, indent=2)
            fh.write("\n")
        emit(f"  ✓ global settings written: {global_settings_path}")
        emit(f"    statusLine:    {statusline_command()}")
        emit(f"    UserPromptSubmit / PreCompact hooks also installed")

    emit("\n  Use Claude Code normally — sessions are ingested on Stop.")
    emit("  When a session bloats, run /mr-handoff to start fresh cleanly.")
    return 0
