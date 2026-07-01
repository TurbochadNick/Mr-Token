# Codex offload ROI smoke

Status: first live pair completed; not yet a win. Do not treat this as a causal
ROI trial; it is a small guardrailed smoke test for the live Codex HUD behavior:

```text
large tool output already hit context; do not rerun it normally...
```

## Claim

When MR Token recommends offloading a large output, following that advice should
reduce future token growth versus ignoring it, while preserving task completion.

This is narrower than the handoff ROI experiment. It tests the "offload the junk"
path, not `/mr-handoff`, compacting, or trigger timing.

The first live pair showed an important boundary: avoiding a repeated noisy
command is useful, but it is not enough when the original huge output already
landed in context. The stronger claim to test next is prevention: redirect or
filter future noisy commands before the bulk enters context.

## Arms

Run one matched pair first:

- `ignore`: continue after the large-output nudge without using offload.
- `follow_offload`: follow MR Token's offload/summarize guidance, keep only a
  compact summary or targeted query in context, then continue.
- `follow_prevent`: use the Mr Token guidance before rerunning a noisy command:
  redirect bulk output to a local file and inspect only targeted slices.

Use the same fixture, model, prompt, and budget for both arms.

## Fixture

Fixture path:

```bash
backend/experiments/tasks/codex-offload-noisy-log
```

It contains one seeded classifier bug. `python3 build_check.py` emits a large
diagnostic stream with one `ROOT_CAUSE` line. The oracle requires `processor.py`
to be fixed and rejects edits to `test_processor.py` or `build_check.py`.

Validate fixture plumbing without Codex:

```bash
python3 backend/experiments/runner.py \
  backend/experiments/tasks/codex-offload-noisy-log \
  --check-fixture
```

## Guardrails

- Run only one paired smoke first.
- Abort if either run crosses about 90% context.
- Abort if either run enters repeated tool errors.
- Do not compare tokens unless both arms pass the oracle.
- Do not claim ROI from one pair; call it directional only.
- Do not mix in compact or handoff. This isolates the offload advice.

## Manual run protocol

1. Prepare two fresh copies of the fixture seed, one named `ignore`, one named
   `follow_prevent`.
2. Start a fresh Codex session in the `ignore` copy with the task prompt.
3. Let the noisy diagnostic output happen and confirm MR Token emits the offload
   nudge.
4. Continue without offload; stop when the oracle passes or a guardrail trips.
5. Repeat in the `follow_prevent` copy, but prevent the noisy output from entering
   context. For example:

   ```bash
   python3 build_check.py > diag.log 2>&1
   grep 'ROOT_CAUSE' diag.log
   ```
6. Run each fixture oracle:

   ```bash
   backend/experiments/tasks/codex-offload-noisy-log/oracle.sh \
     <workdir> backend/experiments/tasks/codex-offload-noisy-log/seed
   ```

7. Compare the Codex sessions. For the legacy cleanup-only pair:

   ```bash
   mrtoken-transcript offload-roi --codex \
     <ignore-session-prefix> <follow-session-prefix> \
     --ignore-passed --follow-passed
   ```

   For the prevention pair:

   ```bash
   mrtoken-transcript offload-roi --codex \
     <ignore-session-prefix> <follow-session-prefix> \
     --ignore-passed --follow-passed --prevention
   ```

## Metrics

By default, `offload-roi` anchors each session at its first oversized tool output,
then compares what happened after that anchor:

- post-anchor fresh tokens (`input_tokens + output_tokens`);
- post-anchor estimated API-equivalent cost;
- post-anchor tool errors;
- post-anchor repeated huge outputs;
- final context tokens.

With `--prevention`, it compares whole-session totals because the follow arm may
avoid the first oversized output entirely.

Success signal for the one-pair smoke:

- both oracles pass;
- post-anchor mode: follow arm uses fewer post-anchor tokens, target `>=10%`;
- prevention mode: follow arm uses fewer whole-session tokens, target `>=10%`;
- follow arm does not add more tool errors;
- follow arm does not produce more huge outputs. In prevention mode it should
  produce zero oversized diagnostic outputs.

If that holds, run two more matched pairs before saying the offload nudge has a
repeatable directional effect.

## Live result 1 — cleanup-only pair, 2026-06-30

Both arms passed the oracle, but the follow arm did not save tokens:

```text
ignore 019f1a40-89d post_tokens=20,481 post_cost=$0.1331 errors=2 huge_outputs=1
follow 019f1a42-cc4 post_tokens=37,715 post_cost=$0.1763 errors=1 huge_outputs=0
delta: -17,234 post-anchor tokens saved (-84.2%), $-0.0432
directional win: no
```

Interpretation: the follow arm avoided the repeated huge output, but the first
huge output was already in context and the run still spent more post-anchor
tokens. This is a failed acceptance case for the old wording, and the reason the
next smoke uses prevention mode.
