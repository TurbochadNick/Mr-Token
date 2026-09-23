#!/usr/bin/env python3
"""MR Token — PreCompact hook.

Fires when Claude Code is about to compact the context, a material state change,
so it is the one Claude event surface kept. Surfaces /mr-handoff as a structured
alternative. It shows no ctx %: the payload carries no measured window.

Returns a systemMessage (does NOT block compaction — user chooses).
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

    cwd = payload.get("cwd")
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)

    # Stage-1 cohort gate (before the heavy import below → free out-of-cohort).
    from mrtoken.cohort import in_cohort
    if not in_cohort(cwd):
        sys.exit(0)

    try:
        from mrtoken.hud import attribution

        # Compaction IS the event, so the suggestion needs no percentage. The PreCompact
        # payload carries no measured context window (only the statusLine stdin does), so
        # any ctx % here would be a guess over an inferred window; it is not shown.
        if not payload.get("transcript_path"):
            sys.exit(0)
        msg = (f"{attribution()} · about to compact — /mr-handoff gives a structured handoff "
               "(goal · files · decisions · next steps) if you'd rather start fresh cleanly.")
        print(json.dumps({"systemMessage": msg}))

    except Exception:
        pass  # never block compaction

    sys.exit(0)


if __name__ == "__main__":
    main()
