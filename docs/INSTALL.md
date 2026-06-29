# Install Mr Token

This is the beta install path for testers. It installs the Python
`mrtoken-transcript` backend, Claude Code hooks, the terminal HUD, and bundled
MR Token skills.

## Requirements

- Python 3.11 or newer
- Claude Code
- Git

On macOS, bare `python3` may be Apple's Python 3.9. `install.sh` searches for
`python3.13`, `python3.12`, `python3.11`, then `python3`, and stops if none are
new enough.

## Install From Clone

```bash
git clone <repo-url> mr_token
cd mr_token
./install.sh
```

The installer:

- installs the backend in editable mode when `pip` is available;
- creates the local metadata DB for the current project;
- writes Claude Code hooks and statusLine settings to `~/.claude/settings.json`;
- installs MR Token skills into `~/.claude/skills/`;
- installs skills into `~/.codex/skills/` and the Stop hook into
  `~/.codex/hooks.json` when `~/.codex/` exists.

It backs up settings before editing and preserves unrelated hooks/settings.

## Verify

```bash
mrtoken-transcript --version
mrtoken-transcript status
```

Use Claude Code normally in a terminal. You should see the `mr` status line and
turn-boundary nudges when a session grows or a rule fires.

## Optional TypeScript UI

The TypeScript CLI/dashboard under `src/` and `web/` is not the primary beta
surface. Use it only when intentionally testing dashboard work:

```bash
pnpm install
pnpm build
pnpm link --global
token-tithe ui
```

The UI binds to `127.0.0.1`. The TS `mrtoken`/`token-tithe` commands include
license/login plumbing, so this is a different onboarding path from the local
backend beta.

## Uninstall

```bash
mrtoken-transcript uninstall
```

This removes MR Token's Claude hooks/statusLine/skills and leaves local
`.token-tithe` data in place for manual deletion.
