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

### 2026-07-07 — sandbox install inspection complete, no default enablement

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

**Sandbox result:** a pinned install of the narrow MCP extra succeeded under
`/tmp/mrtoken-headroom-eval` with no agent registration:

```bash
python3 -m venv /tmp/mrtoken-headroom-eval
/tmp/mrtoken-headroom-eval/bin/pip install 'headroom-ai[mcp]==0.30.0'
HEADROOM_UPDATE_CHECK=off /tmp/mrtoken-headroom-eval/bin/headroom doctor
```

Findings from the sandbox:
- `headroom-ai==0.30.0`; `headroom --version` reports `headroom, version 0.30.0`.
- Even `[mcp]` installs a broad dependency/runtime surface: `litellm`, `openai`,
  `huggingface-hub`, `tokenizers`, `mcp`, `uvicorn`, `ast-grep-cli`, and related
  HTTP/server packages.
- Venv size after install: about **349 MB**.
- `headroom --help` exposes high-impact commands: `wrap`, `init`, `install`,
  `proxy`, `learn`, `memory`, `update`, `dashboard`, `capture`, `tools`.
- `headroom mcp --help` confirms the MCP path is coupled to a local proxy for
  automatic compression: users route Claude/Codex traffic through
  `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL` or `headroom wrap`, and the MCP server
  retrieves compressed originals from the proxy.
- `headroom doctor --json` with no proxy running fails safely:
  proxy not reachable at `http://127.0.0.1:8787`; Claude/Codex not routed; shell env
  bypasses proxy; no savings recorded.
- Help/version/doctor checks with `HOME=/tmp/mrtoken-headroom-home` did not create
  files in that temp HOME.

**Updated conclusion:** Headroom is viable as a lab candidate, but the first real
measurement must be a sandbox/proxy harness, not a normal agent install. Do not run
`headroom wrap`, `headroom init`, `headroom install`, `headroom mcp install`, or route
real Claude/Codex through the proxy until the measurement harness is explicit and
reversible.

Candidate registry shape after a successful sandbox install, still disabled/off by
policy until measured:

```bash
mrtoken-transcript modules --add headroom --kind mcp --command headroom --arg mcp \
  --note 'LAB ONLY: trust-reviewed 2026-07-07; not default-enabled'
mrtoken-transcript modules --disable headroom
```

### 2026-07-08 — reversible measurement harness added and proxy probe run, no agent routing

**Decision:** add MR Token's lab harness, but keep Headroom off and unregistered in
real agents. The new command is:

```bash
mrtoken-transcript module-measure
```

What it can do:
- Compare a baseline text artifact to a compressed/optimized artifact:
  `module-measure --module headroom --before raw.txt --after compressed.txt`.
- Parse a Headroom proxy JSONL log containing `tokens_before` / `tokens_after`:
  `module-measure --module headroom --headroom-log headroom-proxy.jsonl`.
- Run a local-only Headroom proxy health/file-write probe:
  `module-measure --probe-headroom --headroom-bin /tmp/mrtoken-headroom-eval/bin/headroom`.
- Run a synthetic localhost traffic probe with no real provider or agent:
  `module-measure --synthetic-headroom-traffic --headroom-bin /tmp/mrtoken-headroom-proxy-eval/bin/headroom`.
- Write measured positive token deltas to `savings` and explicit quality outcomes
  to `outcomes` only when `--record` is passed. `quality=pass` plus positive token
  delta counts as helped; `quality=fail` counts as hurt; unknown quality does not
  create an outcome.

Safety boundary:
- The proxy probe uses an isolated temporary `HOME`, `XDG_DATA_HOME`, and `TMPDIR`.
- It sets `HEADROOM_UPDATE_CHECK=off`, `HEADROOM_TELEMETRY=off`,
  `HEADROOM_NO_SUBSCRIPTION_TRACKING=1`, and `HEADROOM_STATELESS=true`.
- It starts only `headroom proxy` bound to `127.0.0.1`, hits a local health
  endpoint, records files created under the sandbox, then stops the process.
- It does **not** set `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`, or launch Claude/Codex.
- It does **not** run `headroom wrap`, `headroom init`, `headroom install`, or
  `headroom mcp install`.
- The synthetic traffic probe runs non-stateless inside the same isolated sandbox
  because Headroom disables `--log-file` in stateless mode. It sets
  `HEADROOM_OFFLINE=1`, `HEADROOM_BINARIES_OFFLINE=1`, `HEADROOM_DISABLE_KOMPRESS=1`,
  `HEADROOM_CCR_BACKEND=memory`, `HEADROOM_TIKTOKEN_LOAD_TIMEOUT_SECONDS=0`, and
  routes `/v1/messages` to a fake localhost Anthropic endpoint.

Probe result:
- The earlier `headroom-ai[mcp]==0.30.0` sandbox cannot start proxy mode:
  it fails safely with `No module named 'fastapi'` and writes no files.
- A separate reversible `/tmp/mrtoken-headroom-proxy-eval` venv with
  `headroom-ai[proxy]==0.30.0` started proxy mode successfully under the harness.
- Local endpoint checked: `GET http://127.0.0.1:<ephemeral>/livez` -> `200`.
- Controlled env set by the harness:
  `HEADROOM_UPDATE_CHECK=off`, `HEADROOM_TELEMETRY=off`,
  `HEADROOM_NO_SUBSCRIPTION_TRACKING=1`, `HEADROOM_STATELESS=true`.
- No `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` was set, and no Claude/Codex process
  was launched. The proxy printed provider routes it *would* forward to if a client
  were routed through it, but the probe only hit `/livez`.
- Files written inside the temporary sandbox even with `--stateless`:
  `home/.headroom/logs/proxy.log` (3993 bytes) and
  `home/.headroom/subscription_state.json` (590 bytes). This is acceptable for a
  lab sandbox, but it means "stateless" is not literally zero filesystem writes.

Synthetic traffic result:
- Command:
  `module-measure --synthetic-headroom-traffic --headroom-bin /tmp/mrtoken-headroom-proxy-eval/bin/headroom --timeout 12 --json`.
- Result: `ok=true`; `GET /livez` returned `200`; one synthetic Anthropic-shaped
  request with a large `tool_result` reached the fake localhost upstream; no real
  Claude/Codex process or provider endpoint was used.
- Headroom JSONL parse: `rows_seen=1`, `rows_measured=1`,
  `input_tokens_original=13761`, `input_tokens_optimized=13761`, `tokens_saved=0`.
  This proves the MR Token measurement loop, but it does **not** prove Headroom
  savings because the safe probe disables Kompress and blocks binary downloads.
- Offline controls worked for bundled tools: `difft` and `scc` were skipped with
  `HEADROOM_BINARIES_OFFLINE=1` instead of being fetched.
- Files written in the non-stateless traffic sandbox:
  `headroom-proxy.jsonl`, `home/.headroom/logs/proxy.log`,
  `home/.headroom/proxy_savings.json`, `home/.headroom/subscription_state.json`,
  and a sandbox-local `tiktoken-cache/...` file. Keep treating traffic probes as
  sandbox-only; do not infer "no filesystem writes."

Remaining evidence gate:
1. Decide whether to run a less-constrained compression probe (e.g. with Kompress
   or pre-fetched helper binaries) to test actual savings; that is separate from
   the safe synthetic loop.
2. Record savings only with an explicit equal-quality verdict.
3. Decide keep-off / opt-in / drop. Any real-agent routing still needs separate
   Zach approval.

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
- **License / maturity:** Apache-2.0; PyPI package `headroom-ai` at 0.30.0 in the
  checked repo metadata/sandbox install; marked beta; Python >=3.10; Rust extension built with
  `maturin`.
- **Install surface:** `pip install "headroom-ai[mcp]"` is already broad. It brings
  proxy/server/client dependencies and installs additional commands such as
  `litellm`, `litellm-proxy`, `huggingface-cli`, `mcp`, `uvicorn`, `ast-grep`, and
  `sg`. The npm package is SDK-only and does not provide the CLI.
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

1. Build a reversible sandbox/proxy measurement harness; no real-agent wrapping.
2. Verify exact network behavior under proxy mode and what Headroom stores locally.
3. Add the measurement shim that records module savings/outcomes under the module
   name, or run a one-off before/after harness and write the result here.
4. Decide `keep-off`, `opt-in`, or `drop` from measured savings at equal quality.
