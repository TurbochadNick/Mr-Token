# MR Token — Product Direction

*Proposed direction for sign-off. Zach drafted these; Nick, react/amend freely —
nothing here is locked until we both agree.* · 2026-06-04

## 1. Ownership
**Joint venture, Nick + Zach.** (BYU/TTO ownership question parked for now —
flagged for revisiting before there's real revenue, since it's in a BYU TTO pilot.)

## 2. Scope — stay narrow on Claude Code
**Do not build multi-agent adapters yet.** The moat is that Claude Code's
transcripts expose *real* token counts; that advantage doesn't transfer to tools
that only allow estimates. Win Claude Code decisively first, expand later from
strength. (Revisit only if the pilot/TTO explicitly wants a broad internal tool.)

## 3. One tool, eventually TypeScript
Long-term: **one installable tool, target TypeScript** (npm + single-binary is
solved there; a Node tool that needs a Python runtime loses users at install).

**For now**, the Python engine stays as the *optional accuracy layer* — no rush.
**Port Python → TS only when all three are true:**
1. the pilot has given its verdict (don't rewrite something that might pivot),
2. the rule logic has been stable ~2+ weeks (don't port a moving target),
3. we've committed to external/public distribution (the only thing two languages
   actually blocks).

The engine is ~1500 LOC, so the port is a bounded few-day job once rules freeze.
Cheap to defer, cheap to do later.

## 4. Product layers — advice free, one assistive action as the wedge
- **Free local tier:** monitoring + rule-based recommendations (no AI in the loop).
- **The one assistive action:** a **fresh-handoff generator** — when MR Token
  detects a session should restart, it produces a compact handoff (goal /
  decisions / last state / changed files) the user reviews and pastes into a new
  session. This is the natural paid/AI feature.
- **Hard line:** no auto-compaction, no silent prompt rewriting — ever. It would
  break trust and the local-first/privacy positioning.

## Through-line
Win Claude Code narrow → one TS tool → one killer assistive action → keep
ownership clear. Depth over breadth; do one thing for the user, not just charts.

---

### Sign-off
- [ ] Zach
- [ ] Nick
