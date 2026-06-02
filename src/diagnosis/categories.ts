export type DiagnosisCategory =
  | 'Huge Tool Output'
  | 'Repeated Instructions'
  | 'Bloated Project Context'
  | 'Broad Prompt'
  | 'Unnecessary Full File Reads'
  | 'Re-read Loop'
  | 'Multi-Deliverable Prompt'
  | 'Late Compaction / Long Session Drift'
  | 'Subagent Overkill'
  | 'Style/Boilerplate Overhead'
  | 'Missing Acceptance Criteria'
  | 'Premature Architecture Debate';

export type DiagnosisSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type DiagnosisConfidence = 'low' | 'medium' | 'high';

export type DiagnosisFinding = {
  category: DiagnosisCategory;
  severity: DiagnosisSeverity;
  confidence: DiagnosisConfidence;
  estimatedWasteTokens: number;
  savingsRange: [number, number];
  evidence: string[];
  whyThisMatters: string;
  recommendedFixes: string[];
  patchableAction?: string;
};

export type BurnProfile = {
  usefulEstimatedTokens: number;
  suspectedWasteTokens: number;
  wastePercentage: number;
  topBurnCauses: string[];
  confidence: DiagnosisConfidence;
};

export type FuelRating = 'Efficient' | 'Mostly efficient' | 'Waste detected' | 'Heavy waste' | 'Severe token leak';

export type DiagnosisReport = {
  generatedAt: string;
  fuelScore: number;
  fuelRating: FuelRating;
  burnProfile: BurnProfile;
  generalDiagnosis: string;
  findings: DiagnosisFinding[];
  whatToChangeNext: string[];
};

export const diagnosisDisplayLabels: Record<DiagnosisCategory, string> = {
  'Huge Tool Output': 'Exhaust Flood',
  'Repeated Instructions': 'Idle Repetition',
  'Bloated Project Context': 'Heavy Chassis',
  'Broad Prompt': 'Wide Throttle',
  'Unnecessary Full File Reads': 'Full-Tank File Reads',
  'Re-read Loop': 'Context Reburn',
  'Multi-Deliverable Prompt': 'Multi-Load Turn',
  'Late Compaction / Long Session Drift': 'Stale Load',
  'Subagent Overkill': 'Parallel Burn',
  'Style/Boilerplate Overhead': 'Cabin Noise',
  'Missing Acceptance Criteria': 'No Stop Line',
  'Premature Architecture Debate': 'Bench Racing'
};

export const diagnosisExamples = [
  {
    name: 'Efficient session',
    text: 'Clean burn. Most tokens went into task-relevant prompts and focused tool reads. No major leaks detected.'
  },
  {
    name: 'Tool-output heavy session',
    text: 'Exhaust Flood is the main leak. Large command or tool output is entering context when a filtered excerpt would do.'
  },
  {
    name: 'Repeated prompt/context waste session',
    text: 'Idle Repetition and Heavy Chassis are dragging mileage down. Stable rules are being re-sent or loaded too often.'
  },
  {
    name: 'Broad-prompt exploration session',
    text: 'Wide Throttle is causing exploration burn. The prompt lacks file targets, stop lines, or expected output.'
  },
  {
    name: 'Severe waste session',
    text: 'Multiple leaks are active. Output volume, stale context, and broad prompts are all burning tokens at once.'
  }
] as const;

export function displayDiagnosisCategory(category: DiagnosisCategory): string {
  return diagnosisDisplayLabels[category];
}
