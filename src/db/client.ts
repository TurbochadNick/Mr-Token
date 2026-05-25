import Database from 'better-sqlite3';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { schemaSql } from './schema.js';

export type DbClient = Database.Database;

export function openDatabase(dbPath: string): DbClient {
  mkdirSync(dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(schemaSql);
  migrateEventsTable(db);
  return db;
}

function migrateEventsTable(db: DbClient): void {
  const columns = new Set(
    (db.prepare('pragma table_info(events)').all() as Array<{ name: string }>).map((column) => column.name)
  );
  const migrations: Array<[string, string]> = [
    ['timestamp', 'alter table events add column timestamp text'],
    ['project_path', 'alter table events add column project_path text'],
    ['event_type', 'alter table events add column event_type text'],
    ['file_path', 'alter table events add column file_path text'],
    ['command', 'alter table events add column command text'],
    ['prompt_length', 'alter table events add column prompt_length integer not null default 0'],
    ['stdout_length', 'alter table events add column stdout_length integer not null default 0'],
    ['stderr_length', 'alter table events add column stderr_length integer not null default 0'],
    ['result_length', 'alter table events add column result_length integer not null default 0']
  ];

  for (const [name, sql] of migrations) {
    if (!columns.has(name)) {
      db.exec(sql);
    }
  }

  db.exec(`
    update events set event_type = event_name where event_type is null;
    update events set project_path = cwd where project_path is null;
    update events set timestamp = created_at where timestamp is null;
  `);
}
