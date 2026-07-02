# GOAL: 5B.2 — refresh the coordination note to Nick

**Lane:** Claude drafts · **Zach sends** (outward-facing — do NOT send) · **Status:** ready ·
**Est:** S · **Budget:** $0

**Loop exit (done-criteria):**
1. `backend/docs/HANDOFF-TO-NICK.md` matches the **shipped v1 data surface** — no longer lists the
   two "open questions" as open (they're built: `session_detail.v1` + `--since`).
2. It says, in Nick's terms: what he can consume now (`session_summary` view / `export`), the new
   drill-down (`session_detail` + `export --detail`), incremental refresh (`--since`), and the
   `is_low_activity` column — and points to `docs/UI-INTEGRATION.md` as the full spec.
3. It's a **draft for Zach to send** — the doc ends by making clear Zach forwards it; no auto-send.

## Why (root cause, stated)

`docs/UI-INTEGRATION.md` (5B.1) is now the complete v1 surface, and the code already ships
`session_detail`/`--since`. But `docs/HANDOFF-TO-NICK.md` — the short note Zach actually forwards to
Nick — still frames those as **open questions**, which is now wrong and would confuse him. 5B.2 =
bring the note in line with reality so Nick knows the drill-down data is ready to build against.

## Steps

1. Read `docs/HANDOFF-TO-NICK.md` (current) and `docs/UI-INTEGRATION.md` (source of truth).
2. Rewrite the note: TL;DR of what's consumable, the join, the new `session_detail` drill-down +
   `export` flags, the `is_low_activity` filter, and the stability contract — all pointing to
   UI-INTEGRATION.md for detail. Replace "two questions for you" with "both are answered — here's how."
3. Keep it short and Nick-facing (he's TS/web); link, don't duplicate the full column tables.
4. Leave a one-line "Zach: forward this to Nick" marker so the loop doesn't send it.

## Verify

- `diff`-read the two docs: no claim in HANDOFF-TO-NICK.md contradicts UI-INTEGRATION.md; no "open
  question" language remains. (No command to run — it's a doc; correctness = consistency with 5B.1.)

## Constraints
- Inherit `GOALS/README.md` global rules. **Outward-facing: draft only, Zach sends.** Metadata-only framing.
- Don't restate the whole spec — the note is a pointer + highlights.

## Out of scope
- Building any dashboard panel (Nick's TS lane). Changing the data surface itself (that's 5B.1, done).
