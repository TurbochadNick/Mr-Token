import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { openDatabase } from '../src/db/client.js';
import { insertNormalizedEvent } from '../src/db/events.js';
import { exportMarkdownReport, getSetupStatus, getUiData, runUiDoctor, runUiInit } from '../src/local-ui/api.js';

describe('Mr Token UI API', () => {
  it('returns dashboard, findings, events, and latest doctor patch data', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-ui-'));
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const patchDir = join(projectRoot, '.token-tithe', 'patches', '20260525-101112');
    mkdirSync(patchDir, { recursive: true });
    writeFileSync(join(patchDir, 'SUMMARY.md'), '# summary\n', 'utf8');
    writeFileSync(join(patchDir, 'patch.diff'), 'diff --git a/CLAUDE.md b/CLAUDE.md\n', 'utf8');

    const db = openDatabase(dbPath);
    insertNormalizedEvent(db, {
      timestamp: '2026-05-25T10:00:00.000Z',
      projectPath: projectRoot,
      sessionId: 's1',
      eventType: 'PostToolUse',
      toolName: 'Bash',
      filePath: null,
      command: 'pnpm test',
      promptLength: 0,
      stdoutLength: 20000,
      stderrLength: 0,
      resultLength: 0,
      estimatedTokens: 5000,
      rawEvent: {
        session_id: 's1',
        hook_event_name: 'PostToolUse',
        cwd: projectRoot,
        tool_name: 'Bash',
        tool_input: { command: 'pnpm test' },
        tool_response: { stdout: 'x'.repeat(20000) }
      }
    });
    db.close();

    const data = getUiData(projectRoot, dbPath);

    expect(data.summary).toMatchObject({
      totalEstimatedTokens: 5000,
      sessions: 1,
      prompts: 0,
      toolCalls: 1
    });
    expect(data.summary.estimatedSavingsRange[1]).toBeGreaterThan(0);
    expect(data.findings[0]?.category).toBe('Huge bash/tool outputs');
    expect(data.events[0]).toMatchObject({
      eventType: 'PostToolUse',
      toolName: 'Bash',
      estimatedTokens: 5000,
      command: 'pnpm test'
    });
    expect(data.doctorLatest?.summary).toContain('# summary');
    expect(data.doctorLatest?.diff).toContain('diff --git');
  });

  it('supports setup, init, doctor, and report API helpers', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-ui-actions-'));
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');

    expect(getSetupStatus(projectRoot, dbPath)).toMatchObject({
      projectRoot,
      databaseExists: false,
      eventsJsonlExists: false,
      claudeSettingsExists: false,
      hooksInstalled: false
    });

    const init = runUiInit(projectRoot, dbPath);
    expect(init.dbPath).toBe(dbPath);
    expect(getSetupStatus(projectRoot, dbPath)).toMatchObject({
      databaseExists: true,
      eventsJsonlExists: true,
      claudeSettingsExists: true,
      hooksInstalled: true
    });

    const doctor = runUiDoctor(projectRoot, dbPath);
    expect(doctor.patchDir).toContain('.token-tithe');
    expect(doctor.summaryPath.endsWith('SUMMARY.md')).toBe(true);
    expect(doctor.diffPath.endsWith('patch.diff')).toBe(true);
    expect(doctor.latest?.summary).toContain('token-tithe doctor patch bundle');

    const report = exportMarkdownReport(projectRoot, dbPath);
    expect(report).toContain('# Mr Token Audit Report');
    expect(report).toContain('## Summary');
    expect(report).toContain('## Doctor');
  });
});
