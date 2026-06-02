import type { AuditFinding } from '../audit/rules.js';

export type RedactedAuditSummary = {
  totalEstimatedTokens: number;
  eventCount: number;
  sessionCount: number;
  promptCount: number;
  toolCallCount: number;
  findings: Array<{
    category: string;
    confidence: string;
    estimatedWasteTokens: number;
    savingsRange: [number, number];
    evidence: string[];
    recommendedFixes: string[];
  }>;
};

export function buildRedactedAuditSummary(input: {
  summary: {
    eventCount: number;
    totalTokens: number;
    sessionCount: number;
    toolCallCount: number;
    promptCount: number;
  };
  findings: AuditFinding[];
  redaction: boolean;
  fullContext: boolean;
}): RedactedAuditSummary {
  return {
    totalEstimatedTokens: input.summary.totalTokens,
    eventCount: input.summary.eventCount,
    sessionCount: input.summary.sessionCount,
    promptCount: input.summary.promptCount,
    toolCallCount: input.summary.toolCallCount,
    findings: input.findings.map((finding) => ({
      category: finding.category,
      confidence: finding.confidence,
      estimatedWasteTokens: finding.estimatedWasteTokens,
      savingsRange: finding.savingsRange,
      evidence:
        input.redaction || !input.fullContext
          ? finding.evidence.map(redactEvidenceLine)
          : finding.evidence,
      recommendedFixes: finding.recommendedFixes
    }))
  };
}

export function redactEvidenceLine(line: string): string {
  return line
    .replace(/"[^"]{40,}"/g, '"[redacted]"')
    .replace(/'[^']{40,}'/g, "'[redacted]'")
    .replace(/([A-Za-z]:)?\/[^\s:]+(?:\/[^\s:]+)*/g, '[path]')
    .replace(/\b(?:npm|pnpm|yarn|git|node|tsx|tsc|vitest|python|curl|docker)\s+[^"'\n]+/g, '[command]');
}
