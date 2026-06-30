# Updating MR Token (pilot pipeline)

While MR Token is distributed by git clone + editable pip install, updates are a
pull, not a reinstall. This is deliberately simple for the pilot: no release
server, no auto-updater (those come later, if a wider audience warrants them).

## For a tester: get the latest

From the repo you cloned:

```bash
./update.sh
```

That runs `git pull`, a quick `pip install -e backend/` (no-op unless something
structural changed), `mrtoken-transcript init` to re-sync the `/mr-*` skills and
hooks, and prints the version you landed on.

Prefer to do it by hand:

```bash
git pull --ff-only
mrtoken-transcript init      # re-copies skills, confirms hooks + statusLine
```

If you ever see an import error after an update, the dependency set changed:
re-run `pip install -e backend/`.

## What a pull actually updates

| Part | Updated by |
|---|---|
| Python backend (rules, parser, HUD, commands) | `git pull` — live immediately (editable install) |
| `/mr-handoff`, `/mr-status`, `/mr-why` skills | `mrtoken-transcript init` (overwrites with the current copy) |
| statusLine + Stop/UserPromptSubmit/PreCompact hooks | `mrtoken-transcript init` (idempotent; preserves your other settings) |

## Knowing what version you (or a tester) are on

```bash
mrtoken-transcript --version
```

Every `mrtoken-transcript export` also stamps `tool_version` into the JSON, so a
tester's redacted export self-identifies which build produced it. Useful when
correlating a bug report or a beta log to a specific version.

## For the maintainer: cutting a tester-facing release

1. Make the change, land it on `main`.
2. Bump the version in **both** `backend/mrtoken/__init__.py` (`__version__`, the
   runtime source) and `backend/pyproject.toml` (`version`). Keep them equal.
3. Push. Tell testers to run `./update.sh`.

Versioning is plain semver-ish: bump the minor for new behavior testers should
notice, the patch for fixes. The current beta build is `0.5.8`.
