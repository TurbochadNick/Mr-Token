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
their result. Failure to open it is `mrtoken: store unavailable: ...`.

## Session

An explicit id/prefix selects the newest matching row in the selected store.
If no matching row exists, the command reports `mrtoken: session unavailable`
instead of consulting another store or provider.

Omitted-session behaviour is deliberately command-specific:

- `why` and `explain` select the newest permitted row and print the selected
  session id, provider, and that the choice was implicit.
- `status` refuses an omitted session with a named reason; it must not regain a
  convenience default without an explicit contract change.
- `subagents` with no id is a Claude-parent fleet view, not a single-session
  selection. With an id it selects a Claude parent and states that restriction;
  a Codex-only request names the unsupported provider rather than looking empty.

`report`, `list`, `fleet`, `export`, `savings`, `roi`, the UI, and MCP tools are
aggregate or separately scoped surfaces in this revision; they do not silently
resolve a single default trace. Codex transcript handoff parity remains Slice D.
