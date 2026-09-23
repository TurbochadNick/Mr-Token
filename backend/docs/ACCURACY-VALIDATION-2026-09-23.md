<!--
Provenance: preserved VERBATIM from the 2026-09-23 analysis report (below the rule),
committed because the decision to take the rules engine, validate, and the cost display
offline rests on it. Numbers were measured on file copies of two real stores taken at
16:53 MDT with the code at 081d4bb, and were NOT re-run at commit time.

Bears on RULE-CALIBRATION.md: its "well-calibrated" entries and precision-proxy figures
rest on the `validate` proxy that section 2 below finds mostly unable to fail.
-->

# Does MR Token do it well? What `validate` says, and what it cannot say

2026-09-23. Read-only against COPIES of two real stores, taken with `cp -p` (a filesystem
read) at 16:53 MDT; integrity_check ok on both copies. Live stores were never opened for
writing. `validate` ran with the code at 081d4bb, against the copies only.

- `~/.mrtoken/data/codex.db`: 374 sessions, 178,623 model calls, 837 recommendations
- `mr_token/.token-tithe/token-tithe.db` (Claude): 30 sessions, 5,012 model calls, 19 recommendations

The live codex.db changed during the work (hash 2396538a -> 988bdc54). I attributed it
rather than assuming: the live store gained 2 model_call rows, and its MAX(ingested_at)
moved to 22:53:22Z, equal to the file's new mtime. That is an external Codex ingest, not
this analysis.

## 1. What validate reports

| store | rule | fired | strong | weak | moot | proxy |
|---|---|---|---|---|---|---|
| codex | retry_loop | 342 | 320 | 22 | 0 | 94% |
| codex | huge_tool_output | 199 | 172 | 23 | 4 | 88% |
| codex | step_runaway | 109 | 102 | 7 | 0 | 94% |
| codex | fresh_handoff | 48 | 42 | 4 | 2 | 91% |
| codex | low_cache | 1 | 1 | 0 | 0 | 100% |
| claude | huge_tool_output | 5 | 3 | 2 | 0 | 60% |
| claude | step_runaway | 5 | 3 | 2 | 0 | 60% |
| claude | fresh_handoff | 4 | 4 | 0 | 0 | 100% |
| claude | retry_loop | 3 | 3 | 0 | 0 | 100% |

On Codex it says "thresholds look well-calibrated" for every rule.

Pricing sanity (Codex): 8 models have no price row and are billed at the default rate:
gpt-5.4 (4,899 calls), gpt-6-astra (3,013), gpt-6-sol (1,563), codex-auto-review (988),
gpt-5.3-codex-spark (68), gpt-5.1-codex (52), gpt-5.4-mini (38), gpt-5.3-codex (25). That
is 10,646 of 178,623 calls (6.0%). Price table is 75 days old (2026-07-10). Claude: every
model priced; same staleness warning.

## 2. Assessing the assessor: the proxy mostly cannot fail

The report LOOKS green. Taken rule by rule, almost none of that green is evidence.

| rule | what its "strong" test is | status |
|---|---|---|
| low_cache | `calls >= 10`, while the rule only fires when `calls >= LOW_CACHE_MIN_CALLS` (10) | TAUTOLOGY: cannot return weak for any firing |
| retry_loop | `distinct_calls >= 2`, a field the rule itself computed | CIRCULAR: re-reads the trigger evidence |
| repeated_context | waste >= 20,000, which is the rule's own "high" severity threshold | CIRCULAR ("strong" = "high severity"); 0 firings here |
| huge_tool_output | >= 10 model calls follow the output | NON-DISCRIMINATING: base rate below |
| step_runaway | tool errors + re-reads >= 5 | WEAK: scales with session size |
| fresh_handoff | 2nd-half est. cost > 1st-half | WEAK: high base rate below |
| context_rot | no checker | INVISIBLE: 138 Codex + 2 Claude firings silently skipped (validate.py:147) |

Base-rate control: apply each "strong" test where the rule did NOT fire (Codex store).

| checker | where rule fired | where rule did NOT fire |
|---|---|---|
| huge_tool_output | 97.9% of oversized outputs | 98.4% of ORDINARY outputs |
| fresh_handoff | 91.3% of fired sessions | 71.8% of non-fired sessions with >= 20 calls |
| step_runaway | 93.6% of >= 120-call sessions | 61.8% of 60-119-call sessions (rule does not fire) |

Read plainly:
- huge_tool_output's verdict measures "the output was not at the very end of the session",
  which is true of nearly every tool output. It carries almost no information.
- fresh_handoff's "strong" is mostly "long sessions get costlier in their second half",
  which is true of most long sessions whether or not the rule fired.
- step_runaway's churn grows with step count, which is the thing the rule already fires on.
  It does not separate waste from a genuinely large task.
- The Claude store is too small to be decisive (7 oversized outputs; 13 sessions with >= 20
  calls). Its huge_tool_output base rate (14.3%) disagrees with validate's own 3/5, and at
  that n I have not resolved it.

**Verdict on the assessor:** validate is a precision proxy in name only. 1 of 6 checkers is
a tautology, 2 re-read the evidence that fired the rule, 3 read separate data but pass at
near their base rate, and the second-most-frequent Codex rule has no checker at all.
"94% strong" does not mean 94% of advice was good. It is closer to "94% of firings met a
condition that most sessions meet". The proxy cannot tell us whether any recommendation is
worth acting on.

## 3. Are the numbers right? Nothing in the tool checks, so I did

validate checks price-table coverage and NULL costs. It never checks token counts.

**Claude: stale double-counted history.** 467 request IDs appear more than once in the
ledger (5,012 rows, 4,233 distinct request IDs); 444 of those groups repeat byte-identical
usage (one API response written as several transcript lines). Counting one row per request
ID (assumption: one request ID = one API call, which is how the API defines it; 46 rows
with no request ID excluded):
- fresh input + output over-counted 17.0%
- cache read over-counted 14.1%
- estimated cost over-counted 40.9% (why cost inflates more than tokens is not verified)

Cause, pinned: ALL of it is 6 sessions ingested on 2026-06-15 (1,469 rows for 736 API
calls, 99.6% extra), before the dedup fix 2847a46 (2026-06-20). Every later ingest date shows
0% extra, and ingest.py:449-461 dedups on message.id. So the current ingest is right, but
the store still holds stale inflated history. Nothing flags it and nothing re-ingests it.

**Codex: mostly unverifiable, and where verifiable, over-counted.** Only 19 of 374 sessions
carry a provider-reported cumulative total to check against. The other 355 have no
independent reference. Of the 19:
- 7 match exactly
- 11 are 0.3-2.2% OVER the provider total. Most of that is consecutive rows repeating
  identical usage (repeated token_count events counted twice); removing them leaves
  1.0015-1.006x, so a 0.2-0.6% residual is unexplained.
- 1 (trace 6796) is 2.02x the provider total. Its 770 rows are all distinct, so this is not
  simple duplication. It could equally mean the provider's "final" total covers only part
  of the session (e.g. a counter reset on resume). Direction unknown.
The ledger was never UNDER the provider total.

## 4. What this means, in one paragraph for Zach

MR Token reliably RECORDS what happened and counts current Claude sessions correctly, but
its self-assessment does not establish that its advice is good. Its validation harness
mostly passes by construction or at base rate. The stored numbers carry a known ~17% token
/ ~41% cost inflation in this Claude store from pre-fix history that was never re-ingested,
and a 1-2% over-count on the few Codex sessions that can be checked at all. Dollar
estimates for 6% of Codex calls use a default rate, and the price table is 75 days old. The
honest answer to "does it do it well" is: we do not know, and the tool's own answer to that
question is not evidence either way.

## 5. What the proxy CANNOT tell us, even if every checker were fixed

- No ground truth. It never observes whether acting on advice saved anything. That needs an
  intervention comparison (the roi --measure cohort is the nearest thing, and it is
  observational).
- Corroboration is not correctness. A checker built from the same signal as the rule will
  agree with it by construction.
- It says nothing about rules that did not fire (recall).
- It judges advice given the ledger. If the ledger is wrong (section 3), it inherits that
  silently.

## 6. Limits of this analysis

- Two stores, one machine, one user. The Claude store is small.
- Copies taken at 16:53 MDT; the live Codex store kept changing.
- The dedup figures assume one request ID = one API call.
- The Claude huge_tool_output base-rate discrepancy is unresolved (small n).
- Trace 6796's 2x is unexplained.
- I did not validate the rules' thresholds themselves, only the checkers that grade them.

## 7. Candidate next slices (not started; the Lead's call)

1. Re-ingest or flag pre-2847a46 sessions (a stale-data fix, not a code fix).
2. Dedupe repeated Codex token_count events, and investigate trace 6796.
3. Rebuild validate's checkers on independent evidence, with the base-rate control
   committed as a test, so a checker that passes at base rate fails CI.
4. Add a context_rot checker, or report unchecked rules instead of skipping them.
5. Price rows for the 8 uncovered Codex models; refresh prices.json.
