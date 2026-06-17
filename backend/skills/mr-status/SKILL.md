---
name: mr-status
description: One-glance snapshot of the CURRENT Claude Code session's token spend and the single most important next action — use when the user says "/mr-status", "how am I doing", "token status", "how big is my context", "am I burning too much", or wants a quick health check before deciding to keep going, compact, or hand off.
---

# MR Token: session status

Run the backend command (deterministic, local, no AI call) and relay its output verbatim:

```bash
mrtoken-transcript status   # or: python3 -m mrtoken.cli status
```

It reports profile, calls, tokens, cache, est cost, context size, and the single top next action. Do not recompute it by reading the transcript yourself. If the "next" line points to a fresh start, suggest /mr-handoff; if to cost or shape, suggest /mr-why.
