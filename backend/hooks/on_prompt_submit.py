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

    tpath = payload.get("transcript_path")
    # proc engine (ROADMAP 6.4): if context-pressure + reclaimable junk both trip,
    # fire an actionable intervention (debounced) instead of the passive HUD line.
    try:
        from mrtoken.intervene import intervention_for_session, should_fire
        iv = intervention_for_session(transcript_path=tpath)
        if iv and should_fire(payload.get("session_id", ""), iv["ctx_pct"]):
            print(json.dumps({"systemMessage": "mr · " + iv["message"]}))
            sys.exit(0)
    except Exception:
        pass  # never block the prompt

    try:
        from mrtoken.statusline import build_statusline_text
        # use the EXACT transcript Claude Code handed us, not a newest-file guess
        line = build_statusline_text(transcript_path=tpath)
        if line:
            print(json.dumps({"systemMessage": line}))
    except Exception:
        pass  # never block the prompt

    sys.exit(0)


if __name__ == "__main__":
    main()
