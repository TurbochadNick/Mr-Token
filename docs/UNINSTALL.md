# Uninstall Mr Token

## Remove Local Data

From the project root:

```bash
rm -rf .token-tithe/
```

## Remove Claude Hooks

Open:

```text
.claude/settings.local.json
```

Remove hook entries whose command starts with:

```text
token-tithe watch --stdin
```

Keep unrelated Claude settings and hooks.

## Restore Backup

If `token-tithe init` created a backup, it will be next to the settings file:

```text
.claude/settings.local.json.<timestamp>.bak
```

Restore it manually:

```bash
cp .claude/settings.local.json.<timestamp>.bak .claude/settings.local.json
```

## Unlink CLI

```bash
npm unlink -g token-tithe
```

## Optional: Delete Clone

If installed from a git clone, delete the cloned `token-tithe` repository after unlinking.
