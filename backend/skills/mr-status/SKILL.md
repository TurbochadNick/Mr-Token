---
name: mr-status
description: One-glance snapshot of the CURRENT Claude Code session's token spend and the single most important next action — use when the user says "/mr-status", "how am I doing", "token status", "how big is my context", "am I burning too much", or wants a quick health check before deciding to keep going, compact, or hand off.
---

# MR Token — session status

Give the user a fast read on the current session and what to do next.

## What to do

1. Run the MR Token backend command (auto-detects this session; deterministic,
   no AI call of its own):

   ```bash
   mrtoken-transcript status
   ```

   If `mrtoken-transcript` is not on PATH, fall back to:
   ```bash
   python3 -m mrtoken.cli status
   ```

2. Show the output **verbatim**. It reports profile, calls, tokens, cache hit,
   est cost, current context size, and the single top next action.

3. If the "next" line points to a fresh start, suggest `/mr-handoff`. If it points
   to cost/shape, suggest `/mr-why`. Otherwise just relay it.

## Notes

- Keep it cheap: run the command and relay. Do NOT read the whole transcript into
  context to compute this yourself.
- Local only; nothing leaves the machine.
