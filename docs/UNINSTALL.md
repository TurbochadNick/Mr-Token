# Uninstall / turn off MR Token

## One command (reverses `init`)

```bash
mrtoken-transcript uninstall
```

This removes everything `init` added and **preserves all your other Claude Code
settings**, backing up each settings file first:

- the project-local **Stop** hook from `.claude/settings.local.json`
- the **statusLine** bar and the **UserPromptSubmit** + **PreCompact** hooks from
  `~/.claude/settings.json`
- the `/mr-handoff`, `/mr-status`, `/mr-why` skills from `~/.claude/skills/`
  (keep them with `--keep-skills`)

Run it once per project you ran `init` in (the global bits are only removed once).

Nothing runs in the background, so once the hooks are removed, MR Token does
nothing at all.

## Remove the local data

The metadata ledger is just a folder; delete it per project:

```bash
rm -rf .token-tithe/
```

## Uninstall the package

```bash
pip uninstall mrtoken
```

## Restore a settings backup

`init` and `uninstall` write a timestamped backup next to any settings file they
change:

```text
~/.claude/settings.json.mrtoken-bak.<timestamp>
.claude/settings.local.json.mrtoken-bak.<timestamp>
```

Restore one by copying it back over the original.
