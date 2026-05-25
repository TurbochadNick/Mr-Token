import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { openDatabase } from '../src/db/client.js';
import { listRecentEvents } from '../src/db/events.js';
import { handleHookEvent } from '../src/hooks/handler.js';
import { normalizeHookEvent } from '../src/hooks/normalize.js';

describe('hook handler', () => {
  it('normalizes prompt events into JSONL and SQLite', () => {
    const dir = mkdtempSync(join(tmpdir(), 'token-tithe-handler-'));
    const dbPath = join(dir, '.token-tithe', 'events.db');
    const eventsPath = join(dir, '.token-tithe', 'events.jsonl');
    const rawJson = readFixture('user-prompt.json');

    const { id, event } = handleHookEvent({ rawJson, dbPath, eventsPath });
    const jsonl = readFileSync(eventsPath, 'utf8').trim().split('\n');
    const jsonlEvent = JSON.parse(jsonl[0] ?? '{}') as typeof event;
    const db = openDatabase(dbPath);
    const rows = listRecentEvents(db, 1);
    db.close();

    expect(id).toBe(1);
    expect(jsonl).toHaveLength(1);
    expect(jsonlEvent.eventType).toBe('UserPromptSubmit');
    expect(jsonlEvent.projectPath).toBe('/tmp/example-project');
    expect(jsonlEvent.sessionId).toBe('session-123');
    expect(jsonlEvent.promptLength).toBe(49);
    expect(jsonlEvent.estimatedTokens).toBe(13);
    expect(rows[0]?.eventType).toBe('UserPromptSubmit');
    expect(rows[0]?.projectPath).toBe('/tmp/example-project');
    expect(rows[0]?.promptLength).toBe(49);
  });

  it('extracts tool file paths, commands, and output lengths', () => {
    const preTool = normalizeHookEvent({
      event: JSON.parse(readFixture('pre-tool-use.json')),
      timestamp: '2026-05-25T00:00:00.000Z'
    });
    const postTool = normalizeHookEvent({
      event: JSON.parse(readFixture('post-tool-use.json')),
      timestamp: '2026-05-25T00:00:00.000Z'
    });

    expect(preTool.eventType).toBe('PreToolUse');
    expect(preTool.toolName).toBe('Bash');
    expect(preTool.command).toBe('pnpm test');
    expect(preTool.estimatedTokens).toBe(3);
    expect(postTool.toolName).toBe('Read');
    expect(postTool.filePath).toBe('src/index.ts');
    expect(postTool.stdoutLength).toBe(17);
    expect(postTool.stderrLength).toBe(0);
    expect(postTool.resultLength).toBe(14);
    expect(postTool.rawEvent).toHaveProperty('unknown_future_field');
  });

  it('is tolerant of sparse events and uses the hook event option', () => {
    const normalized = normalizeHookEvent({
      event: {},
      hookEvent: 'PreCompact',
      projectPath: '/tmp/project',
      timestamp: '2026-05-25T00:00:00.000Z'
    });

    expect(normalized.eventType).toBe('PreCompact');
    expect(normalized.projectPath).toBe('/tmp/project');
    expect(normalized.sessionId).toBeNull();
    expect(normalized.toolName).toBeNull();
    expect(normalized.promptLength).toBe(0);
    expect(normalized.estimatedTokens).toBe(1);
  });
});

function readFixture(name: string): string {
  return readFileSync(join(import.meta.dirname, 'fixtures', name), 'utf8');
}
