#!/usr/bin/env python3
"""MR Token — PreCompact hook.

Fires when Claude Code is about to auto-compact the context. Surfaces the
/mr-handoff option as a structured alternative — especially if the session
already has a fresh_handoff signal active.

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

    try:
        from mrtoken.watch import resolve_path, LiveMonitor, _iter_new_lines
        from mrtoken.statusline import context_window

        # use the EXACT transcript Claude Code handed us, not a newest-file guess
        path = resolve_path(payload.get("transcript_path"))
        if not path:
            sys.exit(0)

        mon = LiveMonitor(emit=lambda _: None)
        lines, _ = _iter_new_lines(path, 0)
        for ln in lines:
            try:
                mon.feed(json.loads(ln))
            except json.JSONDecodeError:
                pass

        snap = mon.snapshot()
        has_handoff_signal = "context" in snap["signals_fired"]
        cn = snap["context_now"]
        ctx_pct = min(99, int(cn / context_window(cn) * 100)) if cn else 0

        if has_handoff_signal or ctx_pct >= 70:
            msg = (
                f"mr ⚠  context at {ctx_pct}% — before Claude compacts: "
                "run /mr-handoff for a structured handoff (goal · files · decisions · next steps) "
                "vs lossy auto-compact. Your call."
            )
        else:
            msg = (
                "mr · about to compact — /mr-handoff gives a structured handoff summary "
                "if you'd rather start fresh cleanly."
            )

        print(json.dumps({"systemMessage": msg}))

    except Exception:
        pass  # never block compaction

    sys.exit(0)


if __name__ == "__main__":
    main()
