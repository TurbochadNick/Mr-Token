import { closeSync, mkdirSync, openSync } from 'node:fs';
import { openDatabase } from '../db/client.js';
import { installClaudeHooks } from '../hooks/install.js';
import { defaultClaudeSettingsPath, defaultDataDir, defaultDbPath, defaultEventsPath, findProjectRoot } from '../utils/paths.js';

type InitOptions = {
  settings?: string;
  db?: string;
};

export function runInit(options: InitOptions): void {
  const projectRoot = findProjectRoot();
  const dataDir = defaultDataDir(projectRoot);
  const dbPath = options.db ?? defaultDbPath();
  const eventsPath = defaultEventsPath(projectRoot);
  const settingsPath = options.settings ?? defaultClaudeSettingsPath(projectRoot);

  mkdirSync(dataDir, { recursive: true });
  closeSync(openSync(eventsPath, 'a'));

  const db = openDatabase(dbPath);
  db.close();

  const result = installClaudeHooks({ settingsPath, dbPath, eventsPath });

  console.log('token-tithe initialized');
  console.log(`Project root: ${projectRoot}`);
  console.log(`Data directory: ${dataDir}`);
  console.log(`Events JSONL: ${eventsPath}`);
  console.log(`Database: ${dbPath}`);
  console.log(`Claude settings: ${result.path}`);
  if (result.backupPath) {
    console.log(`Settings backup: ${result.backupPath}`);
  }
  console.log(`Hooks: ${result.events.join(', ')}`);
  console.log(result.changed ? 'Hook config updated.' : 'Hook config already up to date.');
}
