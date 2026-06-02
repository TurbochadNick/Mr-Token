import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

export const HOOK_EVENTS = ['UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'PreCompact', 'PostCompact'] as const;

type ClaudeSettings = {
  hooks?: Record<string, Array<{ matcher?: string; hooks: Array<{ type: 'command'; command: string }> }>>;
  [key: string]: unknown;
};

export type { ClaudeSettings };

type InstallClaudeHooksOptions = {
  settingsPath: string;
  dbPath: string;
  eventsPath: string;
};

export function installClaudeHooks(options: InstallClaudeHooksOptions): {
  path: string;
  backupPath: string | null;
  changed: boolean;
  events: string[];
} {
  const { settingsPath, dbPath, eventsPath } = options;
  mkdirSync(dirname(settingsPath), { recursive: true });
  const settings = readSettings(settingsPath);
  const previous = JSON.stringify(settings, null, 2);
  const nextSettings = mergeTokenTitheHooks(settings, dbPath, eventsPath);
  const next = JSON.stringify(nextSettings, null, 2);
  const changed = previous !== next;
  const backupPath = changed && existsSync(settingsPath) ? createBackup(settingsPath) : null;

  if (changed) {
    writeFileSync(settingsPath, `${next}\n`, 'utf8');
  }

  return {
    path: settingsPath,
    backupPath,
    changed,
    events: [...HOOK_EVENTS]
  };
}

export function mergeTokenTitheHooks(settings: ClaudeSettings, dbPath: string, eventsPath: string): ClaudeSettings {
  const nextSettings: ClaudeSettings = structuredClone(settings);

  nextSettings.hooks ??= {};

  for (const eventName of HOOK_EVENTS) {
    const entries = nextSettings.hooks[eventName] ?? [];
    const command = buildHookCommand({ eventName, dbPath, eventsPath });
    const hasHook = entries.some((entry) =>
      entry.hooks.some((hook) => hook.type === 'command' && hook.command === command)
    );

    if (!hasHook) {
      entries.push({
        matcher: '*',
        hooks: [{ type: 'command', command }]
      });
    }

    nextSettings.hooks[eventName] = entries;
  }

  return nextSettings;
}

export function hasTokenTitheHooks(settingsPath: string, dbPath: string, eventsPath: string): boolean {
  const settings = readSettings(settingsPath);

  return HOOK_EVENTS.every((eventName) =>
    settings.hooks?.[eventName]?.some((entry) =>
      entry.hooks.some(
        (hook) => hook.type === 'command' && hook.command === buildHookCommand({ eventName, dbPath, eventsPath })
      )
    )
  );
}

export function buildHookCommand({
  eventName,
  dbPath,
  eventsPath
}: {
  eventName: string;
  dbPath: string;
  eventsPath: string;
}): string {
  return [
    'token-tithe',
    'watch',
    '--stdin',
    '--hook-event',
    shellQuote(eventName),
    '--db',
    shellQuote(dbPath),
    '--events',
    shellQuote(eventsPath)
  ].join(' ');
}

function readSettings(settingsPath: string): ClaudeSettings {
  try {
    return JSON.parse(readFileSync(settingsPath, 'utf8')) as ClaudeSettings;
  } catch {
    return {};
  }
}

function createBackup(settingsPath: string): string {
  const backupPath = `${settingsPath}.${timestamp()}.bak`;
  copyFileSync(settingsPath, backupPath);
  return backupPath;
}

function timestamp(): string {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}
