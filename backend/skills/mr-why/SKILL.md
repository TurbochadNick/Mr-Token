---
name: mr-why
description: Diagnose WHERE a Claude Code session's tokens/cost actually went and name the biggest fuel leak — use when the user says "/mr-why", "why is this so expensive", "where did my tokens go", "what's burning context", or wants to understand a session's cost before deciding to compact, hand off, or change reasoning effort.
---

# MR Token: why is this session expensive?

Run the backend command (deterministic, local, no AI call) and relay its output verbatim:

```bash
mrtoken-transcript why   # or: python3 -m mrtoken.cli why
```

It breaks down the cost shape (generating output vs carrying cached context vs writing new context vs fresh input), the avoidable drivers, and a one-line "main fuel leak" verdict. Do not re-read the transcript to recompute it. If the verdict points to a large carried context, suggest /mr-handoff; otherwise relay the action it names (e.g. lower reasoning effort, trim large reads or logs).
