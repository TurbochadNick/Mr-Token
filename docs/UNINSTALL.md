# Uninstall / turn off MR Token

## One command (reverses `init`)

```bash
mrtoken-transcript uninstall
```

This removes everything `init` added and **preserves all your other Claude Code
settings**, backing up each settings file first:

- any legacy project-local **Stop** hook from `.claude/settings.local.json`
- the global **Stop**, **UserPromptSubmit**, and **PreCompact** hooks from
  `~/.claude/settings.json`
- the global **statusLine** bar from `~/.claude/settings.json`
- the `/mr-handoff`, `/mr-status`, `/mr-why`, and related MR Token skills from `~/.claude/skills/`
- the Codex Stop hook from `~/.codex/hooks.json`, when present
- the MR Token Codex skills from `~/.codex/skills/`, when present

Use `--keep-skills` to remove hooks/statusLine but leave the Claude/Codex skills
installed.

Run it once per project you ran `init` in (the global bits are only removed once).

Nothing runs in the background, so once the hooks are removed, MR Token does
nothing at all.

## Remove the local data

The metadata ledger is local. Delete it per project:

```bash
rm -rf .token-tithe/
```

Central MR Token state, savings/outcomes, and Codex aggregate data live under:

```text
~/.mrtoken/data/
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
