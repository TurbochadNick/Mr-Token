---
name: mr-handoff
description: Generate a compact, paste-ready handoff to continue the current Claude Code session in a FRESH session — use when the session has grown long/expensive/bloated, when the user says "/mr-handoff", "hand off", "start fresh", "this chat is too long", "compact and restart", or right after MR Token's Stop-hook nudge recommends a fresh handoff. Summarizes goal, last request, files touched, recent commands, and open token-waste signals.
---

# MR Token — fresh handoff

When a Claude Code session has grown bloated (large context, rising cost, retry
loops), the cheapest fix is to start a new session with a compact handoff. This
skill produces that handoff from the current session's transcript.

## What to do

1. Run the MR Token backend command (it auto-detects the newest transcript for
   the current project — i.e. THIS session — and is deterministic + cheap, no AI
   call of its own):

   ```bash
   mrtoken-transcript handoff
   ```

   If `mrtoken-transcript` is not on PATH, fall back to:
   ```bash
   python3 -m mrtoken.cli handoff
   ```

2. Present the command's markdown output to the user **verbatim** — it is already
   formatted to copy straight into a new session. Do not rewrite or summarize it;
   the value is in the exact, reviewable handoff.

3. Add one short line afterward: "Review and edit anything missing, then start a
   fresh session and paste this in." Remind them to add decisions/constraints the
   handoff couldn't infer.

## Notes

- This reads the transcript and **prints** the handoff; it never stores prompt
  content (the MR Token ledger stays metadata-only).
- Keep this cheap: just run the command and relay the output. Don't re-derive the
  handoff yourself by reading the whole transcript into context — that would waste
  exactly the tokens MR Token exists to save.
