# Codex offload ROI smoke

Status: designed and fixture-ready. Do not treat this as a causal ROI trial; it
is a small guardrailed smoke test for the live Codex HUD behavior:

```text
large tool output is sitting in context. Use the `offload` tool...
```

## Claim

When MR Token recommends offloading a large output, following that advice should
reduce future token growth versus ignoring it, while preserving task completion.

This is narrower than the handoff ROI experiment. It tests the "offload the junk"
path, not `/mr-handoff`, compacting, or trigger timing.

## Arms

Run one matched pair first:

- `ignore`: continue after the large-output nudge without using offload.
- `follow_offload`: follow MR Token's offload/summarize guidance, keep only a
  compact summary or targeted query in context, then continue.

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
   `follow_offload`.
2. Start a fresh Codex session in the `ignore` copy with the task prompt.
3. Let the noisy diagnostic output happen and confirm MR Token emits the offload
   nudge.
4. Continue without offload; stop when the oracle passes or a guardrail trips.
5. Repeat in the `follow_offload` copy, but follow MR Token's offload guidance
   after the nudge.
6. Run each fixture oracle:

   ```bash
   backend/experiments/tasks/codex-offload-noisy-log/oracle.sh \
     <workdir> backend/experiments/tasks/codex-offload-noisy-log/seed
   ```

7. Compare the Codex sessions:

   ```bash
   mrtoken-transcript offload-roi --codex \
     <ignore-session-prefix> <follow-session-prefix> \
     --ignore-passed --follow-passed
   ```

## Metrics

`offload-roi` anchors each session at its first oversized tool output, then
compares what happened after that anchor:

- post-anchor fresh tokens (`input_tokens + output_tokens`);
- post-anchor estimated API-equivalent cost;
- post-anchor tool errors;
- post-anchor repeated huge outputs;
- final context tokens.

Success signal for the one-pair smoke:

- both oracles pass;
- follow arm uses fewer post-anchor tokens, target `>=10%`;
- follow arm does not add more tool errors;
- follow arm does not produce more huge outputs.

If that holds, run two more matched pairs before saying the offload nudge has a
repeatable directional effect.
