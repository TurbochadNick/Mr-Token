import { existsSync } from 'node:fs';
import { openDatabase } from '../db/client.js';
import { getSummary } from '../db/events.js';
import { generateDoctorPatches } from '../doctor/patches.js';
import { hasTokenTitheHooks } from '../adapters/claude-code/install.js';
import { defaultClaudeSettingsPath, defaultDbPath, defaultEventsPath, findProjectRoot } from '../utils/paths.js';

type DoctorOptions = {
  settings?: string;
  db?: string;
};

export function runDoctor(options: DoctorOptions): void {
  const projectRoot = findProjectRoot();
  const dbPath = options.db ?? defaultDbPath();
  const eventsPath = defaultEventsPath(projectRoot);
  const settingsPath = options.settings ?? defaultClaudeSettingsPath(projectRoot);
  const dbExists = existsSync(dbPath);
  const settingsExists = existsSync(settingsPath);
  const hooksInstalled = settingsExists ? hasTokenTitheHooks(settingsPath, dbPath, eventsPath) : false;

  console.log('Token Tithe Doctor');
  console.log('==================');
  console.log(`Node: ${process.version}`);
  console.log(`Project root: ${projectRoot}`);
  console.log(`Database: ${dbPath}`);
  console.log(`Database exists: ${dbExists ? 'yes' : 'no'}`);
  console.log(`Events JSONL: ${eventsPath}`);
  console.log(`Events JSONL exists: ${existsSync(eventsPath) ? 'yes' : 'no'}`);
  console.log(`Claude settings: ${settingsPath}`);
  console.log(`Claude settings exists: ${settingsExists ? 'yes' : 'no'}`);
  console.log(`Hooks installed: ${hooksInstalled ? 'yes' : 'no'}`);

  if (dbExists) {
    const db = openDatabase(dbPath);
    const summary = getSummary(db);
    db.close();
    console.log(`Collected events: ${summary.eventCount}`);
    console.log(`Estimated tokens: ${summary.totalTokens.toLocaleString()}`);
  }

  const patches = generateDoctorPatches(projectRoot, new Date(), { dbPath, settingsPath });

  console.log('');
  console.log('Safe patch bundle');
  console.log('=================');
  console.log(`Patch directory: ${patches.patchDir}`);
  console.log(`Patch diff: ${patches.diffPath}`);
  console.log(`Patch summary: ${patches.summaryPath}`);
  console.log('');
  console.log('Diff summary');
  console.log('------------');

  for (const file of patches.files) {
    console.log(`${file.status.toUpperCase()} ${file.targetPath}`);
    console.log(`  ${file.summary}`);
    console.log(`  proposed: ${file.patchPath}`);
  }

  console.log('');
  console.log('Review these patches manually before applying. token-tithe doctor did not modify live project files.');
}
