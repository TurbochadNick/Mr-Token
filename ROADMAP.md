# Mr Token — Roadmap (loop-able task plan)

*Living plan. Ordered so each task is small, self-contained, and verifiable — built to be
worked one-at-a-time, including via Claude Code's `/loop`. Last updated 2026-06-23.*

Purpose recap (see `backend/docs/BRIEF.md` for the full version): a **local-first
observability tool for AI coding agents** that catches the *dynamic* waste that actually
costs you — huge tool dumps, re-read loops, retry loops, runaway steps — and tells you the
**one thing to do right now**. No LLM in the core loop. Metadata-only by default.
**Expansion is gated on proving the heuristics by dogfooding**, so validation comes before
new product surface.

> Ownership/IP planning is intentionally **out of scope here** (tracked separately in
> `OWNERSHIP_GATE.md`). This file is engineering + product only.

---

## How to run this with `/loop`

Each task is a checkbox with a self-contained spec and an **Acceptance** check. To work the
plan autonomously:

```
/loop implement the next unchecked task in ROADMAP.md
```

Per iteration, the agent should:
1. Read this file; pick the **first** `- [ ]` task (top-to-bottom = priority order).
2. State the root cause / approach in one paragraph before editing (per repo working rules).
3. Implement it, staying in scope — one task per iteration, no drive-by refactors.
4. Run the task's **Acceptance** check; the backend suite must stay green:
   `cd backend && python3 -m unittest tests.test_backend`
5. Flip the box to `- [x]`, add a one-line `→ done:` note with the commit hash.
6. Commit on a branch (never commit straight to `main`); end the message with the repo's
   `Co-Authored-By` trailer. Open/My PRs use the `zoozorocks01` gh account (private repo).
7. If blocked or a second root cause appears, **stop and surface it** — don't fold it in.

Stop the loop when the next unchecked task is in a phase you haven't green-lit, or when a
task needs a human decision flagged with **⚑ decision**.

---

## Phase 1 — Honest data *(do first; unblocks all validation)*

- [x] **1.1 — Drop / flag near-empty sessions (regression from the global Stop hook)**
  → done: commit `47f1b7b` on branch `fix/empty-session-noise` (stacked on `fix/global-stop-hook`). 45 tests green.
  - **Why:** the global Stop hook now fires on every trivial desktop session, writing a
    noise row per 11–17-token stub. Theron saw 35 of 38 "sessions" were empty stubs from a
    single day, corrupting fleet stats and any validation number derived from them.
  - **Files:** `backend/mrtoken/ingest.py` (skip at ingest), `backend/mrtoken/hooks/on_stop.py`
    (don't print a HUD/summary for skipped), `backend/mrtoken/fleet.py` + the
    `session_summary` view (exclude low-activity from headline counts), `backend/mrtoken/schema.sql`.
  - **Spec:**
    - Define a tunable module-level constant: `MIN_ACTIVITY = {"model_calls": 2}` — Zach's
      call: a substantive session is **at least 2 model calls** (≈2 request/response rounds).
      Anything with fewer is low-activity.
    - **Do not persist** a trace with **zero** model_calls (pure noise, no possible signal).
    - For sessions that ingest but fall below the floor, mark them **low-activity** (a derived
      flag — column or view predicate, your call) and **exclude them from fleet/session
      counts and `report` headlines**, while keeping the rows queryable.
    - Make the threshold a single named constant so it can be tuned once volume exists.
  - **Acceptance:** new unit test — ingest a fabricated zero-model-call transcript → no trace
    row; ingest a sub-floor transcript → row exists but `fleet` session count excludes it.
    Full suite green.

- [x] **1.2 — `ingest --backfill` over local transcript history**
  → done: commit `e88267e` on `fix/empty-session-noise`. Real run: 153 sessions / 93 recs; idempotent. 46 tests green.
  - **Why:** capture is going-forward only (backfill was skipped), so real post-fix volume is
    thin. Backfill builds a real corpus *today* instead of waiting weeks — the single highest-
    leverage step for validation.
  - **Files:** `backend/mrtoken/cli.py` (add `--backfill` to `ingest`), `backend/mrtoken/ingest.py`.
  - **Spec:** walk `~/.claude/projects/*/*.jsonl` (+ subagent transcripts under
    `<session>/subagents/`), ingest each idempotently (re-ingest must not duplicate rows —
    `trace.session_id` is UNIQUE; upsert/replace), honoring the 1.1 low-activity rule. Print a
    summary (sessions seen / ingested / skipped). Respect `MRTOKEN_DB`.
  - **Acceptance:** running it twice over a temp projects dir yields identical row counts
    (idempotent); a known transcript produces the same trace as a single-file ingest.

- [x] **1.3 — Validation corpus intake for shared exports**
  → done: commit `37834a3` on `fix/empty-session-noise`. New `corpus` command; 47 tests green.
  - **Why:** beta testers (Theron) can send redacted `export` JSON; we need a place to land it
    and compare against our own fleet without re-deriving by hand.
  - **Files:** new `backend/mrtoken/` helper or extend `validate.py`; a `reports/` dir (gitignored).
  - **Spec:** accept one or more `mrtoken.session_summary.v1` JSON files and produce a combined
    rule-precision / cost / cache summary across them. Metadata-only; never store raw content.
  - **Acceptance:** feeding a sample v1 export prints aggregate stats without error; a malformed
    or empty file is reported, not crashed.

## Phase 2 — Proof *(the brief's gate; do before new rules ship as trusted)*

- [x] **2.1 — ROI before/after measurement**
  - **Why:** `roi` currently *estimates* the lever (context carry). The real proof is "did
    acting on a recommendation actually reduce tokens on the next comparable session?"
  - **Files:** `backend/mrtoken/roi.py`, `backend/docs/ROI-EXPERIMENT.md`.
  - **Spec:** define a before/after comparison on real sessions (e.g. sessions where a
    `fresh_handoff` fired vs. the continuation), report observed token delta with caveats about
    confounds. Output is evidence, not a guarantee.
  - **Acceptance:** runs against the backfilled corpus and produces a delta with an explicit
    n and confound note. **⚑ decision:** confirm the comparison design before trusting outputs.
  → done: commit `ba0e59c`. Zach chose **C+B**. `roi --measure`; C projects ~$40.70 over 20 fired
    sessions; B degenerate on current data (needs cross-session linkage — see backlog). 48 tests green.

- [x] **2.2 — Rule calibration at volume**
  → done: commit `381649b`. Found+fixed a validate corroboration bug (huge_tool_output was
    all-moot → really 80%); no threshold changes warranted. Record in `docs/RULE-CALIBRATION.md`. 49 tests green.
  - **Why:** `validate` proxies look strong (huge_tool_output 91%, retry_loop 100%,
    fresh_handoff 94%, low_cache 100%) but several are low-n. Re-run after backfill, tune.
  - **Files:** `backend/mrtoken/validate.py`, `backend/mrtoken/rules.py`.
  - **Spec:** re-run `validate` on the larger corpus; for any rule whose precision proxy drops
    below ~85%, adjust its threshold in `rules.py` and document the change. Don't weaken a rule
    just to raise the number — if it's genuinely noisy, say so.
  - **Acceptance:** `validate` output recorded before/after; any threshold change has a one-line
    rationale in the rule's docstring.

## Phase 3 — Product *(unlock as rules prove out)*

- [x] **3.1 — New rule: step-count / runaway-loop**
  → done: commit `28e2444` on `fix/empty-session-noise`. `step_runaway` rule; corpus: 24 fires / 92% proxy. 50 tests green.
  - **Files:** `backend/mrtoken/rules.py`, tests. **Spec:** flag sessions whose model_call count
    per task is a clear outlier (the Stanford "30× by steps" failure mode). **Acceptance:**
    fires on a fabricated runaway trace, silent on a normal one; added to `validate`.

- [x] **3.2 — Surface subagent ROI in reports**
  → done: commit `03f258a`. Net-tokens-vs-inline per subagent (NET column + report one-liner); real corpus reads a WebFetch-isolating subagent at +21,538 saved. 51 tests green.
  - **Files:** `backend/mrtoken/subagents.py`, `report.py`. **Spec:** for sessions with
    sidechains, show whether the subagent saved or cost net tokens vs. inline. **Acceptance:**
    a session with a known-good subagent reads as positive ROI; a thrashing one reads negative.

- [x] **3.3 — Context-rot / degradation hint** *(soft signal only)*
  → done: commit `a491fb5` on `feat/phase3-product`. `context_rot` info-only rule; corpus: 18 fires, all info. 52 tests green.
  - **Files:** `backend/mrtoken/rules.py`. **Spec:** a *soft* hint when context grows large with
    falling cache efficiency / rising re-reads (quality risk, not a hard rule). Keep it a hint,
    per the brief. **Acceptance:** fires as a low-severity hint only; never high.

- [x] **3.4 — Cost-gated Assist auto-suggestion (opt-in LLM)**
  → done: commit `6cf8040`. ⚑ decision: Zach's recommended default taken — opt-in OFF (MRTOKEN_ASSIST),
    5× ratio (both tunable). Corpus: fires on 11/85 sessions. 53 tests green.
  - **Why:** `/mr-handoff` and `/mr-why` already do in-session LLM assist; the unbuilt piece is
    auto-suggesting an LLM action **only when expected token savings justify the spend**.
  - **Files:** `backend/mrtoken/` (new), skills under `backend/skills/`. **Spec:** opt-in,
    metadata-respecting; suggest (don't auto-run) when projected savings > a multiple of the
    assist's own cost. **Acceptance:** with assist off (default), behavior is unchanged; with it
    on, a high-waste session yields a suggestion and a low-waste one does not. **⚑ decision:**
    confirm the savings-vs-spend ratio before enabling by default.

- [x] **3.5 — Codex transcript ingestion (2nd agent)** *(gated: only after Phase 2 passes for Claude Code)*
  → done: commit `523269e` on `feat/phase3-product`. `ingest_codex.py` adapter (source='codex'), auto-routed.
    Verified on a real rollout: 292 calls / 366 tools / 3 recs. 54 tests green. Codex-dir backfill → backlog.
  - **Files:** `backend/mrtoken/ingest.py` (source adapter), `schema.sql` (`source` already
    generic). **Spec:** parse Codex session logs into the same `trace → model_call/tool_call`
    model; reuse the rule engine. **Acceptance:** a sample Codex session ingests and reports
    with the existing rules; Claude Code path unaffected.

## Phase 4 — GTM / hardening *(parallelizable; first-run reliability is the real bottleneck)*

- [x] **4.1 — Install smoke test for the desktop-app path** *(regression guard)*
  → done: commit `5f8387d` on `feat/phase4-hardening`. Drives on_stop from an arbitrary cwd; asserts cwd-resolved DB ingest. 55 tests green.
  - **Why:** the global-Stop-hook bug + the empty-session noise both surfaced from real installs;
    lock the fixed behavior so it can't silently regress.
  - **Files:** `backend/tests/test_backend.py`. **Spec:** assert `init` registers the Stop hook
    globally, migrates a legacy project-local hook, and that a simulated Stop from an arbitrary
    cwd ingests into the cwd-resolved DB. **Acceptance:** test added and green.

- [x] **4.2 — Release discipline: tag check in `doctor`/`update`**
  → done: commit `53221f1` on `feat/phase4-hardening`. `release_tag_warning` in `status`; caught + fixed a
    real 0.4.4 pyproject/`__init__` version drift. 56 tests green.
  - **Why:** we shipped `0.4.4` in `pyproject.toml` but the update-nudge keys off git tags, so
    an untagged bump reaches no one. Make the gap visible.
  - **Files:** `backend/mrtoken/update_check.py`, `doctor`/`status` surface. **Spec:** warn when
    the installed/declared version is ahead of the latest git tag ("release not tagged"). Don't
    auto-tag. **Acceptance:** with version > latest tag, the warning shows; when equal, quiet.

- [x] **4.3 — Positioning: rate-limit-first copy**
  → done: commit `97e6794` on `feat/phase4-hardening`. Backend copy (fresh_handoff nudge + BRIEF one-liner)
    leads with limits/quality; HUD already did. README left to Nick with a suggested line (in commit msg). 56 tests green.
  - **Why:** most users are flat-rate and hitting plan caps; "do more within your limits" lands
    harder than "save money." **Files:** `README.md`, HUD/nudge copy. **Spec:** lead with the
    rate-limit + quality angle, keep the cost angle secondary. **Acceptance:** README one-liner
    and at least one nudge string updated; no behavior change.

---

## Phase 5 — Prove · Show · Grow *(next; spans lanes — read the notes)*

### A — Prove it (ROI experiment → a causal number) *(backend mine; live runs SPEND BUDGET)*
The harness exists (`backend/experiments/`, continue+handoff arms live, oracle+recorder working).
Pilots 1–2 were inconclusive because the fixtures didn't reliably bloat past the 100k reset point
and used a turn-count proxy. Pilot 3 fixes exactly that.
- [ ] **5A.1 Reliably-bloating fixture** — a task whose seed forces the agent past ~100k input-side
  tokens before it can finish (large multi-file repo / forced reads). Pilot once to confirm it crosses
  the threshold. *(build only; ~1 cheap confirm run)*
- [ ] **5A.2 Token-threshold reset** — replace the turn-count proxy with a reset fired when input-side
  context crosses 100k, via transcript-watching (reuse `watch`'s tracking — avoids needing the Agent SDK).
- [ ] **5A.3 Wire the `compact` arm** (currently deferred in `drive_agent`).
- [ ] **5A.4 Run the matrix** — continue/compact/handoff × pilot-3 × K=5–10, interleaved. **⚑ decision/SPEND:**
  needs explicit budget greenlight (doc estimates a few M tokens / tens of $). Hard budget cap in the harness.
- [ ] **5A.5 Analyze + record** — apply the pre-registered rule (≥5% signal, ≥10–15% win vs BOTH arms at
  equal completion), write the result into `docs/ROI-EXPERIMENT.md`.

### B — Show it (dashboard — Nick's TS/web lane) *(I provide the contract, do NOT build)*
- [ ] **5B.1 Data-surface spec for Nick** — `session_summary.v1` + `session_detail.v1` + `--since`, with the
  estimated↔actual join and example queries. (backend doc — in lane)
- [ ] **5B.2 Coordination note to Nick** — what's ready + his two open questions now answered (draft; Zach sends).

### C — Grow it (pilots / GTM) *(materials in lane; outreach is Zach's)*
- [ ] **5C.1 Pilot one-pager / onboarding** — from `INTERVIEW-KIT.md` + the v0.4.5 capabilities (draft).
- [ ] **5C.2 BYU TTO pilot framing / weekly report** — Zach-driven; I can draft.

### D — Internal feedback & observability *(backend mine; ~zero budget; do BEFORE 5A.4)*
We've validated Mr Token ad hoc (dogfood + the `validate` *proxy*). This adds a continuous internal loop
to see *why* a signal fired and whether it was actually *right* — the cheap, ongoing cousin of 5A.
- [x] **5D.1 Explain-on-signal** — `explain <session>` decodes each fired rec's `evidence_json` into readable
  "what triggered it" lines. Done (v0.4.6); dogfood: explains a 597-call session's signals incl. 36 offenders.
- [x] **5D.2 Feedback capture** — `feedback <session> <rule> right|wrong|unsure [--note]` + `feedback --summary`
  (new `feedback` table → labelled precision). Done (v0.4.6).
- [x] **5D.3 Golden regression** — whole-session fixtures + expected fired-signal sets; `test_golden_session_signals`
  flags drift. Done (v0.4.6).

**Decisions needed:** (1) 5A.4 spends budget — greenlight the full matrix, or build 5A.1–5A.3 + one smoke-run
then pause for explicit go? (2) 5B.2 — draft the Nick note now? Recommended path: **5D first** (zero budget,
continuous proof), then 5A.1–5A.3, gate 5A.4 on budget; 5B.1 + 5C.1 docs in parallel.

## Phase 6 — The intervention engine *(the v2 vision; see `backend/docs/BRIEF.md`)*

Goal: stop the agent running out of context on junk, by **teaching** it (the manual),
**equipping** it (the toolbox), and **acting in the moment** (the proc engine) — consented,
toggleable, measured. **Cross-cutting requirements for every task:** works for **both Claude
Code and Codex**; every tool/tweak individually toggleable; nothing auto-acts (L1/L2 only)
until 6.7's measurement proves it helps. **Locked defaults** (Zach): toolbox = MCP tools +
a manual skill; approval = hook-driven first; AFK default = warn-only.

- [x] **6.1 Toolbox foundation — MCP server + `mr_offload`**
  → done: commit `3025bcb` on `feat/mcp-offload`. Zero-dep MCP stdio server (`mrtoken-transcript mcp`)
    exposing `offload`; works for Claude + Codex (both speak MCP); `docs/MCP.md` registration. 64 tests
    green, verified over real stdio. Live in-agent confirm = register + call in a session.
- [x] **6.2 More tools — `mr_handoff`, `mr_compact`**
  → done: commit `d5a5da4`. Toolbox registry; `handoff` (real), `compact` (advisory — host op), per-tool
    toggle via MRTOKEN_TOOLS_OFF. 65 tests green; stdio lists offload/handoff/compact. *(Note: compact is
    advisory because compaction is a host action an MCP server can't execute.)*
- [x] **6.3 The manual — a context-efficiency skill** the agent consults (the "teach" half)
  → done: commit `689bc3c`. Bundled `mr-context` skill; `init` installs skills to both ~/.claude/skills
    and ~/.codex/skills. 66 tests green.
- [x] **6.4 Proc engine — turn-boundary trigger**
  → done: commit `fc1f602`. Pure agent-agnostic `evaluate()` (pressure ∧ reclaimable-junk → tool nudge),
    debounced; wired LIVE into Claude's UserPromptSubmit. 68 tests green. **Codex caveat:** engine is shared,
    but Codex live-pressure needs a rollout-based ctx tracker (model_context_window + running input) — next
    increment (added to backlog), not faked.
- [x] **6.5 Config + kill switch**
  → done: commit `4a8fe01`. `policy.py` (config + env), proc engine gates on `autonomy()`, default
    warn-only; `mrtoken-transcript config` to view/set; global kill switch. 69 tests green.
- [ ] **6.6 L2 Ask + AFK escalation** — hook-driven approval (reply = approve; AFK = next-turn
  escalation per config). **Acceptance:** ask shown; inaction escalates to the configured action (or warn).
- [ ] **6.7 Measure-don't-degrade** — every tool action logs before/after (tokens, ctx %, task still
  succeeded?); a tool whose outcome trends negative **auto-disables and says so**. Builds on
  `feedback`/`explain`. **Acceptance:** a fabricated "made it worse" history auto-disables that tool.
- [ ] **6.8 L3 Do (per tool)** — enable auto-act only for tools 6.7 (and the gated experiment) prove
  help, at equal quality. **⚑ decision per tool** before it defaults to auto.

## Shipped after the roadmap (v0.4.5–0.4.7)
- [x] **Codex-dir backfill** — `ingest --backfill` now also sweeps `~/.codex/sessions/**` (+ archived_sessions)
  via the Codex adapter. Real run: 119 rollouts ingested. (`--codex-root` to override.) *(v0.4.5)*
- [x] **`export --since <iso>`** — incremental dashboard refresh (Nick-requested). *(v0.4.5)*
- [x] **`session_detail` view + `export --detail <session>`** — per-model-call timeline (Nick-requested),
  schema `mrtoken.session_detail.v1`. *(v0.4.5)*
- [x] **Internal feedback & observability** — `explain` / `feedback` / golden regression. *(v0.4.6, ROADMAP 5D)*
- [x] **Codex live integration** — the Stop hook is now agent-aware: `~/.codex/hooks.json` auto-ingests each
  Codex session on end (`source='codex'`) with a Codex HUD. Confirmed live (a real session captured). *(v0.4.7)*
- [x] **Central Codex DB** — Codex sessions sprawl across dirs, so per-project DBs scattered them. Now they
  aggregate in one central `~/.mrtoken/data/codex.db`; `--codex` shortcut on fleet/report/explain/export/
  validate/roi/why; `ingest --backfill` routes Codex there. fleet now counts Codex sessions. Backfilled 122
  sessions (165M tok, $1,059 API-eq). *(v0.4.8)*

## Backlog / not yet scheduled
- **Codex live-pressure tracker (proc engine)** — feed the 6.4 engine for Codex by tracking current
  context from the rollout (`model_context_window` + running input-side tokens), since Codex has no
  Claude-style live transcript snapshot. Surfaced by 6.4 (engine is shared; only Claude is wired live).
- **Cross-session linkage for ROI cohort B** — detect that a *fresh* session started in the
  same project shortly after a `fresh_handoff` fired, so the acted-vs-ignored split is real
  (current B is degenerate because the rule only fires on already-deep sessions). Surfaced by 2.1.
- `--since <iso>` incremental filter on `export` (Nick asked, for dashboard refresh).
- `session_detail` per-model-call timeline view (drill-down panel for the dashboard).
- Dashboard maturity (TS/`web/`) — Nick's lane; coordinate via the `session_summary.v1` contract.
