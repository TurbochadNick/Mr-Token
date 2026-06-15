#!/usr/bin/env python3
"""MR Token — UserPromptSubmit hook.

Fires before each user prompt is processed. Reads the current session
transcript and injects a compact status line as a systemMessage so the
user sees context %, cost, profile, and top rule signal each turn.

Example systemMessage: mr · ctx 45% · ~$0.84 · code · ⚠ retry loop
"""
import json, os, sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def _dbg(msg: str) -> None:
    """Append a diagnostic line so we can confirm this hook actually fires."""
    try:
        from datetime import datetime
        d = os.path.expanduser("~/.mrtoken")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "hook-debug.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} [UserPromptSubmit] {msg}\n")
    except Exception:
        pass


def main():
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    # run from the project cwd so resolve_path finds the right transcript
    cwd = payload.get("cwd")
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)

    try:
        from mrtoken.statusline import build_statusline_text
        line = build_statusline_text()
        _dbg(f"fired cwd={cwd or ''} emit={line!r}")
        if line:
            print(json.dumps({"systemMessage": line}))
    except Exception as e:
        _dbg(f"error: {e}")  # never block the prompt

    sys.exit(0)


if __name__ == "__main__":
    main()
