# Install Mr Token

## Requirements

- Node.js 22+
- pnpm recommended
- Claude Code CLI for hook capture

## Install From Clone

```bash
git clone <repo-url>
cd token-tithe
pnpm install
pnpm build
npm link
```

## npm Install Path

When published:

```bash
npm install -g token-tithe
```

For this pilot, prefer the git clone path above.

## Run The UI

```bash
token-tithe ui
```

Optional:

```bash
token-tithe ui --port 4317
token-tithe ui --no-open
```

Open:

```text
http://localhost:4317
```

Verify the Setup page shows the project root, database status, events JSONL status, Claude settings status, and hook status.

## Troubleshooting Permission Denied

If `token-tithe` is not found or permission is denied:

```bash
npm unlink -g token-tithe
npm link
which token-tithe
token-tithe --help
```

If port binding fails, choose another local port:

```bash
token-tithe ui --port 4321
```

If Claude settings cannot be written, check project permissions for `.claude/settings.local.json`.
