# MR Token interview kit (recruiting, demo, capture)

Companion to [USER-INTERVIEW.md](USER-INTERVIEW.md), which is the script and is
ready. The script was never the bottleneck; starting was. This file is
everything around it so interviews can begin: who to reach, the messages to
send, the real findings to show in Section 4, and a per-interview capture sheet.

Goal unchanged: learn whether anyone will PAY, and for WHAT, before building a
paid tier. Run the BYU TTO pilot evaluator first, then 2 to 4 real Claude Code
users or teams.

## Targets (aim for ~5; the decision rule needs them)

| # | Who | Type | Status | Booked for |
|---|-----|------|--------|-----------|
| 1 | BYU TTO technical pilot evaluator (name TBD, ask Campbell/Dave) | warm | not contacted | |
| 2 | Claude Code power user (BYU CS / lab) | semi-warm | not contacted | |
| 3 | Small team that pays for Claude/Cursor | cold | not contacted | |
| 4 | Solo dev hitting rate limits | cold | not contacted | |
| 5 | Referral from #1 to #4 | referral | pending | |

## Outreach

Mom Test discipline applies to recruiting too: ask about THEIR world, do not
pitch the tool. Request 20 to 30 minutes. The reciprocity hook is offering to
show them one real thing about their own usage at the end, not a demo of a
product. Keep it short.

### A. BYU TTO technical pilot evaluator (warm)

> Subject: 20 min on your Claude Code experience?
>
> Hi [name], you are evaluating MR Token for the TTO. Before you form a view, I
> would rather hear how Claude Code actually fits your day: where long sessions
> or limits get in your way, what you do about it, and what you have tried. About
> 20 to 30 minutes, mostly me listening. At the end I can show you one real thing
> the tool found in an actual session if that is useful. When works this week?

### B. Claude Code user / small team (semi-cold)

> Subject: how Claude Code goes for you (20 min, not a sales call)
>
> Hi [name], I am researching how people actually use coding agents day to day,
> the parts that frustrate you, what you do when a session gets long or slow or
> throttled, whether cost ever comes up on your team. Not selling anything; I
> just want to understand the real workflow. 20 to 30 minutes? Happy to share
> what I am learning, and I can show you something concrete about your own usage
> if you want.

## Demo artifact for Section 4 (real, from the local fleet, 2026-06-15)

Show ONE finding, then stop talking. Live on their own (or a recent) session is
most convincing; these are true backups from this machine's fleet.

- **Re-read bloat (now caught live):** across 36 real local sessions, 7 (19%)
  re-read the same file or target 3+ times. Worst case re-paid **~78,000 tokens**
  re-reading a single large file already loaded into context. As of today this
  fires live in `watch`, not just after the fact.
- **Prior validated:** one session re-read files 87 times, about 141k tokens of
  avoidable context bloat.
- **Fleet corroboration (prior 55-session pass):** huge_tool_output 91%,
  retry_loop 100%, fresh_handoff 94%. The waste is not a one-off.

Reproduce live during the call:

    mrtoken-transcript report <session>   # retrospective findings on a session
    mrtoken-transcript watch              # live signals on the current session
    mrtoken-transcript handoff            # the fresh-session handoff summary

Then: "Is this something you would have wanted to know in the moment? Would it
have changed what you did?" Do not explain the tool. Let the finding land.

## Per-interview capture (copy one block per interview; fill within the hour)

    --- Interview N ---
    Date / name / how reached:
    Plan + personal-vs-company card + team size:
    Sharpest pain (with the story):
    What they already do / tools tried + whether they stuck:
    Reaction to the artifact (verbatim if possible):
    Real past spend on comparable tools + who signs off:
    Q1 would-pay-per-seat? (evidence, not yes/no):
    Q2 what free tools do NOT give them:
    Q3 "more within flat-rate limits" worth paying for, or expected free:
    Referrals:

## Rolling synthesis (update after each interview)

- Q1 pay-per-seat for recovered velocity, evidence so far:
- Q2 the gap beyond free (CodeBurn `optimize` etc.):
- Q3 flat-rate-limit help: pay-for or expect-free:
- Repeated paid feature pointed at by 2+ teams (the wedge, if any):
- Running referral list:

Decision after ~5 (from the script): if no team surfaces a budget-backed pain
the free tier does not already solve, the paid tier is not validated, keep it
free and revisit. If 2+ teams point at the same paid feature with past spend
behind it, that is the wedge to build next.
