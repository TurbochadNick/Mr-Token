import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { openDatabase } from '../../db/client.js';
import { insertNormalizedEvent } from '../../db/events.js';
import type { NormalizedHookEvent } from '../../schemas/events.js';
import { claudeHookEventSchema } from './events.js';
import { normalizeHookEvent } from './normalize.js';

export type HandleHookEventOptions = {
  rawJson: string;
  dbPath: string;
  eventsPath: string;
  hookEvent?: string;
  projectPath?: string;
};

export function handleHookEvent(options: HandleHookEventOptions): { id: number; event: NormalizedHookEvent } {
  const raw = parseJsonObject(options.rawJson);
  const parsed = claudeHookEventSchema.parse({
    ...raw,
    hook_event_name: typeof raw.hook_event_name === 'string' ? raw.hook_event_name : options.hookEvent
  });
  const event = normalizeHookEvent({
    event: parsed,
    hookEvent: options.hookEvent,
    projectPath: options.projectPath
  });

  appendNormalizedJsonl(options.eventsPath, event);

  const db = openDatabase(options.dbPath);
  const id = insertNormalizedEvent(db, event);
  db.close();

  return { id, event };
}

function parseJsonObject(rawJson: string): Record<string, unknown> {
  const parsed = JSON.parse(rawJson) as unknown;
  return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
}

function appendNormalizedJsonl(eventsPath: string, event: NormalizedHookEvent): void {
  mkdirSync(dirname(eventsPath), { recursive: true });
  appendFileSync(eventsPath, `${JSON.stringify(event)}\n`, 'utf8');
}
