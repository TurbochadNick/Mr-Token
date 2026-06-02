# Security Notes

## Localhost Only

`token-tithe ui` binds to `127.0.0.1`, not `0.0.0.0`.

## No Arbitrary Shell Execution

The UI does not expose an endpoint for arbitrary shell commands.

## Write Scope

Write operations are limited to:

- `.token-tithe/`
- `.token-tithe/patches/`
- `.claude/settings.local.json`

## Patch Safety

Doctor generates patch proposals only. It never applies patches automatically.

## Known Alpha Risks

- Hook payloads may contain sensitive snippets from Claude Code events.
- The local UI has no auth because it is localhost-only.
- Diagnosis is heuristic and may produce false positives.
- Users should review `.claude/settings.local.json` changes before using in sensitive repositories.
