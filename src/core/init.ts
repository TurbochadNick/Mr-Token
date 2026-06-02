import { closeSync, mkdirSync, openSync } from 'node:fs';
import { openDatabase } from '../db/client.js';
import { installClaudeHooks } from '../adapters/claude-code/install.js';
import {
  defaultClaudeSettingsPath,
  defaultDataDir,
  defaultDbPath,
  defaultEventsPath,
  findProjectRoot
} from '../utils/paths.js';

export type InitProjectOptions = {
  projectRoot?: string;
  settingsPath?: string;
  dbPath?: string;
};

export type InitProjectResult = {
  projectRoot: string;
  dataDir: string;
  dbPath: string;
  eventsPath: string;
  settingsPath: string;
  backupPath: string | null;
  hooksChanged: boolean;
  hooks: string[];
};

export function initializeProject(options: InitProjectOptions = {}): InitProjectResult {
  const projectRoot = options.projectRoot ?? findProjectRoot();
  const dataDir = defaultDataDir(projectRoot);
  const dbPath = options.dbPath ?? defaultDbPath(projectRoot);
  const eventsPath = defaultEventsPath(projectRoot);
  const settingsPath = options.settingsPath ?? defaultClaudeSettingsPath(projectRoot);

  mkdirSync(dataDir, { recursive: true });
  closeSync(openSync(eventsPath, 'a'));

  const db = openDatabase(dbPath);
  db.close();

  const result = installClaudeHooks({ settingsPath, dbPath, eventsPath });

  return {
    projectRoot,
    dataDir,
    dbPath,
    eventsPath,
    settingsPath,
    backupPath: result.backupPath,
    hooksChanged: result.changed,
    hooks: result.events
  };
}
