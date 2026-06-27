# External module evaluation (ROADMAP 7.3 groundwork)

Before any external token-saver module ships **on by default**, it passes this review.
The registry (7.2, `modules.py`) lets a user *declare/toggle* a module; this is the
**⚑ gate** for trusting one. Nothing here vendors or runs external code — it's the
checklist + an initial (public-info) assessment with explicit VERIFY items.

## Criteria (all must pass to enable by default)

1. **Real savings, measured.** The claimed token reduction holds in a before/after on
   *our* corpus — via `savings` (realized) + the ROI experiment harness
   (`backend/experiments/`). Marketing % ≠ proof.
2. **Equal quality.** Answers don't degrade. Gated on the experiment's completion oracle
   — a cheaper run that answers worse is a regression, and `measure-don't-degrade`
   (6.7) must be able to auto-disable it if it hurts in situ.
3. **Privacy / data flow (potentially disqualifying).** Mr Token's invariant is
   **no network egress by default**. A module that sends prompts/outputs off-machine,
   proxies through a cloud, or phones home is **disqualified** unless it runs fully
   local AND the user explicitly opts in. Determine exactly what leaves the machine.
4. **Trust / supply chain.** License, maintainership, install surface (pip/npm/MCP),
   how much code runs and with what permissions, pinned versions. Prefer an MCP server
   we launch over a library we import into our process.
5. **Integration fit.** How it's invoked (ideally an MCP server via the 7.2 registry),
   how we record its savings (the measurement shim), how it's toggled/disabled, and what
   happens if it crashes (must fail safe — never block the agent).

## Decision rule
Enable a module **on by default** only if it shows **measured savings at equal quality**,
is **local / no-egress (or explicitly consented)**, and passes the **trust review**.
Otherwise: leave it registered-but-off (opt-in) or drop it.

## Initial assessment (public info only — all internals are VERIFY)

### headroomlabs-ai/headroom
- *Claim:* compress tool outputs/logs/files/RAG before the LLM; 60–95% fewer tokens,
  "same answers"; library, proxy, **MCP server**; 51k★.
- **Fit:** strong — it's a stronger `offload`, and the MCP-server form drops into the 7.2
  registry cleanly (launch it, both agents use it).
- **VERIFY:** ① does the MCP/library run **fully local** with no egress? (criterion 3 — the
  big one). ② "same answers" — confirm with our equal-quality experiment, not the README.
  ③ license + install surface. ④ overlap with our `offload` — do we adopt it *instead of*
  offload, or for the cases offload can't (RAG/logs)?

### DietrichGebert/ponytail
- *Claim:* makes the agent "think like the laziest senior dev — the best code is the code
  you never wrote" (do-less guidance).
- **Fit:** it's a **guidance module** (kind=`guidance`), closer to our `mr-context` manual
  than a tool. Savings are indirect (fewer steps) → measure via step/token deltas, not a
  per-call figure.
- **VERIFY:** ① what form is it (prompt/skill/config)? ② does it conflict with our manual?
  ③ measurable effect on steps/tokens at equal quality?

## Next (the real 7.3, when greenlit)
Pick **one** (headroom is the stronger candidate), do the VERIFY items, register it via 7.2,
run the before/after, and decide keep-on / keep-off / drop on the evidence.
