# MR Token — Product Brief

*Status: v2 vision (2026-06-25). After ~8 releases of dogfooding (v0.4.1→v0.4.8) the
measurement half is solid but the product wasn't yet indispensable — it observed waste
but didn't change behavior in the moment. This brief recommits to the original promise
("the one thing to do **right now**" + "keep the agent sharp") by completing the loop.
Earlier framing + research: this file's git history and DECISIONS.md.*

## One-liner
**Mr Token is the agent's efficiency manual + toolbox + report card** — it keeps a coding
agent from running out of context on junk, by **teaching** it how to avoid waste, **equipping**
it with the tools to fix waste in the moment, and **grading** whether it actually got better.
Local-first, metadata-by-default, cheap to leave on. The cheap detection core runs with **no
LLM in the loop**; acting is an opt-in layer on top.

## The shift (v2) — what's the same, what evolved
The measurement was never the product; it was the foundation. The product is **closing the
loop in the moment**. Three honest changes from v1:

1. **Audience can be the agent, not just the human.** The human isn't in the loop at
   token-decision time — the agent is. So Mr Token aims its guidance at *the agent* (injected
   manual pages + agent-callable tools) by default, and at the *human* when you want it to.
   Configurable; one default, flexible underneath.
2. **From report to manual + toolbox.** "Diagnose → teach → equip → grade" is just the original
   **Monitor → Detect → Recommend → Assist** ladder said plainly. The toolbox (`handoff`,
   `offload`, `compact`, `summarize`) *is* the Assist rung — now agent-callable.
3. **It can act (consented).** v1's non-goal was "no autonomous context reducer; never silently
   rewrite context." We relax the *letter* (it may act) while keeping the *spirit*: **never
   silently or unconsented — every action is toggleable, reversible, and measured.**

## Problem
The waste that matters is **dynamic**: huge tool/log dumps, re-reading the same files, retry
loops, runaway step counts — non-cacheable context that snowballs (Stanford: same task up to
**30×** by steps/re-reads). The felt pain: **you run out of context** mid-task because it got
filled with junk — forcing a compaction, losing coherence, or burning your rate-limit window.
Three flavors of damage by user: **money** (metered), **rate limit + context window** (flat-rate),
**output quality** (context rot). It lives at the **session/workflow** level, so per-call
dashboards miss it.

## What it does — diagnose → teach → equip → grade
1. **Diagnose (Monitor + Detect).** Reconstruct `trace → model_call / tool_call`, exact tokens /
   cache / cost; deterministic rules flag the waste (huge output, re-read loop, repeated context,
   retry loop, low cache, step runaway, context rot). No AI. This is the **report card**.
2. **Teach (the manual).** At the right moment, inject guidance *written for the agent to act on*
   ("ctx 82%, ~40k is re-read junk — offload it or hand off"), plus a standing skill it can consult.
3. **Equip (the toolbox).** Ship the agent the tools to fix it: `offload` (big output → disk +
   summary), `handoff` (fresh session), `compact`, `summarize`. The agent has hands, not just a warning.
4. **Grade (feedback).** Did the agent get better? `validate` / `feedback` / `explain` track whether
   an action helped — and **auto-disable any tool whose measured outcome trends negative.**

### The intervention engine ("right now")
- **Proc point = each turn boundary** (hooks fire there; you reset *between* turns, not mid-turn).
- **Fires when both:** *pressure* (context filling toward the wall — predictive turns-to-full) **and**
  *reclaimability* (it's junk a tool can fix). Pressure alone = a quiet heads-up; pressure + junk = act.
- **Graduated autonomy, per tool, configurable:** **L1 Tell** → **L2 Ask** (approve, with an AFK
  timeout that escalates on inaction) → **L3 Do** (auto-remediate, logged, reversible). L3 only after
  the report card proves that action helps.

## Audience & customization (sharp default, flexible underneath)
- **Hero default:** agent-facing **context-rescue** — "don't run out of context on junk" — working
  out of the box. This is what must be indispensable.
- **Flexible layer:** point it at the human instead; tune autonomy levels per tool; turn any tweak
  off. People will use it in ways we don't predict — *that's fine, on top of one sharp default*, not
  instead of one.
- Users: **agent power users** (primary) → agent/tool builders → teams/cost owners (later).

## Cost model
**Tokens are ground truth.** Dollars are a computed overlay (`tokens × versioned price table`),
labeled **"estimated API-equivalent cost"** for subscription use — not a real bill.

## Guardrails (hard constraints)
- **Every tool/tweak individually toggleable + a global kill switch.** Nothing auto-acts unless
  opted to that level.
- **Measured so it can't silently degrade.** Every action logs before/after (tokens, context %, and
  did the task still succeed); a tool trending negative auto-disables and says so.
- **Privacy: metadata-only by default** — counts, hashes, sizes, tool names, timings, cost. Content
  is read to derive metadata then discarded; full-content capture is explicit, local, per-session,
  secret-scanned. **No network egress by default.**

## Non-goals
- **No silent or unconsented action** — it may act, but only toggled-on, reversible, and logged.
  (Revised from v1's blanket "no autonomous reducer.")
- No AI call in the cheap detection core (the always-on layer stays deterministic).
- No marketplace; no all-providers-before-proof.
- No claim of exact dollar cost for subscription tools.

## Open questions to resolve next
- **Toolbox surface:** MCP tools vs skills vs both (the agent needs to *call* the toolbox).
- **Approval/timeout host:** hook-driven (works today) vs a live watcher daemon (richer UX).
- **AFK default action** when unanswered: handoff, compact, or warn-only.
- **Does acting actually help, at equal quality?** The gated ROI experiment (`backend/experiments/`)
  is how we prove the toolbox earns L3 — before any tool defaults to auto.
