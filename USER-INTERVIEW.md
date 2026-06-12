# MR Token — user / pilot interview script

Goal: find out whether anyone will PAY, and for WHAT, before we build a paid tier.
Two deep research passes told us the pain is real but willingness-to-pay is
unproven and only real users can answer it. This is that conversation.

Use it with the BYU TTO pilot evaluator and 2-4 real Claude Code users/teams.

## Ground rules (read before every interview)

- **Do not pitch.** The moment you describe MR Token, they start being polite.
  Talk about THEIR life and PAST behavior, not your idea or their future.
- **Never ask "would you pay?"** Hypothetical WTP is the least reliable signal
  there is. Ask what they pay for *today*, what they've *already* done about the
  pain, and who controls budget. (Mom Test discipline.)
- **Dig into specifics and emotion.** "Tell me about the last time..." beats
  "do you usually...". Follow pain that has a story attached.
- ~20-30 min. Mostly listen. Silence is fine.

## 1. Context / qualify (2-3 min)
- What are you building, and how does Claude Code (or Cursor/Codex) fit your day?
- Solo, or on a team? If team: how many devs use it, and who pays for the plan?
- Which plan are you on (Pro / Max / API / Cursor)? Personal card or company card?

## 2. Pain discovery — let them surface it, do NOT lead (8-10 min)
- Tell me about the last time a coding-agent session frustrated you. What happened?
- (If not mentioned) Have you ever hit a rate limit or had it slow down? Walk me
  through that day. What did you do? Did it block shipping anything?
- Have you ever felt the agent got "dumber" or lost the plot in a long session?
  What did that cost you (time, rework, a bad merge)?
- Do you ever think about how many tokens / how much context a session is using?
  When, and why?

## 3. Current behavior — what they already do (4-5 min)
- When a session gets long or slow, what do you actually do? (compact? /clear?
  new session? just push through? nothing?)
- Have you ever installed anything to watch your usage (ccusage, CodeBurn, a
  monitor)? What made you try it, and do you still use it? Why / why not?
- Has your team ever discussed agent cost or usage? Who raised it, what came of it?

## 4. Reaction to the artifact — show, don't sell (4-5 min)
Show ONE real finding (e.g. "this session re-read files 87 times, ~141k tokens
of avoidable context bloat" + a `status`/`handoff` example). Then shut up.
- What's your reaction? Is this something you'd have wanted to know in the moment?
- Would this have changed what you did in that session? How?
- What's missing / what would you want it to also tell you?

## 5. Money — past and present, never hypothetical (4-5 min)
- What dev tools do you personally pay for out of pocket right now? What about
  the team / company?
- For the usage tools you've tried, were any paid? Would you have paid? (Then
  push: did you actually pay for anything like it?)
- If your team were losing real shipping time to throttling or bad long sessions,
  who would have to sign off to spend money fixing it? Have they spent on
  anything like that before?
- (Only if they lean in) The measurement and basic advice would be free. What
  would have to be true for a team to pay for the extra layer (shared usage
  across the team, attribution, governance, an assistant that writes the handoff
  for you)? Which of those, if any, is worth real money to you?

## 6. The three questions we must leave able to answer
1. Would a team lead pay per-seat to recover velocity lost to throttling / bad
   long sessions? (Evidence = past spend + who signs off, not a yes/no.)
2. What do they need that a free tool (CodeBurn's `optimize` etc.) does NOT give?
3. Is "do more within your flat-rate limits" worth paying for, or expected free?

## Wrap
- Who else should I talk to? (referrals = the best output of every interview)
- Can I follow up when there's something to try?

## After each interview — log within an hour
- Plan / personal-vs-company card / team size:
- Sharpest pain (with the story):
- What they already do / tools tried + retention:
- Reaction to the artifact (verbatim if possible):
- Real past spend on comparable tools + who signs off:
- Verdict on the 3 questions: would-pay-per-seat? / beyond-free? / worth-paying-or-free?
- Referrals:

## Decision rule
After ~5 interviews: if NO team surfaces a budget-backed pain that the free tier
doesn't already solve, the paid tier is not validated — keep it free / open-source
and revisit. If 2+ teams point at the same paid feature with past spend behind it,
that feature is the paid wedge to build next.
