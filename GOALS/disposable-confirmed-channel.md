# GOAL: The explicit disposability channel (`disposable_confirmed`)

**Lane:** Codex / Fable (backend Python + one skill doc, test-checkable) · **Status:** ready
**after PR #19 review ratifies the Gate 1 contract** · **Est:** M · **Budget:** $0

**Loop exit (done-criteria):**
1. An agent can explicitly confirm droppability for the current session — a toolbox/MCP call
   (working name `confirm_disposable`) that records, session-scoped and metadata-only, "the
   loaded bulk context is no longer needed for the remaining work."
2. `intervention_for_session()` merges a **fresh** confirmation into the `disposability` input
   as `disposable_confirmed`, so `decide()`'s existing escalation path (b9a52c6: proxy capped
   at tell, explicit may reach ask/do) works end-to-end from a real session.
3. **Staleness is enforced**: a confirmation expires after N model calls / M minutes (named
   constants) — context changes, so an old "yes drop it" must not authorize a later drop.
   An expired confirmation degrades to the proxy path (tell-only).
4. `backend/skills/mr-context/SKILL.md` documents when the agent should call it (after the
   consent-question nudge, only when it has actually checked what the remaining work needs).
5. Unit tests: fresh confirmation → escalation allowed; stale → capped at tell; no
   confirmation → proxy behaviour (unchanged); privacy — the record holds a timestamp +
   call-index only, never content. `./scripts/test-backend.sh` green.

## Why (root cause / spec)

PR #19's replay oracle falsified the recency proxy at the real 5A reset points (speclib
`2whh9wno` → 93% "disposable" share in the +20% LOSE regime): **last-access bookkeeping cannot
observe whether the FUTURE task re-needs the refs — only the agent holding the task can.**
`decide()` therefore caps proxy-unlocked drops at L1 tell. This brief builds the only party
that can honestly answer the consent question a channel to answer it — which is what makes
L2 ask real and is the precondition for 6.8 L3 auto-act (auto-drop ONLY on explicit + runway,
never the proxy alone).

## Design notes (decided so the executor doesn't have to)

- State lives beside the ask/proc state: `<central>/state/disposable-<session_id>.json`
  (mirrors `ask-*.json` / `proc-*.json` conventions in `intervene.py`).
- The confirmation records `{confirmed_at_call, confirmed_at_ts}`; freshness = within
  `CONFIRM_TTL_CALLS` model calls AND `CONFIRM_TTL_MIN` minutes (pick ~10 calls / ~30 min,
  named constants, comment the reasoning).
- Merge rule in `intervention_for_session()`: if fresh confirmation exists, add a synthetic
  entry `{"explicit:session": "disposable_confirmed"}` to the LiveMonitor dict — do NOT
  overwrite per-block proxy verdicts (they still inform the message).
- The MCP tool registration follows the existing `toolbox.py` pattern (`TOOL_REGISTRY`);
  keep it toggleable like offload/handoff/compact.

## Constraints
- Inherit `GOALS/README.md`. `evaluate()`/`decide()` signatures unchanged — this brief only
  produces the input they already accept. Privacy invariant: metadata only.
- Do NOT touch the proxy classifier or the Gate 1 cap (one root cause per change; the cap is
  the safety line this channel threads through).

## Out of scope
- 6.8 L3 auto-act itself (needs this + a ratified contract + 6.7 outcomes evidence).
- The huge-block-only unlock experiment (separate brief; needs new fixture regimes + budget).

## Notes
- If PR #19 review overrules option 1, this brief's premise changes — re-check the contract
  before starting.
