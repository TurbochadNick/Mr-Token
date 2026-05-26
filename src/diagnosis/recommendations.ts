import type { DiagnosisFinding } from './categories.js';
import { displayDiagnosisCategory } from './categories.js';

export function rankedNextChanges(findings: DiagnosisFinding[]): string[] {
  return findings
    .slice(0, 5)
    .flatMap((finding) => finding.recommendedFixes.slice(0, 1).map((fix) => `${displayDiagnosisCategory(finding.category)}: ${fix}`));
}

export function generalDiagnosis(findings: DiagnosisFinding[]): string {
  if (findings.length === 0) {
    return 'Clean burn. The session shows no major token leaks in the local event data.';
  }

  const primary = findings[0];
  const secondary = findings[1];
  const primaryLabel = displayDiagnosisCategory(primary.category);
  const secondaryLabel = secondary ? displayDiagnosisCategory(secondary.category) : null;
  const tail = secondary
    ? ` Secondary leak: ${secondaryLabel}.`
    : ' No major secondary leak detected.';

  return `${primaryLabel} is the main fuel leak. ${primary.whyThisMatters}${tail}`;
}
