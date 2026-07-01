# The compaction gate — telling the WIN regime from the LOSE regime

*Design spec. Turns the 5A regime-map result (`ROI-EXPERIMENT.md` → "RESULTS") into a
concrete refinement of the proc engine (`intervene.py`) so it only nudges a context
reset when a reset actually pays. This is the precondition for ROADMAP 6.8 (L3 auto-act):
you cannot safely auto-compact until you can predict whether compacting helps.*

## Why this is the roadblock

The proc engine (`intervene.py:evaluate`) fires when **`pressure ∧ reclaimable-junk`**:

```python
RECLAIMABLE = {"huge_tool_output", "re_read_loop", "repeated_context", "context_rot"}
pressure = ctx_pct >= 70 or (0 < turns_to_full <= 4)
if not (pressure and junk): return None      # else: nudge offload/handoff
```

The 5A experiment shows that `pressure ∧ junk` is **necessary but not sufficient**, and
that the *outcome flips sign* by regime at the same pressure and the same "junk":

| Regime | What the context is | Reset (handoff/compact) result |
|---|---|---|
| Disposable (debug-scanlib) | big read used once, never needed again | **−28% to −30% (WINS)** |
| Load-bearing (debug-speclib) | refs needed again to finish | **+20% (LOSES)** — dropped, then re-read |

The governing model (validated): a reset pays iff
`reclaimable × carry-cost × turns_remaining > summary + re-establish + re-read_risk`.
Two terms decide it, and **the engine currently measures neither**:

1. **re-read_risk** — will the reclaimed context be needed again? (disposable vs load-bearing)
2. **remaining-runway** — is there enough work left for per-turn savings to compound?
   (`turns_to_full` is turns-to-context-**wall**, NOT turns-to-**task-done** — different quantity.)

### Where the current engine is right, and where the gap is

Credit where due: `_tool_for()` already routes `re_read_loop`/`repeated_context` to **`offload`**
(keep-but-externalize) — the regime-safe choice, since that content is being re-paid *because it's
needed again*. Good. `huge_tool_output` → `offload` too.

The gap is the **one DROP path**: `context_rot` → **`handoff`** (a fresh session that drops the
transcript). `context_rot` is a *generic* "this session has run long and is filling up" signal — it
carries **no information about whether the accumulated context is disposable or load-bearing.** So the
only destructive nudge the engine emits fires on a signal that can't tell the win regime from the lose
regime. That's exactly the speclib case: pressure is real, but the context is load-bearing, so
`handoff` drops refs that must be re-read (+20%). Today this is only L1 "tell" (advisory, low stakes),
but it is the precise path that **must not** graduate to L3 auto-act (6.8) without a disposability +
runway gate — an auto-`handoff` on `context_rot` over load-bearing context would actively raise cost.

## The fix: two gates + a tool-choice rule

### Gate 1 — disposability (re-read_risk), per reclaimable block

At a turn boundary, for each large context block (a big file Read / tool output), track
**turns-since-last-access**. Classify:

- **Disposable** — read once (or early) and **not re-accessed** for ≥K turns → safe to DROP.
  (`huge_tool_output` that hasn't recurred is the canonical case.)
- **Load-bearing** — re-accessed recently, or flagged by `re_read_loop` / `repeated_context`
  → do **not** drop; if pressure demands action, prefer `offload` (keep-but-externalize).

This is computable from the transcript LiveMonitor already feeds `intervention_for_session()`
— it's a per-block last-seen timestamp, no new capture, privacy-invariant (hashes/sizes only).

### Gate 2 — remaining-runway (turns_remaining)

`turns_to_task_done` is unknowable a priori, so use conservative proxies and **suppress** the
nudge when runway is short (benefit < cost — the speclib late-burst case, threshold crossed with
few turns left):

- **Progress trend**: tests trending red→green, error/diagnostic count falling, edits/writes
  accumulating (durable artifacts being produced) → likely near done → suppress drop-nudges.
- **Session trajectory**: early/mid session → runway long; if the only remaining signal is
  "one test failing," do not nudge a reset.
- **Optional explicit**: let the `mr-context` skill / a toolbox call report remaining work so
  the agent can override the proxy.

### Tool-choice rule (immediate, cheap win)

Decouple the tool from mere "junk present":

| Situation | Nudge |
|---|---|
| Disposable junk + runway remaining + pressure | `handoff` / `compact` (DROP) — the win case |
| Load-bearing but heavy (`re_read_loop`/`repeated_context`) | `offload` (KEEP-but-externalize) — never a blind drop |
| Near-done (short runway) | **suppress** — a reset now costs more than it saves |
| Pressure, no reclaimable junk | quiet HUD only (unchanged) |

## Where it plugs in (`intervene.py:evaluate`)

Keep `evaluate()` pure and agent-agnostic; extend its inputs, don't fork it:

```python
def evaluate(ctx_pct, turns_to_full, signals_fired, *,
             disposability=None,     # {block_id: "disposable"|"load_bearing"} or a score
             progress=None,          # e.g. {"tests_trend": "improving", "near_done": bool}
             pressure_pct=PRESSURE_PCT, pressure_turns=PRESSURE_TURNS):
    ...
    if near_done(progress): return None                  # Gate 2: short runway → suppress
    if drop_tool(tool) and not any_disposable(disposability, junk):
        tool = "offload"                                 # Gate 1: don't drop load-bearing
```

`intervention_for_session()` computes `disposability`/`progress` from the same transcript it
already parses. Everything stays behind `policy.py` toggles and is measured by `outcomes.py`
(6.7): if a gated nudge still trends negative, measure-don't-degrade disables it as today.

## Validation — the fixtures ARE the acceptance test

The two committed fixtures give a ground-truth oracle for the gate (this is the elegant part):

- Replay a `debug-scanlib` transcript → the gate MUST fire a **drop** nudge (disposable notes,
  runway remaining). Acting on it should reproduce the ~30% win.
- Replay a `debug-speclib` transcript → the gate MUST **suppress** the drop nudge (or downgrade
  to `offload`), because dropping the load-bearing refs is the +20% loss.

A gate that fires-drop on scanlib and suppresses-drop on speclib is, by construction, one that
distinguishes the win regime from the lose regime. Add both as golden cases to the 5D.3 golden
regression so the classifier can't silently regress.

## Phasing

1. **Gate the one DROP path (cheap, do first).** `context_rot → handoff` currently fires with no
   disposability signal. Until Gate 1 exists, make it conservative: on `context_rot` alone, prefer
   `offload` (reversible) and only *mention* handoff as an option, rather than leading with the drop.
   (`re_read_loop`/`repeated_context`/`huge_tool_output` already route to `offload` — leave them.)
2. **Gate 1 (disposability recency).** Per-block turns-since-access; a `handoff`/`compact` DROP
   nudge requires a disposable target, not just `context_rot` pressure.
3. **Gate 2 (runway proxy).** Near-done suppression from progress trend.
4. **Only then, 6.8 L3 auto-act** — enable auto-drop **exclusively** in the
   disposable ∧ runway-remaining case that the fixtures + 6.7 outcomes prove positive. Auto-act
   stays off for load-bearing and near-done.

## Risks / limits

- Proxies are imperfect: "disposable" can be wrong (a block re-becomes relevant), so Gate 1
  should bias toward `offload` (reversible: content is preserved) over `handoff` (destructive)
  when uncertain. 6.7 remains the backstop.
- Runway detection is the hardest and least certain; ship it warn-only long before auto.
- Small-n experiment (2–4 reps, high rollout variance): the *direction* is robust and
  mechanistically explained, but re-validate the gate on real sessions before 6.8 auto.

## Related

- `ROI-EXPERIMENT.md` → "RESULTS — the regime map" (the evidence)
- `intervene.py` (proc engine), `policy.py` (toggles), `outcomes.py` (6.7 measure-don't-degrade)
- ROADMAP 6.8 (L3 Do — gated on this), open research thread in `ORCHESTRATION.md`
