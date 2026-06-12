# MR Token — Product Direction

*Proposed direction for sign-off. Zach drafted these; Nick, react/amend freely —
nothing here is locked until we both agree.* · 2026-06-04

## 1. Ownership
**Joint venture, Nick + Zach.** (BYU/TTO ownership question parked for now —
flagged for revisiting before there's real revenue, since it's in a BYU TTO pilot.)

## 2. Scope — stay narrow on Claude Code
**Do not build multi-agent adapters yet.** The moat is that Claude Code's
transcripts expose *real* token counts; that advantage doesn't transfer to tools
that only allow estimates. Win Claude Code decisively first, expand later from
strength. (Revisit only if the pilot/TTO explicitly wants a broad internal tool.)

## 3. One tool, eventually TypeScript
Long-term: **one installable tool, target TypeScript** (npm + single-binary is
solved there; a Node tool that needs a Python runtime loses users at install).

**For now**, the Python engine stays as the *optional accuracy layer* — no rush.
**Port Python → TS only when all three are true:**
1. the pilot has given its verdict (don't rewrite something that might pivot),
2. the rule logic has been stable ~2+ weeks (don't port a moving target),
3. we've committed to external/public distribution (the only thing two languages
   actually blocks).

The engine is ~1500 LOC, so the port is a bounded few-day job once rules freeze.
Cheap to defer, cheap to do later.

## 4. The wedge (revised 2026-06-05 after two research passes)
Two independent research passes (a 105-agent deep-research run + a Perplexity
pass) reshaped this. See `backend/docs/ROI-EXPERIMENT.md` (pilots) and the
research notes. Key findings:
- **Measurement alone is table stakes** — several free local-first token trackers
  already exist (ccusage, tokscale, TokenTracker, ...). We cannot lead with "we
  measure your tokens."
- **The open gap = session-level TIMING signals + recommend/act.** No tool turns
  context best-practices into live "do this now" signals. That is the wedge.
- **The real waste is DYNAMIC, not "repeated context."** Prompt caching makes
  re-sending the static prefix cheap, so "repeated context costs money" is a myth.
  But dynamic working-set bloat (huge tool outputs, re-read loops, excessive
  steps) is NOT cache-friendly and dominates cost/throughput in long sessions
  (Stanford "How AI agents spend your money": same task varies up to 30x by
  step/re-read count). Our most-fired rule, `huge_tool_output`, targets exactly
  this.
- **Whole-session handoff is NOT the savings lever** (it resets the cheap cached
  prefix too). Keep the handoff, but as a QUALITY / capacity tool, not the
  headline token-saver. This is why the ROI pilots showed handoff costing more.

**So the wedge is: watch for the waste that actually costs you (tool-output
bloat, re-read loops, context rot) and surface the one action to take now.**

**Free vs paid (clarified):** recommendations were ALWAYS meant to be free; the
paid tier is *other* features. This matters because the free incumbent CodeBurn
shipping free recommendations does not threaten our wedge — it confirms that the
free tier (measurement + rule-based advice) is correctly free, the same place we
put it. The paid layer is therefore NOT "charge for advice" but a team intelligence layer
(see §6 for the evidence-backed specifics):
- **Team attribution + intelligence** (per-dev usage/attribution, shared config &
  policy, and team-level *what-to-do* recommendations) — the one thing a single
  local binary can't self-provide, and the evidence-backed #1 paid feature.
- **Premium assistive actions** (LLM-polished handoff, log summarization) — opt-in.
**Hard line:** no auto-compaction, no silent rewriting, ever. The free core stays
100% local + private; cloud/LLM lives only in the paid, opt-in tier (see §6 fork).

## 5. Positioning — efficiency, framed as three benefits of one thing
Cutting dynamic waste at the right moment delivers three benefits; lead with
whichever fits the user, do NOT drop any:
- **Save money** — real on metered/API usage, specifically by killing dynamic
  bloat and re-read loops (not the repeated-context myth).
- **Do more within your limits** — flat-rate plans (Claude Code Max, Cursor) meter
  usage by tokens across surfaces; long bloated sessions eat your quota and
  exhaust the context window. Vendor-documented.
- **Keep your agent sharp** — research-backed: output quality degrades as context
  bloats (Context Rot, Lost-in-the-Middle). Universal, every plan.

One-liner: *MR Token watches your agent for the waste that actually costs you, and
tells you the one thing to do about it right now — so you spend less, do more
within your limits, and keep the agent sharp.*

## 6. Monetization (the "what to charge for" question is now ANSWERED; "will our buyer pay" is not)
Two research passes shaped this. The 104-agent pass (2026-06-05) found the hard
constraints; a focused Perplexity report (2026-06-12, "Measuring & Reducing AI
Token Waste", 15pp/~41 cites) answered *what the paid feature should be* with
evidence. Full notes in memory.

**Constraints (still hold):**
- **Every direct measurement competitor is free, MIT, local-first** (ccusage,
  CodeBurn, TokenTracker). Measurement + rule-based advice is free-tier territory.
- **Individual out-of-pocket WTP looks weak** — individuals have free substitutes.
  Plausible paid buyer = **team / devex lead / eng-leadership**.
- **Pricing gravity:** AI coding tools ~$20/mo individual; **$19-40/seat team**;
  observability $39-79/mo or open-core. Free-tier→paid is the norm. Realistic
  free-to-paid conversion for a dev-tool CLI is **1-3%** (need install volume first).
- **Savings-share pricing does NOT map** — flat-rate plans have no metered dollar.
- **Local-first helps trust, not monetization** (no usage hook, forkable).

**WHAT TO CHARGE FOR — answered (evidence-backed, HIGH confidence):** the #1 paid
feature is a **team usage attribution dashboard** (per-dev token spend, per-session
trends, cost-per-merged-PR). Evidence: Uber burned its entire 2026 AI-coding budget
in 4 months for lack of per-dev visibility; funded competitors already sell this
(Codensics, Coder AI Governance Add-On); OpenAI says the bottleneck shifts "from
access cost to governance." Governance/attribution is an *actively-purchased*
category, not nascent. Paid-feature ranking by evidence: (1) team attribution
dashboard, (2) SSO/SAML (enterprise procurement enabler, naturally fork-proof —
needs a server), (3) shared config/policy, (4) history retention/reports, (5)
premium LLM-assist/handoff (weak direct evidence teams pay for this alone),
(6) support/SLA.

**Our differentiator vs the funded players:** Codensics/Coder/TokenUse do
governance + quotas + attribution but NOT *what-to-do* reasoning. Our paid tier
should be an **intelligence/recommendation layer** = the single-session
recommendation wedge extended to the team ("your team's biggest leak this sprint
was X; here's the shared rule"), not a dumb dashboard. This is **Layer 4** of the
founding 4-layer model (opt-in AI optimizer) — not a pivot. Scope it as stateless
LLM *inference over aggregated metadata*, NOT "a system that learns" (training =
research-project trap).

**THE ARCHITECTURAL FORK (deliberate decision needed, with Nick — do not drift):**
the #1 paid feature *requires a server* to aggregate across developers, and the
LLM layer rides on that server. This is in direct tension with the local-first /
no-cloud / "nothing leaves your machine" identity. Resolution = a **clean tier
split**: free tier stays deterministic + 100% local + private (privacy pitch
intact); the *paid, opt-in* tier is where the server AND the LLM live, behind
explicit opt-in telemetry. Design the opt-in telemetry data model NOW so team
accounts aren't a rewrite later — but leave it as a *seam*, don't build it.

**WHAT STILL NEEDS VALIDATION (the only open monetization question):** does *our*
buyer (BYU TTO, real Claude Code teams) have the Uber-style per-dev-visibility pain
with **budget behind it**? Desk research can't close this. The interview job has
*narrowed*: we no longer need to discover what a paid tier could be (answered) —
`USER-INTERVIEW.md` now answers one sharp question: is the attribution/governance
pain real and budget-backed for this buyer. The BYU TTO pilot is the first signal.

**Provisional model:** free local core (open-source) + paid opt-in team tier at
~$19-40/seat (attribution dashboard + shared config/policy + team-level
recommendation intelligence; SSO/retention as enterprise add-ons). Do NOT build
the server/paid tier until interviews show a budget-backed team pain the free tier
doesn't already solve. Building the (fun, LLM-flavored) paid tier before a
confirmed buyer is the classic trap.

## Through-line
Win Claude Code narrow → one TS tool → timing signals on dynamic waste (not just
charts, not whole-session resets) → save money + do more within limits + keep
quality → free core, paid TEAM value → validate WTP with real users → keep
ownership clear. Depth over breadth.

---

### Open gaps
- **Budget-backed buyer pain (the big one)** — *narrowed*: we know what to charge
  for; the open question is whether our buyer (BYU TTO, real Claude Code teams) has
  the per-dev-visibility/governance pain with budget behind it. Real-user
  interviews (`USER-INTERVIEW.md`), not more research.
- **The server/local-first fork** — a deliberate decision with Nick before any
  paid build (see §6). Don't drift into it.
- **Quality-axis validation** — the missing experiment is continue vs trim-waste
  measured on output QUALITY, not whole-session token totals. (Report reinforces:
  optimize cost-per-SUCCESS, not tokens-per-session.)

### Sign-off
- [ ] Zach
- [ ] Nick
