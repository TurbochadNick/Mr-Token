# MR Token direction: a consumption meter, not a performance advisor

Decision record, 2026-09-23. Evidence: [ACCURACY-VALIDATION-2026-09-23.md](ACCURACY-VALIDATION-2026-09-23.md)
(measured on copies of two real stores) and the commits named below. Read this before
reviving anything it switches off.

## Decision

MR Token is a **consumption meter**: it measures tokens, context windows, cache efficiency
and context carry, and it measures them well. That is its durable value.

It is **not, and structurally cannot be, a performance advisor**. It never observes an
outcome. It sees what was consumed, never whether the work was any good, so no threshold
tuning can produce a quality signal from a consumption stream. This is why `validate` has
no ground truth: the gap is in the INPUTS, not the harness.

## Triage

| Bucket | What | Evidence |
|---|---|---|
| **Works** | Ingestion (current dedup is correct) | Every ingest after dedup fix 2847a46 (2026-06-20) shows 0% duplicate rows |
| | The HUD, both providers | ede40af: one field set, total expenditure, measured-or-absent window, no cost |
| | Plain measurement (tokens, window, cache ratio, carry) | Provider totals, deduplicated per API response |
| **Broken but sound** (fix, keep) | Analysis commands wrote the store | 9 read paths opened the writer; fixed by 5b2577e + e819b1b, LANDED as 06b53ef (2026-09-23) |
| | Crashes on zero-data states | 82e9c58 (fleet, empty DB), 7acf493 (roi, any session without cache reads); guard 8a696d6 |
| | Stale inflated history | Claude store: 6 sessions ingested 2026-06-15, before 2847a46, hold 1,469 rows for 736 API calls (~17% tokens, ~41% est. cost over). Re-ingest or flag: not yet decided |
| | Label derivation | "total tokens" on a subtotal across 5 printers: ee64359, 62c9e44, 929a676 |
| **Flawed idea** (switch off) | The rules engine | Every rule compares against a FIXED CONSTANT, never the user's own distribution, and most are gated on session size. Base-rate control (Codex store): huge_tool_output scores 98.4% of ORDINARY outputs "strong" vs 97.9% of oversized; fresh_handoff 71.8% non-fired vs 91.3% fired; step_runaway 61.8% at 60-119 calls vs 93.6% at 120+. The rules largely detect bigness |
| | The thresholds themselves | Calibrated (RULE-CALIBRATION.md) by a loop that cannot calibrate: the proxy below |
| | `validate` | Its stated purpose is tuning thresholds, so it goes with them. Its checkers mostly cannot fail: low_cache is a tautology (fires at calls >= 10, "strong" iff calls >= 10); retry_loop and repeated_context re-read the rule's own trigger fields; context_rot has no checker (138 Codex firings silently skipped) |
| | Cost on subscription sessions | There is no cost to be accurate about. No provider record carries billing_mode (0 keys in 1.77M Codex and 191k Claude lines); the price table is 75 days old with 8 Codex models unpriced (6% of calls) |

**Also switched off, carded separately:** the proc-engine intervention (`mrtoken.intervene`),
SILENCED ON BOTH PROVIDERS, not deleted. It has no evidence of discriminating better than the
rules engine, and needs its own evidence before anyone revives or removes it.
- Claude: the UserPromptSubmit hook, which fired at initiation, is silent (ede40af).
- Codex: `on_stop.CODEX_INTERVENTION = False` (one line to revive). Its only Codex input is
  `analyse()`'s rule names, so the rules gate already starves it; the switch keeps it off BY
  DECISION if the rules engine is ever re-enabled.

## Design principles

**What a number may be**
- An efficiency metric must be a **ratio or a shape, never a total.** A total mostly
  measures how big the session was.
- Compare against the **user's own distribution**, not a constant. That needs no tuning
  and no ground truth.
- An **unverified number** may be displayed with its basis. It may **never drive a
  decision**.
- **Every number displayed is a claim.** If it cannot be supported, it is not shown, or it
  is shown with its basis. An inferred value (e.g. a context window guessed from the model
  name) is never rendered as a measured one; a percentage over an unmeasured denominator is
  not a measurement.
- **Absent is not zero, and not-applicable is not unknown.** A field that applies but
  cannot be derived shows "?" and carries its reason; a field that does not exist for this
  provider is omitted.
- **A number's direction is on its face.** Every budget percentage is "% used"; the cache
  ratio is "cache hit" (a rate). The line states numbers; consequence lives only in the
  warning slot.

**How the displays relate (the governing rule)**
- **As similar as reasonable** across providers. Default to identical; diverge only for a
  reason, and name the reason where the divergence is. Strict parity forces false
  equivalence; free divergence is how two surfaces came to disagree about one model name.
  Valid reasons:
  - **The surface already shows it: do not render it again.** On Codex the CLI line shows
    model and effort, so MR Token's line carries consumption only. That is the right
    division of labour, not an accepted asymmetry: the user gets the same total picture,
    split by who already knows what. (It also saves context tokens every turn, since Codex
    puts the hook message into the model conversation, but that is a consequence, not the
    reason. Do not add the fields back when tokens get cheap.) The same rule would have
    caught the Claude HUD rendered three times per turn.
  - **The provider genuinely differs**, e.g. Claude reports a 5h window, the Codex account
    reports a 7d one: labelled by real duration, never flattened into one label.
  - **The data does not exist**, e.g. no measured window on a stdin-less Claude surface.
- **One readout per provider.** Claude: the persistent statusLine. Codex: the Stop message.
- **Deliver at completion, never at initiation.** A persistent surface needs no timing; an
  event surface fires when state has changed (Stop, PreCompact), never on submit.
- **Attribute every line.** "mr <version>" leads every surface (MR Token writes beside the
  harness's own text), and the version comes from the running code, never a literal.

## Savings (for when it is built)

`savings.py` already separates the two halves:
- **Realized**: tokens kept out of context by tools that actually ran. This is an observed
  intervention, so it SURVIVES the cleanup. But `est_tokens_saved` is self-reported by the
  tool performing the action (`offload`: bytes/4 minus summary/4), so even realized needs a
  base-rate treatment before it is trusted in a hook.
- **Addressable**: the sum of recommendation estimates. It inherits everything wrong with
  the rules and GOES with them.

## Design dividend (card: minimal status line)

The HUD is built as structured fields (value, state, alert, provenance, reason), with each
surface as a formatter over them. So Zach's idea of a user-selectable **very reduced status
line** is nearly free: another formatter over the same fields, not a rewrite. Its shape is
the same governing question asked harder: **what does this surface not already tell you?**
The same property lets a verbose plain-text view show provenance and "?" reasons with no
new data plumbing.

## Sequence from here

1. DONE: the read-only opener, reviewed and landed as 06b53ef.
2. DONE: the offline commit. Rules engine, thresholds, `validate` and the addressable half of
   savings are switched off behind `rules.RULES_ENABLED` (808a583, review fixes 7c4e800),
   RULE-CALIBRATION.md is superseded, and the Codex intervention is silenced (23e680e).
3. Decide re-ingest vs flag for the six stale sessions.
4. Carded: the proc-engine intervention (silenced on both providers); the TypeScript `openDatabase` write on
   every open, including the local UI read path (taken to Command); the WAL read-only-dir
   crash at ingest.py:331; offload-roi ValueError on sessionless stores; report.py:129 raw
   connect; `explain` exit code; a non-editable install to end live-from-tree deploys.
