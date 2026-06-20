import { describe, expect, it } from 'vitest';
import { diagnoseFuel } from '../src/diagnosis/diagnose.js';
import { calculateFuelScore } from '../src/diagnosis/scoring.js';
import { exportMarkdownReport } from '../src/local-ui/api.js';
import type { StoredEvent } from '../src/schemas/events.js';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

describe('fuel diagnosis', () => {
  it('scores against REAL totals when provided, not estimated findings', () => {
    const report = diagnoseFuel({
      projectRoot: '/tmp/p',
      events: [event({ stdoutLength: 20000, estimatedTokens: 5000, toolName: 'Bash', eventType: 'PostToolUse' })],
      realTotalTokens: 1000,
      realWasteTokens: 100
    });
    expect(report.fuelScore).toBe(90); // 100 - 100/1000
    expect(report.burnProfile.wastePercentage).toBe(10);
    expect(report.burnProfile.suspectedWasteTokens).toBe(100);
    expect(report.burnProfile.confidence).toBe('high');
  });

  it('detects huge tool output', () => {
    const report = diagnoseFuel({ projectRoot: '/tmp/p', events: [event({ stdoutLength: 20000, estimatedTokens: 5000, toolName: 'Bash', eventType: 'PostToolUse' })] });
    expect(report.findings[0]?.category).toBe('Huge Tool Output');
  });

  it('detects repeated instructions', () => {
    const prompt = 'Always use the same careful process and repeat these stable instructions. '.repeat(3);
    const report = diagnoseFuel({ projectRoot: '/tmp/p', events: [event({ id: 1, promptText: prompt, promptLength: prompt.length }), event({ id: 2, promptText: prompt, promptLength: prompt.length })] });
    expect(report.findings.some((finding) => finding.category === 'Repeated Instructions')).toBe(true);
  });

  it('detects broad prompt and missing acceptance criteria', () => {
    const report = diagnoseFuel({ projectRoot: '/tmp/p', events: [event({ promptText: 'Please improve and optimize everything.', promptLength: 39 })] });
    expect(report.findings.some((finding) => finding.category === 'Broad Prompt')).toBe(true);
    expect(report.findings.some((finding) => finding.category === 'Missing Acceptance Criteria')).toBe(true);
  });

  it('detects re-read loops', () => {
    const report = diagnoseFuel({ projectRoot: '/tmp/p', events: [
      event({ id: 1, toolName: 'Read', filePath: 'src/app.ts' }),
      event({ id: 2, toolName: 'Read', filePath: 'src/app.ts' }),
      event({ id: 3, toolName: 'Read', filePath: 'src/app.ts' })
    ] });
    expect(report.findings.some((finding) => finding.category === 'Re-read Loop')).toBe(true);
  });

  it('calculates fuel score', () => {
    expect(calculateFuelScore(1000, 250)).toBe(75);
    expect(calculateFuelScore(0, 0)).toBe(100);
  });

  it('exports markdown diagnosis', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-diagnosis-report-'));
    const report = exportMarkdownReport(projectRoot, join(projectRoot, '.token-tithe', 'token-tithe.db'));
    expect(report).toContain('# Mr Token AI Fuel Report');
    expect(report).toContain('## Fuel Score');
    expect(report).toContain('Privacy Note');
  });
});

function event(overrides: Partial<StoredEvent>): StoredEvent {
  return {
    id: 1,
    sessionId: 's1',
    eventType: 'UserPromptSubmit',
    toolName: null,
    filePath: null,
    command: null,
    promptText: null,
    promptLength: 0,
    stdoutLength: 0,
    stderrLength: 0,
    resultLength: 0,
    estimatedTokens: 100,
    projectPath: '/tmp/p',
    transcriptPath: null,
    rawJson: '{}',
    createdAt: '2026-05-26T00:00:00.000Z',
    ...overrides
  };
}
