import { diagnosisExamples, displayDiagnosisCategory, type DiagnosisReport } from './categories.js';

export function formatDiagnosisMarkdown(report: DiagnosisReport): string {
  return [
    `## Fuel Score`,
    '',
    `- Score: ${report.fuelScore}/100 (${report.fuelRating})`,
    `- Useful estimated tokens: ${report.burnProfile.usefulEstimatedTokens.toLocaleString()}`,
    `- Suspected waste tokens: ${report.burnProfile.suspectedWasteTokens.toLocaleString()}`,
    `- Waste percentage: ${report.burnProfile.wastePercentage}%`,
    `- Confidence: ${report.burnProfile.confidence}`,
    '',
    '## General Diagnosis',
    '',
    report.generalDiagnosis,
    '',
    '## Diagnosis Findings',
    '',
    ...(report.findings.length === 0
      ? ['No diagnosis findings.']
      : report.findings.flatMap((finding) => [
          `### ${displayDiagnosisCategory(finding.category)}`,
          '',
          `- Technical category: ${finding.category}`,
          `- Severity: ${finding.severity}`,
          `- Confidence: ${finding.confidence}`,
          `- Estimated waste: ${finding.estimatedWasteTokens.toLocaleString()} tokens`,
          `- Estimated savings: ${finding.savingsRange[0].toLocaleString()}-${finding.savingsRange[1].toLocaleString()} tokens`,
          `- Why this matters: ${finding.whyThisMatters}`,
          '- Evidence:',
          ...finding.evidence.map((line) => `  - ${line}`),
          '- Recommended fixes:',
          ...finding.recommendedFixes.map((fix) => `  - ${fix}`),
          finding.patchableAction ? `- Patchable action: ${finding.patchableAction}` : '',
          ''
        ])),
    '',
    '## Diagnosis Examples',
    '',
    ...diagnosisExamples.flatMap((example) => [`- ${example.name}: ${example.text}`])
  ].join('\n');
}
