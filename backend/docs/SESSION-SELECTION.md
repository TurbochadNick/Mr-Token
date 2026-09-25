# Session selection contract

There are two independent axes: **store** (which database was opened) and
**session** (which `trace` row inside that store was selected). Neither axis may
be inferred from a successful-looking report.

## Store

- `--db PATH` selects that explicit store.
- `--codex` selects the central Codex store and restricts a single-session
  selection to `source='codex'`; it never falls back to a Claude row.
- Without either flag, the command uses the current project's store.

The session-selecting CLI commands print `mrtoken: store: ...` on stdout before
their result. Failure to open it is `mrtoken: store unavailable: ...` and exits
2; a present store without the requested session exits 1; and `status`,
`handoff`, `why` or `explain` refusing an omitted session exits 3. The distinct codes are part of the contract so
callers can distinguish store, session, and caller-refusal failures.

## Session

An explicit id/prefix selects the newest matching row in the selected store.
If no matching row exists, the command reports `mrtoken: session unavailable`
instead of consulting another store or provider.

A caller that restricts a provider MUST pass `source` to `select_session()`;
its permissive default is only for callers whose documented contract permits all
providers in the selected store.

Omitted-session behaviour is deliberately command-specific:

- `why` and `explain` follow the same caller-session rule as `handoff` (below):
  an omitted id is the caller's own session, matched exactly within the
  permitted provider, never the newest row (which could expose another seat's
  session id, tokens, cost and tool names). With no caller identity they refuse
  with `mrtoken: <command> refused: ...` (exit 3). They print the selected
  session id, provider, and `implicit caller session`.
- `status` refuses an omitted session with a named reason; it must not regain a
  convenience default without an explicit contract change.
- `subagents` with no id is a Claude-parent fleet view, not a single-session
  selection. With an id it selects a Claude parent and states that restriction;
  a Codex-only request names the unsupported provider rather than looking empty.
- `handoff` selects an already-recorded session, then reads only that session's
  matching transcript for paste-ready detail. `handoff --codex` restricts the
  selected row to Codex and never ingests or updates the selected store. An
  omitted id means the CALLER's own session: `MRTOKEN_SESSION`, else
  `CLAUDE_CODE_SESSION_ID`, matched exactly (not as a prefix) within the
  permitted provider. It never falls back to the newest row: one project store
  is shared by every seat under that project root, so the newest row can belong
  to another seat, and handoff would then read that seat's transcript. With no
  caller identity, handoff refuses with a named reason (`mrtoken: handoff
  refused: ...`, exit 3); a caller id absent from the store is `session
  unavailable` (exit 1). The header names the selected session, provider, and
  `implicit caller session`. An explicit id remains a deliberate choice and may
  select any recorded session.

The MCP `handoff` tool is an UNTRUSTED entry point: its `session` is an id resolved only
within the caller's project bucket (never a path), and an omitted `session` is the
caller's own env session resolved the same way. It hands `build_handoff` that transcript's
session id, matched exactly, plus the verified transcript path. With no caller identity it
refuses; it never falls back to the newest transcript.

`report`, `list`, `fleet`, `export`, `savings`, `roi`, the UI, and the other MCP tools are
aggregate or separately scoped surfaces in this revision; they do not silently
resolve a single default trace.
