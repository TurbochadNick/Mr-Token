---
name: mr-why
description: Diagnose WHERE a Claude Code session's tokens/cost actually went and name the biggest fuel leak — use when the user says "/mr-why", "why is this so expensive", "where did my tokens go", "what's burning context", or wants to understand a session's cost before deciding to compact, hand off, or change reasoning effort.
---

# MR Token — why is this session expensive?

Diagnose the cost shape of the current session and surface the single biggest
driver, so the user knows what to do about it.

## What to do

1. Run the MR Token backend command (auto-detects this session; deterministic,
   no AI call of its own):

   ```bash
   mrtoken-transcript why
   ```

   If `mrtoken-transcript` is not on PATH, fall back to:
   ```bash
   python3 -m mrtoken.cli why
   ```

2. Show the output **verbatim** — it includes the cost-shape breakdown
   (generating output vs carrying cached context vs writing new context vs fresh
   input), the avoidable drivers, and a one-line "main fuel leak" verdict.

3. If the verdict points to carrying a large context, suggest `/mr-handoff`.
   Otherwise relay the action the verdict names (e.g. lower reasoning effort,
   trim large reads/logs).

## Notes

- Keep it cheap: run the command and relay. Do NOT re-read the transcript into
  context to compute this yourself — that wastes the tokens the tool is measuring.
- This reads only the local ledger/transcript; nothing leaves the machine.
