# Data directory contract (TS + Python)

The single source of truth for where MR Token stores `token-tithe.db` and
`events.jsonl`. Both sides implement this IDENTICALLY:

- TypeScript: `src/utils/paths.ts`
- Python: `backend/mrtoken/datadir.py`

If you change one, change the other in the same commit, or the shared DB will
drift (TS writes one location, Python another).

## Why this exists

The old resolution was per-cwd: it walked up for `.git`/`package.json`, and if it
found none it returned the cwd itself, so `.token-tithe/` got created wherever an
agent happened to run. In practice it scattered into `~`, `~/Documents`,
`~/Downloads`, `~/Music/...`, and several unrelated git repos. This contract fixes
the fallback while preserving the local-first privacy story.

## Resolution algorithm (highest precedence first)

1. **Explicit path** (`--db` / `--events` flags): use exactly as given.
2. **DB env override** (`TOKEN_TITHE_DB` or `MRTOKEN_DB`): use exactly as given.
   Both sides honor both names.
3. **`MRTOKEN_DATA_DIR` is set** (full-central opt-in): use
   `<MRTOKEN_DATA_DIR>/projects/<key>/`.
4. **cwd is inside a real project** (an ancestor has `.git`, `package.json`, or
   `pyproject.toml`): use `<project-root>/.token-tithe/`. **This is the default**
   and keeps each project's data local (the privacy selling point).
5. **cwd is NOT a project** (the old scatter case): use
   `<central-default>/projects/<key>/`. NEVER write into the cwd.

Within a chosen data dir: the DB is `token-tithe.db`, events are `events.jsonl`.

## The default scoping decision (for Zach + Nick)

Per-project stays the DEFAULT for real projects (privacy intact). The two changes
are: (a) the non-project fallback now goes central instead of scattering, and (b)
full-central is an opt-in via `MRTOKEN_DATA_DIR`. If you want central to be the
default for everything, that is a one-line policy change here, but it weakens the
"data stays in this project" story, so it is opt-in for now.

## Central default location

- `$XDG_DATA_HOME/token-tithe` if `XDG_DATA_HOME` is set,
- else `~/.mrtoken/data` (consistent with the existing `~/.mrtoken/config.json`
  auth precedent in `src/auth/config.ts`).

## Project key (must match byte-for-byte across TS and Python)

Given an absolute project/cwd path:

1. `abs` = absolute path (`os.path.abspath` / `path.resolve`), symlinks NOT
   resolved, trailing separators stripped.
2. `slug` = `basename(abs)` lowercased, every run of non-`[a-z0-9]` replaced with
   `-`, leading/trailing `-` stripped; if empty, `root`.
3. `hash` = first 8 hex chars of `sha256(abs)` (utf-8 bytes).
4. key = `"<slug>-<hash>"`.

Example: `/Users/zach/My Proj` -> `my-proj-<8hex>`. Same input gives the same key
on both sides, so TS and Python resolve to the same central path.

## What does NOT move

- `.claude/settings.local.json` stays project-local (`defaultClaudeSettingsPath`).
- The shared-DB contract is unchanged: TS owns `events`; Python owns
  `trace`/`model_call`/`tool_call`/`context_block`/`recommendation` +
  `session_summary`; joinable on `session_id`. Per-project scoping is preserved
  because each project (or each cwd, when central) gets its own keyed DB.
- Explicit overrides (`--db`/`--events`, `TOKEN_TITHE_DB`) keep working; the watch
  hook that passes them explicitly is unaffected.

## Migration

`mrtoken-transcript migrate-data` finds every `.token-tithe/token-tithe.db`,
classifies it, and relocates the scattered (non-project) ones into the central
store, keyed by their location. Real per-project DBs are left in place (they are
already the correct default location). Dry-run by default; `--apply` to move.
Conflicts (a central destination already exists) are reported and skipped, never
overwritten, so no historical data is lost.
