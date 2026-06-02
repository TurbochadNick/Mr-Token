import type { DiagnosisConfidence, DiagnosisFinding, FuelRating } from './categories.js';

export function calculateFuelScore(totalTokens: number, wasteTokens: number): number {
  if (totalTokens <= 0) return 100;
  const wasteRatio = Math.min(1, wasteTokens / totalTokens);
  return Math.max(0, Math.min(100, Math.round(100 - wasteRatio * 100)));
}

export function fuelRating(score: number): FuelRating {
  if (score >= 90) return 'Efficient';
  if (score >= 70) return 'Mostly efficient';
  if (score >= 50) return 'Waste detected';
  if (score >= 30) return 'Heavy waste';
  return 'Severe token leak';
}

export function aggregateConfidence(findings: DiagnosisFinding[]): DiagnosisConfidence {
  if (findings.some((finding) => finding.confidence === 'high')) return 'high';
  if (findings.some((finding) => finding.confidence === 'medium')) return 'medium';
  return 'low';
}

export function savingsRange(waste: number, low = 0.35, high = 0.8): [number, number] {
  return [Math.round(waste * low), Math.round(waste * high)];
}
