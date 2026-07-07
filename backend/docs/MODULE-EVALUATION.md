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

## Decision log

### 2026-07-07 — trust review complete, no default enablement

**Decision:** pick **Headroom** as the first lab candidate, but keep it **off by
default** and do not install/register/run it in a real agent yet. Ponytail remains a
guidance candidate, not the first token-saver module.

Why:
- Headroom has the better integration fit for Mr Token's "module" idea: MCP tools,
  proxy/library modes, local-first reversible compression, published benchmark claims,
  and direct overlap with `offload`/tool-output pressure.
- Headroom is also the higher-risk candidate: a large Python/Rust package, optional
  model/runtime downloads, proxy modes that intercept provider traffic, memory/learning
  features that write local agent files, and update-check behavior. That is acceptable
  for a pinned sandbox evaluation, not for default enablement.
- Ponytail is lower technical risk but is mostly instruction/plugin guidance. Its
  savings are indirect (fewer steps/LOC/tokens), so it belongs in a later guidance A/B,
  not the first external token-saver measurement shim.

**Do not enable by default. Do not `wrap` Claude/Codex. Do not install `[all]` for
the first trial.** The next approved step should be a sandbox-only Headroom trial
with a pinned version and the narrowest useful extra (`headroom-ai[mcp]` or a local
checkout), update checks disabled where supported, and no memory/learning/output-shaper
features enabled unless separately approved.

Suggested first trial command shape, not yet run:

```bash
python3 -m venv /tmp/mrtoken-headroom-eval
/tmp/mrtoken-headroom-eval/bin/pip install 'headroom-ai[mcp]==0.29.0'
HEADROOM_UPDATE_CHECK=off /tmp/mrtoken-headroom-eval/bin/headroom doctor
```

Candidate registry shape after a successful sandbox install, still disabled/off by
policy until measured:

```bash
mrtoken-transcript modules --add headroom --kind mcp --command headroom --arg mcp \
  --note 'LAB ONLY: trust-reviewed 2026-07-07; not default-enabled'
mrtoken-transcript modules --disable headroom
```

Evidence sources checked on 2026-07-07:
- Headroom GitHub README: `https://github.com/headroomlabs-ai/headroom`
- Headroom PyPI metadata: `https://pypi.org/project/headroom-ai/`
- Headroom license/security/package metadata:
  `https://raw.githubusercontent.com/headroomlabs-ai/headroom/main/LICENSE`,
  `SECURITY.md`, `pyproject.toml`
- Ponytail GitHub README/package/license:
  `https://github.com/DietrichGebert/ponytail`,
  `package.json`, `LICENSE`

## Current assessment

### headroomlabs-ai/headroom
- *Verified claim surface:* compresses tool outputs/logs/RAG/files/history; exposes
  Python library, proxy, wrapper, and **MCP tools**; claims local-first reversible
  compression; README currently reports 15-20% fewer tokens for coding agents and
  larger reductions for structured/log workloads.
- **License / maturity:** Apache-2.0; PyPI package `headroom-ai` at 0.29.0 in the
  checked repo metadata; marked beta; Python >=3.10; Rust extension built with
  `maturin`.
- **Install surface:** `pip install "headroom-ai[all]"` is broad. The first trial
  should avoid `[all]` and use the smallest extra that exposes MCP. The npm package
  is SDK-only and does not provide the CLI.
- **Privacy / egress:** likely acceptable only in narrow local modes. The project
  says Headroom runs locally and data stays on-machine, but proxy/wrap modes forward
  compressed prompts to the normal LLM provider, optional assets may be fetched from
  `cdn.pyke.io` and Hugging Face, and `headroom learn` can write agent guidance files.
  Treat as **opt-in lab only** until verified in a sandbox.
- **Trust risks:** large dependency surface; optional ML/model downloads; local proxy
  should not be exposed publicly; request logs may contain sensitive information per
  its own security notes.
- **Fit:** strongest candidate for first measurement because it can be run as an MCP
  module and maps cleanly to Mr Token's savings/outcomes model.
- **Decision:** **selected for lab evaluation, not enabled.** First measured question:
  does Headroom reduce tool-output/context pressure versus Mr Token `offload` on our
  corpus without reducing task quality?

### DietrichGebert/ponytail
- *Verified claim surface:* plugin/rules/skills package for many agents; measured
  claims are LOC/tokens/cost/time deltas from agentic coding tasks, not direct
  tool-output compression.
- **License / package:** MIT; npm package `@dietrichgebert/ponytail` at 4.8.4 in the
  checked package metadata; includes `AGENTS.md`, hooks, skills, OpenCode plugin files,
  and uninstall script. A private `ponytail-mcp` package manifest exists in-repo for
  serving prompts/tools.
- **Install surface:** Claude/Codex plugin installs include Node.js lifecycle hooks.
  Instruction-only fallbacks exist by copying rules files, but plugin mode changes
  prompt/hook behavior across sessions.
- **Privacy / egress:** likely low egress risk because it is guidance/hooks rather
  than a proxy, but hooks still run local code every turn and must be reviewed before
  trust.
- **Fit:** useful as a guidance module, but it overlaps with `mr-context` and measures
  differently: steps, LOC, cost, and quality, not per-call token savings.
- **Decision:** **defer.** Revisit after Headroom's lab measurement or as a separate
  guidance A/B. Do not install plugin hooks as part of the Headroom evaluation.

## Next (the real 7.3, when greenlit)
Headroom is picked for the first lab measurement. Before it can move from candidate
to recommended module:

1. Run a sandbox install with the narrow MCP extra, no agent wrapping.
2. Record exact installed version, commands, network behavior, and files written.
3. Add the measurement shim that records module savings/outcomes under the module
   name, or run a one-off before/after harness and write the result here.
4. Decide `keep-off`, `opt-in`, or `drop` from measured savings at equal quality.
