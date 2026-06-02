import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

export function findProjectRoot(startDir = process.cwd()): string {
  let current = resolve(startDir);

  while (true) {
    if (existsSync(join(current, '.git')) || existsSync(join(current, 'package.json'))) {
      return current;
    }

    const parent = dirname(current);

    if (parent === current) {
      return resolve(startDir);
    }

    current = parent;
  }
}

export function defaultDataDir(projectRoot = findProjectRoot()): string {
  return join(projectRoot, '.token-tithe');
}

export function defaultDbPath(projectRoot = findProjectRoot()): string {
  return process.env.TOKEN_TITHE_DB ?? join(defaultDataDir(projectRoot), 'token-tithe.db');
}

export function defaultEventsPath(projectRoot = findProjectRoot()): string {
  return join(defaultDataDir(projectRoot), 'events.jsonl');
}

export function defaultClaudeSettingsPath(projectRoot = findProjectRoot()): string {
  return join(projectRoot, '.claude', 'settings.local.json');
}
