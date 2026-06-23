# Rule calibration log

Running record of `mrtoken-transcript validate` (precision PROXY, not labels) on a
real corpus, plus any threshold changes and their rationale. See ROADMAP.md 2.2.

Principle: a low proxy is a prompt to investigate, **not** a license to lower a
threshold until the number looks good. Tune only when a rule is genuinely noisy,
and never on too few fires to be meaningful.

## 2026-06-23 — first calibration at volume (153-session backfill corpus)

| rule | fired | proxy (before) | proxy (after) | action |
|---|---|---|---|---|
| fresh_handoff | 20 | 100% | 100% | none — well-calibrated |
| retry_loop | 41 | 90% | 90% | none — well-calibrated |
| huge_tool_output | 21 | — (all moot) | **80%** | fixed corroboration bug (below) |
| repeated_context | 2 | 0% | 0% | none — n=2 too low to act |

**huge_tool_output was a measurement bug, not a rule problem.** The corroboration
checker read a top-level `tool_use_id` from the recommendation evidence, but the
rule writes its offenders under `offenders[]` (no top-level key). So the checker
never located the tool call and scored *every* fire "moot" → proxy undefined. Fixed
`validate._check_huge_tool_output` to read `offenders[]` and corroborate on the
worst-persisting output. The rule's real precision proxy is **80%** (16 strong /
4 weak / 1 moot) — sound; left unchanged. (Tool→model_call linkage verified healthy:
0 NULL across 121 oversized outputs, so the moot result was purely the key mismatch.)

**repeated_context (0%, n=2): no change.** Both fires were small (~3–4k uncached
tokens re-sent), which the corroboration correctly calls "weak"; the warn tier
(`REPEATED_WASTE_WARN`=2k … `REPEATED_WASTE_HIGH`=20k) is moderate-confidence by
design. With only two fires this is too thin to recalibrate responsibly — raising
the floor here would be tuning on noise. **Re-check once backfill volume grows;**
if a larger sample still shows the warn tier corroborating weak, consider raising
`REPEATED_WASTE_WARN` toward the ~5k meaningfulness floor.
