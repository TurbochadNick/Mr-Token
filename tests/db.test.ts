import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { openDatabase } from '../src/db/client.js';
import { getSummary, insertEvent, listRecentEvents } from '../src/db/events.js';

describe('event database', () => {
  it('stores hook events and summarizes usage', () => {
    const dir = mkdtempSync(join(tmpdir(), 'token-tithe-'));
    const db = openDatabase(join(dir, 'test.db'));

    const id = insertEvent(db, {
      session_id: 's1',
      hook_event_name: 'UserPromptSubmit',
      prompt: 'Write a test for this CLI.'
    });

    const summary = getSummary(db);
    const recent = listRecentEvents(db, 5);
    db.close();

    expect(id).toBe(1);
    expect(summary.eventCount).toBe(1);
    expect(summary.promptCount).toBe(1);
    expect(summary.totalTokens).toBeGreaterThan(0);
    expect(recent[0]?.sessionId).toBe('s1');
  });
});
