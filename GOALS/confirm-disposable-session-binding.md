# GOAL: Bind `confirm_disposable` to the CALLING session (fix the cross-session misdirect)

**Lane:** Codex / Claude / Fable (backend Python, test-checkable) · **Status:** ready
**Est:** S–M · **Budget:** $0 · **Source:** Fable adversarial review of PR #20 (2026-07-03)

**Loop exit (done-criteria):**
1. A `confirm_disposable` call from session A can never record a confirmation under session
   B's id. Concretely: when the caller's session cannot be identified UNAMBIGUOUSLY, the tool
   records **nothing** and returns an instruction telling the agent how to re-call with its
   session id (fail-closed, matching the channel's design).
2. The single-session case keeps working with zero friction (no `session` arg needed).
3. A regression test simulates the two-pane case — two transcripts in one project dir, the
   OTHER session's file newer — and asserts the no-arg call refuses (or binds correctly),
   and that nothing lands under the other session's id.
4. `backend/skills/mr-context/SKILL.md` tells the agent how to pass its identity when asked
   (e.g. `session: <value of $CLAUDE_CODE_SESSION_ID from a Bash echo>`).
5. `./scripts/test-backend.sh` green.

## Why (root cause — verified 2026-07-03)

`record_disposable_confirmation(None)` resolves "the current session" via
`resolve_path(None) → latest_transcript()` **inside the MCP server process**. The session
pinning in `latest_transcript()` (`MRTOKEN_SESSION` / `CLAUDE_CODE_SESSION_ID`) never applies
there: inspection of the 10 live `mrtoken-transcript mcp` processes on 2026-07-03 showed
**neither env var is present** (only HOME/PATH/etc — Claude Code does not pass the session id
to MCP server processes). So the resolver always falls to newest-mtime in the cwd project dir.

With two concurrent sessions in one project — the documented K2 two-pane setup
(`ONBOARDING.md`), and the normal state of this repo — the newest transcript at call time can
be the OTHER session's. Then:
1. Agent A calls `confirm_disposable` → recorded as `disposable-<B>.json`, with
   `confirmed_at_call` = **B's** model_calls (so the call-TTL check passes cleanly in B).
2. B's next prompt hook (which pairs `session_id` + transcript correctly from the hook
   payload) finds a "fresh" confirmation → merges `disposable_confirmed` → **escalation past
   tell unlocked in a session whose agent never consented.** A gets nothing (fails safe;
   B fails open).

Severity by autonomy level: at today's default (`tell`) it's only a wrongly-strengthened
nudge in B; at `ask` it's a misdirected consent question; at 6.8 `do` it is an **auto-drop
authorized by the wrong agent** — potentially auto-resetting a load-bearing session, the
exact +20% lose regime the whole gate exists to prevent. This is a **pre-6.8 blocker**:
fix before any tool's autonomy flips to `do`.

Note the unit tests couldn't catch this: they stub `intervene._session_calls`, which is
exactly where the identity bug lives.

## Recommended fix (decide here so the executor doesn't have to; Zach/Claude may overrule)

**Refuse-on-ambiguity** in `record_disposable_confirmation` / `_session_calls`:
- If the no-arg resolver's project dir contains **more than one transcript modified
  recently** (e.g. within the last ~10 minutes — named constant, comment the reasoning),
  treat the caller's identity as unknown: record nothing, and have
  `_confirm_disposable_call` return "multiple active sessions here — re-call with
  `session: <your session id>` (Bash: `echo $CLAUDE_CODE_SESSION_ID`)".
- An explicit `session` arg that matches exactly one transcript proceeds as today.
- Keep it cheap: `os.path.getmtime` over the same glob `resolve_path` already does.

Rejected alternatives (for the record): passing the id via MCP server env (Claude Code
doesn't provide it, verified above); trusting mtime ordering (the race is the bug); a
negative call-delta guard in `_fresh_disposable_confirmation` (useless here — the recorded
count comes from B's own transcript, so the delta looks valid).

## Adjacent hardening from the same review (optional, separate commits if taken)

- `_fresh_disposable_confirmation` catches only `ValueError` on timestamp parse; a naive-tz
  ISO string in a corrupted state file raises **TypeError** on the aware-naive subtraction,
  which the hook's blanket `except Exception` then swallows **every turn** — persistently and
  silently disabling the intervention path for that session. Fix: `except (ValueError,
  TypeError)` → return False (fail-closed, matches intent).
- `resolve_path(arg)` prefix glob spans **all** projects (`PROJECTS/*/{arg}*.jsonl`); a short
  prefix can bind another project's session. Consider requiring ≥ 8 chars or an exact match
  for `confirm_disposable`'s `session` arg specifically.
- Test gap: nothing exercises the `intervention_for_session` merge line end-to-end (fresh
  confirmation file + matching `session_id` + transcript fixture → escalated level). The
  decide() contract and the freshness state machine are each unit-tested; the plumbing
  between them is not.

## Constraints
- Inherit `GOALS/README.md`. `evaluate()`/`decide()` signatures unchanged; do NOT touch the
  Gate 1 cap or the TTL semantics (one root cause per change — this brief is about **caller
  identity**, nothing else).
- Privacy invariant: metadata only (the refusal message must not quote transcript content).

## Out of scope
- 6.8 L3 auto-act (still needs this + 6.7 outcomes evidence).
- Consume-on-use for confirmations at `do` level (one confirmation currently stays valid for
  its whole TTL, so it could in principle authorize more than one auto-act; a handoff's new
  session id invalidates it naturally, so this is a 6.8-design note, not a defect today).
