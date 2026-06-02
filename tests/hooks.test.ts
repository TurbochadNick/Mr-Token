import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildHookCommand, hasTokenTitheHooks, installClaudeHooks } from '../src/adapters/claude-code/install.js';

describe('Claude hook installer', () => {
  it('installs token-tithe command hooks', () => {
    const dir = mkdtempSync(join(tmpdir(), 'token-tithe-hooks-'));
    const settingsPath = join(dir, 'settings.local.json');
    const dbPath = join(dir, '.token-tithe', 'token-tithe.db');
    const eventsPath = join(dir, '.token-tithe', 'events.jsonl');

    const result = installClaudeHooks({ settingsPath, dbPath, eventsPath });
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8')) as {
      hooks: Record<string, Array<{ hooks: Array<{ command: string }> }>>;
    };

    expect(result.changed).toBe(true);
    expect(result.backupPath).toBeNull();
    expect(hasTokenTitheHooks(settingsPath, dbPath, eventsPath)).toBe(true);
    expect(settings.hooks.UserPromptSubmit[0]?.hooks[0]?.command).toBe(
      buildHookCommand({ eventName: 'UserPromptSubmit', dbPath, eventsPath })
    );
    expect(Object.keys(settings.hooks)).toEqual(
      expect.arrayContaining(['UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'PreCompact', 'PostCompact'])
    );
  });

  it('preserves existing settings and hook entries while creating a backup', () => {
    const dir = mkdtempSync(join(tmpdir(), 'token-tithe-hooks-'));
    const settingsPath = join(dir, 'settings.local.json');
    const dbPath = join(dir, '.token-tithe', 'token-tithe.db');
    const eventsPath = join(dir, '.token-tithe', 'events.jsonl');

    writeFileSync(
      settingsPath,
      JSON.stringify(
        {
          permissions: { allow: ['Bash(git status)'] },
          hooks: {
            UserPromptSubmit: [
              {
                matcher: '*',
                hooks: [{ type: 'command', command: 'echo existing' }]
              }
            ]
          }
        },
        null,
        2
      ),
      'utf8'
    );

    const result = installClaudeHooks({ settingsPath, dbPath, eventsPath });
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8')) as {
      permissions: { allow: string[] };
      hooks: Record<string, Array<{ hooks: Array<{ command: string }> }>>;
    };
    const backups = readdirSync(dir).filter((file) => file.startsWith('settings.local.json.') && file.endsWith('.bak'));

    expect(result.changed).toBe(true);
    expect(result.backupPath).not.toBeNull();
    expect(backups).toHaveLength(1);
    expect(settings.permissions.allow).toEqual(['Bash(git status)']);
    expect(settings.hooks.UserPromptSubmit[0]?.hooks[0]?.command).toBe('echo existing');
    expect(settings.hooks.UserPromptSubmit[1]?.hooks[0]?.command).toBe(
      buildHookCommand({ eventName: 'UserPromptSubmit', dbPath, eventsPath })
    );
    expect(settings.hooks.PreCompact[0]?.hooks[0]?.command).toBe(
      buildHookCommand({ eventName: 'PreCompact', dbPath, eventsPath })
    );
  });
});
