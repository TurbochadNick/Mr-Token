import { describe, expect, it } from 'vitest';
import { buildRedactedAuditSummary, redactEvidenceLine } from '../src/ai/redacted-summary.js';

describe('AI redaction', () => {
  it('redacts paths, commands, and long quoted text', () => {
    const redacted = redactEvidenceLine(
      'event #7: /Users/me/project/src/secret.ts ran pnpm test -- --verbose with "this is a very long prompt block that should not leave the machine"'
    );

    expect(redacted).toContain('[path]');
    expect(redacted).toContain('[command]');
    expect(redacted).toContain('"[redacted]"');
    expect(redacted).not.toContain('/Users/me/project/src/secret.ts');
    expect(redacted).not.toContain('pnpm test -- --verbose');
  });

  it('builds a structured summary without raw source or transcript data by default', () => {
    const summary = buildRedactedAuditSummary({
      redaction: true,
      fullContext: false,
      summary: {
        eventCount: 1,
        totalTokens: 1000,
        sessionCount: 1,
        promptCount: 1,
        toolCallCount: 1
      },
      findings: [
        {
          category: 'Huge bash/tool outputs',
          confidence: 'high',
          estimatedWasteTokens: 400,
          savingsRange: [200, 500],
          evidence: ['event #1: /repo/src/app.ts output "full transcript text that is intentionally long"'],
          recommendedFixes: ['Filter command output.']
        }
      ]
    });

    expect(JSON.stringify(summary)).not.toContain('/repo/src/app.ts');
    expect(summary.findings[0]?.category).toBe('Huge bash/tool outputs');
    expect(summary.findings[0]?.recommendedFixes).toEqual(['Filter command output.']);
  });
});
