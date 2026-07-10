# GOAL: Headroom less-constrained compression probe (7.3 measurement)

**Lane:** Codex / Claude (harness exists; scoped, test-checkable) · **Status:** ready
**Est:** M · **Budget:** $0 API (fake localhost upstream — no real provider calls; ~500 MB
disk in `/tmp`) · **Source:** MODULE-EVALUATION "remaining evidence gate" item 1;
**greenlit by Zach 2026-07-10** (protocol designed by Fable, this brief).

**Question:** does Headroom's compression actually save tokens on OUR tool-output corpus,
reversibly? The safe synthetic probe proved the measurement loop but showed 0 savings
because it disabled Kompress and blocked binary downloads. This probe relaxes exactly one
thing — **compression capability** — and nothing else.

## What is relaxed vs. what stays hard-line

Relaxed (the point of this probe):
- Kompress enabled: drop `HEADROOM_DISABLE_KOMPRESS=1` from the traffic probe env.
- Helper assets allowed — but ONLY via the audited pre-fetch step below, never mid-probe.

Hard lines (unchanged from the 2026-07-08 harness; violating any = stop and report):
- No real agent: never run `headroom wrap`, `headroom init`, `headroom install`,
  `headroom mcp install`; never set `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL` in a real shell;
  never launch Claude/Codex through the proxy.
- No real provider traffic: upstream stays the fake localhost Anthropic endpoint.
- Proxy binds `127.0.0.1` only.
- All writes stay inside the sandbox (temp `HOME`/`XDG_DATA_HOME`/`TMPDIR` under `/tmp`);
  nothing lands in the real `~/.headroom` or `~/.mrtoken`.
- `HEADROOM_UPDATE_CHECK=off`, `HEADROOM_TELEMETRY=off`,
  `HEADROOM_NO_SUBSCRIPTION_TRACKING=1` stay set in every step.
- Do NOT register/enable the module in `mrtoken-transcript modules` as part of this brief.

## Protocol

**Step 0 — venv.** Reuse `/tmp/mrtoken-headroom-proxy-eval` (`headroom-ai[proxy]==0.30.0`,
pinned); recreate per MODULE-EVALUATION.md if gone. If Kompress needs an extra (e.g.
`[kompress]`/model deps), install it pinned into the SAME sandbox venv and record exactly
what was added.

**Step A — audited asset pre-fetch (the ONLY networked step).** Find out what Kompress
needs at runtime (read the installed package source — don't guess): model files from
`cdn.pyke.io`/Hugging Face, `difft`/`scc` binaries, tiktoken vocab. Fetch them explicitly
into the sandbox cache, and record in the results note: each URL, byte size, and sha256.
Then the probe itself runs with `HEADROOM_OFFLINE=1` + `HEADROOM_BINARIES_OFFLINE=1` so
nothing fetches mid-measurement. If Kompress refuses to run under those flags even with
assets pre-fetched, relax the SINGLE blocking flag, name it in the results, and eyeball
`proxy.log` for fetch attempts afterward (any unexpected egress → verdict `drop`, see below).

**Step B — corpus.** Two tiers, both local-only:
1. **Fixtures (reproducible):** the big reference/tool-output blocks from
   `backend/experiments/tasks/debug-hugelib`, `debug-scanlib`, `debug-speclib` — they were
   built to bloat, and they're what the compaction gate already reasons about.
2. **Real corpus (the honest one):** the ~20 largest `tool_result` payloads drawn from
   local Claude transcripts (query the shared DB / transcripts for the biggest tool
   outputs; mixed kinds — file reads, test output, grep dumps). Content stays on-machine:
   it only transits the localhost proxy to the fake upstream. Delete the sandbox (incl.
   Headroom's logs, which may contain payload content) when done — the privacy invariant
   applies to what we KEEP, and we keep only token counts.

Send each payload through the proxy as an Anthropic-shaped request (the
`--synthetic-headroom-traffic` plumbing already does this for one canned payload —
generalize it to take a payload file/dir; small harness change, tests green after).
Collect `tokens_before`/`tokens_after` per row via the existing `--headroom-log` parser.

**Step C — quality gate (probe-level, deterministic — no LLM judge).** Headroom's pitch is
*reversible* compression (the agent can retrieve originals). So probe-level "equal quality"
= reversibility + fidelity:
1. **Round-trip:** for each compressed payload, retrieve the original through Headroom's
   own retrieval path (CCR store — use a disk/memory backend inside the sandbox) and
   byte-compare to the input. Any mismatch = quality fail for that row.
2. **Needle check:** per payload, pick 3 deterministic needles a debugging agent would
   need (the error line, a failing test name, a specific identifier/number). Each needle
   must appear verbatim in the compressed text OR be recoverable via the round-trip.
   Automated string asserts.
A row passes quality only if both hold. Task-level quality (does an agent still finish the
job?) is explicitly NOT claimable from this probe — that's the 6.7/experiment oracle, later,
real-agent, separately gated.

**Step D — record + write up.**
- `module-measure --record` savings/outcomes ONLY for rows with quality=pass (the harness
  already enforces this pairing).
- Append a dated decision-log entry to `backend/docs/MODULE-EVALUATION.md`: the per-tier
  table (n, median/mean savings %, quality pass rate), the pre-fetch audit list, any flag
  relaxed in Step A, files the sandbox wrote, and the verdict.

## Verdict rule (decide from the numbers — no re-litigating)

- **drop** if ANY of: median savings on the real-corpus tier < 10%; any round-trip
  failure; any needle unrecoverable; any egress during Step B/C beyond localhost.
- **opt-in (registered but disabled, LAB note)** if ALL of: real-corpus median savings
  ≥ 10%, 100% quality pass, clean egress. Registration itself happens in a follow-up
  commit with Zach's ack — this brief only writes the verdict.
- **default-on is unreachable from this probe** regardless of numbers: it additionally
  requires real-agent equal-quality evidence (6.7 oracle) + separate Zach approval for
  any wrap/routing. Say so in the decision log so nobody upgrades the claim later.

The 10% bar, for the record: Headroom's README claims 15–20% for coding agents; below 10%
on our own tool-heavy corpus, the integration + trust surface (349 MB venv, proxy in the
loop) isn't worth carrying against our existing free `offload` path.

**Loop exit (done-criteria):**
1. Both corpus tiers measured with Kompress actually active (a run where
   `tokens_before == tokens_after` on every row means Kompress never engaged — that's a
   harness bug to fix, not a result to record).
2. Quality gate run on every measured row; results in the table.
3. `MODULE-EVALUATION.md` decision-log entry with table + audit + one verdict from the
   rule above.
4. Savings/outcomes recorded via `--record` only for passing rows (or explicitly "none
   recorded" if verdict is drop).
5. Any harness change: `./scripts/test-backend.sh` green, noted in the entry.
6. Sandbox torn down (payload-bearing logs deleted); what was written+deleted is listed.

## Out of scope
- Registering/enabling the module (follow-up, Zach-acked).
- Real-agent wrapping/routing, task-level quality claims, Ponytail (deferred per
  MODULE-EVALUATION).
- Comparing Headroom vs `offload` head-to-head (worth doing LATER if verdict is opt-in;
  needs its own design).
