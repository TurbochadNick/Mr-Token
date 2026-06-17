---
name: mr-handoff
description: Generate a compact, paste-ready handoff to continue the current Claude Code session in a FRESH session — use when the session has grown long/expensive/bloated, when the user says "/mr-handoff", "hand off", "start fresh", "this chat is too long", "compact and restart", or right after MR Token's Stop-hook nudge recommends a fresh handoff. Summarizes goal, last request, files touched, recent commands, and open token-waste signals.
---

# MR Token: fresh handoff

Run the backend command (deterministic, local, no AI call) and present its markdown output verbatim. It is already formatted to paste straight into a new session:

```bash
mrtoken-transcript handoff   # or: python3 -m mrtoken.cli handoff
```

Do not rewrite or re-derive it; the value is the exact, reviewable handoff. After it, add one line: "Review and edit anything missing, then start a fresh session and paste this in." It prints only metadata-derived structure and never stores prompt content.
