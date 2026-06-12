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
put it. The paid layer is therefore NOT "charge for advice" but:
- **Team features** (shared usage/attribution across a team, governance, shared
  config recommendations, optional hosted sync) — the one thing a single local
  binary can't self-provide, and where research says budget actually exists.
- **Premium assistive actions** (LLM-polished handoff, log summarization) — opt-in.
**Hard line:** no auto-compaction, no silent rewriting, ever.

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

## 6. Monetization (research-informed 2026-06-05; still needs real-user validation)
A 104-agent monetization research pass found hard truths (full notes in memory /
the research output):
- **Every direct competitor is free, MIT, local-first, donation-only** (ccusage,
  CodeBurn, TokenTracker). Measurement + basic advice is free-tier territory.
- **Individual out-of-pocket WTP looks weak** — individuals have free substitutes.
  The plausible paid buyer is a **team / devex lead / eng-leadership** whose team
  loses shipping velocity to throttling and usage opacity.
- **Pricing gravity:** AI coding tools ~$20/mo individual, ~$200/mo power,
  **$19-40/seat team**; observability $39-79/mo or open-core. Free-tier→paid norm.
- **Savings-share pricing (ProsperOps) does NOT map** — flat-rate plans have no
  metered dollar to take a cut of. Rule it out.
- **Local-first helps trust, not monetization** (no usage hook, forkable). Best
  model = free local core + paid team add-ons (Obsidian Sync/Publish pattern).
- **Biggest risk:** WTP is UNPROVEN; desk research can't close it. Validate with
  real users via `USER-INTERVIEW.md` — the BYU TTO pilot is the first real signal.

**Provisional model:** free local core (open-source) + paid team tier at
~$19-40/seat (attribution, governance, shared config, optional sync) + opt-in
premium assist. Do NOT build the paid tier until interviews show a budget-backed
team pain the free tier doesn't already solve.

## Through-line
Win Claude Code narrow → one TS tool → timing signals on dynamic waste (not just
charts, not whole-session resets) → save money + do more within limits + keep
quality → free core, paid TEAM value → validate WTP with real users → keep
ownership clear. Depth over breadth.

---

### Open gaps
- **Willingness-to-pay (the big one)** — unproven; desk research is exhausted.
  Next step is real-user interviews (`USER-INTERVIEW.md`), not more research.
- **Quality-axis validation** — the missing experiment is continue vs trim-waste
  measured on output QUALITY, not whole-session token totals.
- **What the paid feature actually is** — interviews should surface which team
  feature (if any) carries past-spend behind it.

### Sign-off
- [ ] Zach
- [ ] Nick
