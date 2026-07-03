---
name: mr-context
description: The context-efficiency manual — how to avoid running out of context on junk, and which Mr Token tool to reach for. Use when context is getting heavy, a tool/file output is large, you're re-reading files, a session is deep, or you see a Mr Token nudge about context pressure. Pairs with the Mr Token MCP tools (offload / handoff / compact).
---

# MR Token: the context-efficiency manual

Goal: **don't run out of context on junk.** The context window fills with non-cacheable
bulk — huge tool/file outputs, re-reads, repeated context — long before the *real* work
needs it. This is how to spot it and what to do, using the Mr Token toolbox (the `offload`,
`handoff`, `compact`, and `confirm_disposable` MCP tools, if registered — see `docs/MCP.md`).

## The failure modes (what fills context with junk)
- **Huge tool/file outputs** — one `Read` of a big file or a noisy command dumps 10k+ tokens
  that then ride along on *every* later turn.
- **Re-reads** — reading the same file/target more than once re-pays its tokens each time.
- **Repeated context** — the same large block restated across turns.
- **Deep sessions** — many turns deep, the carried context dwarfs the active task; quality
  degrades (context rot) and every turn is expensive.

## What to do — pick the smallest fix
1. **Big output coming?** Don't read it whole — **`offload`** it: the full content goes to disk,
   you keep a compact summary + a stash path to grep later. (Best *before* a large read.)
2. **One huge thing already in context?** `offload` the specific content, then continue.
3. **Context heavy but the task's not done and you want to stay here?** **`compact`** (run your
   host's compaction, e.g. `/compact`).
4. **Deep into a long/multi-task session?** **`handoff`** — generate a compact handoff and start a
   FRESH session. Usually cheaper than compacting once you're truly deep.
5. **Nudge asked you to confirm a drop?** When Mr Token says some big context *looks* droppable and
   asks, it can't actually tell whether you'll re-open those refs — only you can. **First check what
   the remaining work needs.** If that context is genuinely done with, call **`confirm_disposable`**
   — that authorizes an escalating reset (`handoff`/`compact`). If you'll still need those refs,
   `offload` instead. Never confirm reflexively: a wrong "yes" drops context you then re-read (the
   +20% load-bearing loss the experiment found).

## Habits that prevent it (cheaper than any fix)
- Read **targeted ranges**, not whole files; search/grep instead of dumping.
- Read once, **keep the result** — don't re-read the same target.
- Send large command output to a file and read a summary, not the raw stream.
- Watch the Mr Token HUD (`ctx %`, turns-to-full); act on the nudge *before* you hit the wall.

## Rule of thumb
Offload the **junk**, handoff the **session**, compact the **middle ground**. When unsure and
context is climbing fast, `offload` the biggest thing and keep going.
