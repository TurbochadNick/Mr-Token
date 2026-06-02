import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { runAuditRules } from '../src/audit/rules.js';
import { formatAuditReport } from '../src/report/audit.js';
import type { StoredEvent } from '../src/schemas/events.js';

describe('audit rules', () => {
  it('detects deterministic waste categories with evidence and fixes', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-audit-'));
    writeFileSync(join(projectRoot, 'CLAUDE.md'), 'Keep this instruction.\n'.repeat(700), 'utf8');
    const repeatedPrompt =
      'Please carefully implement this feature with tests and keep the code simple. '.repeat(3);
    const events = [
      event({ id: 1, projectPath: projectRoot, promptText: repeatedPrompt, promptLength: repeatedPrompt.length, estimatedTokens: 55 }),
      event({ id: 2, projectPath: projectRoot, promptText: repeatedPrompt, promptLength: repeatedPrompt.length, estimatedTokens: 55 }),
      event({ id: 3, projectPath: projectRoot, eventType: 'PostToolUse', toolName: 'Read', filePath: 'src/big.ts', resultLength: 24000, estimatedTokens: 6000 }),
      event({ id: 4, projectPath: projectRoot, eventType: 'PostToolUse', toolName: 'Bash', command: 'pnpm test', stdoutLength: 18000, estimatedTokens: 4500 }),
      event({ id: 5, projectPath: projectRoot, eventType: 'PostToolUse', toolName: 'mcp__docs__fetch', estimatedTokens: 2500, rawJson: '{"server_name":"docs"}' }),
      event({ id: 6, projectPath: projectRoot, eventType: 'PreToolUse', toolName: 'Task', estimatedTokens: 2500, rawJson: '{"subagent":"explorer"}' }),
      event({ id: 7, projectPath: projectRoot, eventType: 'PreToolUse', toolName: 'Task', estimatedTokens: 2500, rawJson: '{"subagent":"explorer"}' }),
      event({ id: 8, projectPath: projectRoot, eventType: 'PreToolUse', toolName: 'Task', estimatedTokens: 2500, rawJson: '{"subagent":"explorer"}' }),
      event({ id: 9, projectPath: projectRoot, promptText: 'Fix and improve the app.', promptLength: 24, estimatedTokens: 6 }),
      event({
        id: 10,
        projectPath: projectRoot,
        promptText: 'Summarize current status.',
        promptLength: 25,
        estimatedTokens: 7,
        rawJson: '{"model":"claude-opus-4","prompt":"Summarize current status."}'
      }),
      event({ id: 11, projectPath: projectRoot, eventType: 'PreCompact', estimatedTokens: 30000 })
    ];

    const findings = runAuditRules({ events, projectRoot });
    const categories = findings.map((finding) => finding.category);

    expect(categories).toEqual(
      expect.arrayContaining([
        'Bloated CLAUDE.md',
        'Repeated prompt blocks',
        'Large file reads',
        'Huge bash/tool outputs',
        'Unused or expensive MCP/tool usage',
        'Excessive subagent/task usage',
        'Late compaction',
        'Broad unscoped prompts',
        'Model mismatch for cheap meta work'
      ])
    );
    expect(findings[0]?.estimatedWasteTokens).toBeGreaterThanOrEqual(findings[1]?.estimatedWasteTokens ?? 0);
    expect(findings.every((finding) => finding.evidence.length > 0)).toBe(true);
    expect(findings.every((finding) => finding.recommendedFixes.length > 0)).toBe(true);
  });

  it('formats a clean terminal report', () => {
    const report = formatAuditReport({
      dbPath: '/tmp/token-tithe.db',
      summary: {
        eventCount: 2,
        totalTokens: 1000,
        sessionCount: 1,
        toolCallCount: 1,
        promptCount: 1
      },
      findings: [
        {
          category: 'Huge bash/tool outputs',
          confidence: 'high',
          estimatedWasteTokens: 400,
          savingsRange: [200, 500],
          evidence: ['event #2: Bash output 20000 chars'],
          recommendedFixes: ['Filter command output.']
        }
      ]
    });

    expect(report).toContain('Total estimated tokens: 1,000');
    expect(report).toContain('Top waste categories');
    expect(report).toContain('Confidence: high');
    expect(report).toContain('event #2: Bash output 20000 chars');
    expect(report).toContain('Filter command output.');
    expect(report).toContain('Estimated savings: 200-500 tokens');
  });
});

function event(overrides: Partial<StoredEvent>): StoredEvent {
  return {
    id: 0,
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
    estimatedTokens: 1,
    projectPath: '/tmp/project',
    transcriptPath: null,
    rawJson: '{}',
    createdAt: '2026-05-25T00:00:00.000Z',
    ...overrides
  };
}
