import type { AuditFinding } from '../audit/rules.js';

type AuditReportInput = {
  dbPath: string;
  summary: {
    eventCount: number;
    totalTokens: number;
    sessionCount: number;
    toolCallCount: number;
    promptCount: number;
  };
  findings: AuditFinding[];
  aiReview?: {
    status: string;
    message: string;
  };
};

export function formatAuditReport(input: AuditReportInput): string {
  const totalSavings = input.findings.reduce(
    (range, finding): [number, number] => [
      range[0] + finding.savingsRange[0],
      range[1] + finding.savingsRange[1]
    ],
    [0, 0] as [number, number]
  );
  const lines = [
    'Token Tithe Audit',
    '=================',
    '',
    `Database: ${input.dbPath}`,
    `Events: ${input.summary.eventCount}`,
    `Sessions: ${input.summary.sessionCount}`,
    `Prompts: ${input.summary.promptCount}`,
    `Tool calls: ${input.summary.toolCallCount}`,
    `Total estimated tokens: ${input.summary.totalTokens.toLocaleString()}`,
    `Estimated savings range: ${formatRange(totalSavings)}`,
    '',
    'Top waste categories',
    '--------------------',
    ...formatFindingSummary(input.findings),
    '',
    'Findings',
    '--------',
    ...formatFindings(input.findings),
    '',
    'AI Review',
    '---------',
    ...formatAiReview(input.aiReview)
  ];

  return lines.join('\n');
}

function formatFindingSummary(findings: AuditFinding[]): string[] {
  if (findings.length === 0) return ['No deterministic waste patterns detected yet.'];

  return findings.slice(0, 5).map((finding, index) => {
    const rank = `${index + 1}.`;
    return `${rank.padEnd(3)} ${finding.category.padEnd(36)} ${finding.estimatedWasteTokens
      .toLocaleString()
      .padStart(8)} waste tokens  confidence: ${finding.confidence}`;
  });
}

function formatFindings(findings: AuditFinding[]): string[] {
  if (findings.length === 0) {
    return [
      'No findings. Keep collecting Claude Code hook events, then run audit again after a few sessions.'
    ];
  }

  return findings.flatMap((finding, index) => [
    `${index + 1}. ${finding.category}`,
    `   Confidence: ${finding.confidence}`,
    `   Estimated waste: ${finding.estimatedWasteTokens.toLocaleString()} tokens`,
    `   Estimated savings: ${formatRange(finding.savingsRange)}`,
    '   Evidence:',
    ...finding.evidence.map((line) => `   - ${line}`),
    '   Recommended fixes:',
    ...finding.recommendedFixes.map((line) => `   - ${line}`),
    ''
  ]);
}

function formatRange(range: [number, number]): string {
  return `${range[0].toLocaleString()}-${range[1].toLocaleString()} tokens`;
}

function formatAiReview(aiReview: AuditReportInput['aiReview']): string[] {
  if (!aiReview) return ['AI review was not run.'];

  return [`Status: ${aiReview.status}`, aiReview.message];
}
