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

- [ ] **3.5 — Codex transcript ingestion (2nd agent)** *(gated: only after Phase 2 passes for Claude Code)*
  - **Files:** `backend/mrtoken/ingest.py` (source adapter), `schema.sql` (`source` already
    generic). **Spec:** parse Codex session logs into the same `trace → model_call/tool_call`
    model; reuse the rule engine. **Acceptance:** a sample Codex session ingests and reports
    with the existing rules; Claude Code path unaffected.

## Phase 4 — GTM / hardening *(parallelizable; first-run reliability is the real bottleneck)*

- [ ] **4.1 — Install smoke test for the desktop-app path** *(regression guard)*
  - **Why:** the global-Stop-hook bug + the empty-session noise both surfaced from real installs;
    lock the fixed behavior so it can't silently regress.
  - **Files:** `backend/tests/test_backend.py`. **Spec:** assert `init` registers the Stop hook
    globally, migrates a legacy project-local hook, and that a simulated Stop from an arbitrary
    cwd ingests into the cwd-resolved DB. **Acceptance:** test added and green.

- [ ] **4.2 — Release discipline: tag check in `doctor`/`update`**
  - **Why:** we shipped `0.4.4` in `pyproject.toml` but the update-nudge keys off git tags, so
    an untagged bump reaches no one. Make the gap visible.
  - **Files:** `backend/mrtoken/update_check.py`, `doctor`/`status` surface. **Spec:** warn when
    the installed/declared version is ahead of the latest git tag ("release not tagged"). Don't
    auto-tag. **Acceptance:** with version > latest tag, the warning shows; when equal, quiet.

- [ ] **4.3 — Positioning: rate-limit-first copy**
  - **Why:** most users are flat-rate and hitting plan caps; "do more within your limits" lands
    harder than "save money." **Files:** `README.md`, HUD/nudge copy. **Spec:** lead with the
    rate-limit + quality angle, keep the cost angle secondary. **Acceptance:** README one-liner
    and at least one nudge string updated; no behavior change.

---

## Backlog / not yet scheduled
- **Cross-session linkage for ROI cohort B** — detect that a *fresh* session started in the
  same project shortly after a `fresh_handoff` fired, so the acted-vs-ignored split is real
  (current B is degenerate because the rule only fires on already-deep sessions). Surfaced by 2.1.
- `--since <iso>` incremental filter on `export` (Nick asked, for dashboard refresh).
- `session_detail` per-model-call timeline view (drill-down panel for the dashboard).
- Dashboard maturity (TS/`web/`) — Nick's lane; coordinate via the `session_summary.v1` contract.
