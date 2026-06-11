# MR Token — Product Brief

*Status: discovery → MVP build. Last updated 2026-06-05 (positioning revised after two research passes — see DECISIONS.md section 4-5).*

## One-liner
A local-first tool that watches your AI coding agent for the waste that actually costs you — bloated tool outputs, re-read loops, context rot — and tells you the one thing to do about it right now. So you **spend less, do more within your rate limits, and keep the agent sharp.** Cheap to leave on always; useful day one with **no LLM in the loop**.

## Problem (sharpened by research)
The waste that matters is **dynamic**, not "repeated context" (prompt caching makes re-sending the static prefix cheap). The real drivers are huge tool/log dumps, re-reading the same files, retry loops, and runaway step counts — non-cacheable context that snowballs. Stanford's agent-spend study: the same task can cost up to **30x** more depending on how many steps/re-reads the agent took. That snowball does three kinds of damage, depending on the user: **costs money** (metered/API), **eats your rate limit and context window** (flat-rate plans — vendor-documented), and **degrades output quality** (context rot — research-backed, every plan). Users can't see it, and per-call dashboards miss it because it lives at the **session/workflow** level.

## What it does (in order of build)
1. **Monitor** — reconstruct a task as `trace → model_call / tool_call → event`, with token counts, cache stats, sizes, timings, cost estimate. No AI.
2. **Detect** — deterministic rules flag waste (repeated context, huge tool output, retry loops, low cache use, context-block domination, reasoning ratio outliers).
3. **Recommend** — plain-text workflow advice: continue / compact / fresh handoff / spawn subagent / lower or raise reasoning / re-plan / offload logs.
4. **Assist (opt-in, later)** — LLM generates handoffs, summarizes logs, diagnoses cost. Only when expected savings justify the spend.

## Cost model
**Tokens are the ground-truth unit.** Dollars are a computed overlay: `tokens × versioned per-model price table`, stored per call with the price-table version. For Claude Code subscription use, the dollar figure is labeled **"estimated API-equivalent cost"** — not a real bill.

## Users (MVP targets one)
- **Agent power users** (Claude Code daily drivers) — *primary.* "Why was that task expensive, and what do I do right now?"
- Agent/tool builders (custom Anthropic/OpenAI agents) — later, via SDK wrapper.
- Teams / cost owners — later.

## MVP scope (proves the concept)
- **Source:** Claude Code only, via **transcript JSONL** (`~/.claude/projects/<path>/<session>.jsonl`) — verified to contain full token usage, cache stats, model, tools, retries (`requestId`/`parentUuid`), and subagents (`isSidechain`). No OTEL/hooks required for v1.
- **Stack:** Python, SQLite ledger, pure-function rule engine, CLI report (`mrtoken-transcript report <session>`). No dashboard yet.
- **Rules (3 high-signal):** repeated-context (block hashing), huge-tool-output, retry-loop.
- **One trusted recommendation:** "fresh handoff recommended" with a token-based justification.
- **Validation:** dogfood on Zach's own real sessions (ground truth known) for ~2 weeks before adding a 2nd integration or any dashboard.

## Non-goals (explicitly NOT first)
- No autonomous context reducer; never silently delete/rewrite context.
- No marketplace; no all-providers-before-proof.
- No AI call after every agent call.
- No dashboard before the data model is proven.
- No claim of exact dollar cost for subscription tools.

## Privacy stance (hard constraint, not a setting)
- **Default = metadata only**: token counts, hashes, sizes, types, tool names, timings, cost estimates.
- Transcript content is read to *derive* metadata, then discarded — reading raw content counts as content-capture mode.
- Full-content capture is explicit, local, per-session opt-in, with **secret scanning** before anything is persisted.
- No network egress by default.

## Open questions to resolve via dogfooding
- Are the handoff/subagent heuristics actually right when they fire? (Currently hypotheses.)
- Reasoning over/underuse needs fuzzy task classification — keep as a soft hint only.
- OTEL 60s metric interval vs transcript-on-write latency — does "real-time" advice need OTEL traces (beta, ~5s)?
