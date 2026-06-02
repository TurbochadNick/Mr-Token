import { initializeProject } from '../core/init.js';

type InitOptions = {
  settings?: string;
  db?: string;
};

export function runInit(options: InitOptions): void {
  const result = initializeProject({ settingsPath: options.settings, dbPath: options.db });

  console.log('token-tithe initialized');
  console.log(`Project root: ${result.projectRoot}`);
  console.log(`Data directory: ${result.dataDir}`);
  console.log(`Events JSONL: ${result.eventsPath}`);
  console.log(`Database: ${result.dbPath}`);
  console.log(`Claude settings: ${result.settingsPath}`);
  if (result.backupPath) {
    console.log(`Settings backup: ${result.backupPath}`);
  }
  console.log(`Hooks: ${result.hooks.join(', ')}`);
  console.log(result.hooksChanged ? 'Hook config updated.' : 'Hook config already up to date.');
}
