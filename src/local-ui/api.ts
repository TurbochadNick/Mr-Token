import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { runAuditRules, type AuditFinding } from '../audit/rules.js';
import { initializeProject, type InitProjectResult } from '../core/init.js';
import { openDatabase } from '../db/client.js';
import { getSummary, listEvents } from '../db/events.js';
import { generateDoctorPatches } from '../doctor/patches.js';
import { hasTokenTitheHooks } from '../adapters/claude-code/install.js';
import { diagnoseFuel } from '../diagnosis/diagnose.js';
import { formatDiagnosisMarkdown } from '../diagnosis/report.js';
import type { DiagnosisReport } from '../diagnosis/categories.js';
import type { StoredEvent } from '../schemas/events.js';
import { defaultClaudeSettingsPath, defaultDataDir, defaultDbPath, defaultEventsPath } from '../utils/paths.js';

export type UiSummary = {
  totalEstimatedTokens: number;
  sessions: number;
  prompts: number;
  toolCalls: number;
  estimatedSavingsRange: [number, number];
};

export type UiFinding = {
  category: string;
  confidence: string;
  estimatedWasteTokens: number;
  savingsRange: [number, number];
  recommendedFixes: string[];
  evidence: string[];
};

export type UiEvent = {
  id: number;
  eventType: string;
  toolName: string | null;
  estimatedTokens: number;
  filePath: string | null;
  command: string | null;
  timestamp: string;
};

export type UiDoctorLatest = {
  patchDir: string;
  summaryPath: string;
  diffPath: string;
  summary: string;
  diff: string;
} | null;

export type UiSetupStatus = {
  projectRoot: string;
  dbPath: string;
  databaseExists: boolean;
  eventsPath: string;
  eventsJsonlExists: boolean;
  settingsPath: string;
  claudeSettingsExists: boolean;
  hooksInstalled: boolean;
};

export type UiDoctorRunResult = {
  patchDir: string;
  summaryPath: string;
  diffPath: string;
  files: Array<{
    targetPath: string;
    patchPath: string;
    status: string;
    summary: string;
  }>;
  latest: UiDoctorLatest;
};

export type UiData = {
  summary: UiSummary;
  findings: UiFinding[];
  events: UiEvent[];
  doctorLatest: UiDoctorLatest;
  setup: UiSetupStatus;
  diagnosis: DiagnosisReport;
};

export function getUiData(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiData {
  const db = openDatabase(dbPath);
  const summary = getSummary(db);
  const events = listEvents(db);
  db.close();

  const findings = runAuditRules({ events, projectRoot });
  const diagnosis = diagnoseFuel({ events, projectRoot, totalTokens: summary.totalTokens });

  return {
    summary: toUiSummary(summary, findings),
    findings: findings.map(toUiFinding),
    events: events.map(toUiEvent).reverse(),
    doctorLatest: getLatestDoctorPatch(projectRoot),
    setup: getSetupStatus(projectRoot, dbPath),
    diagnosis
  };
}

export function getUiSummary(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiSummary {
  return getUiData(projectRoot, dbPath).summary;
}

export function getUiFindings(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiFinding[] {
  return getUiData(projectRoot, dbPath).findings;
}

export function getUiEvents(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiEvent[] {
  return getUiData(projectRoot, dbPath).events;
}

export function getUiDiagnosis(projectRoot: string, dbPath = defaultDbPath(projectRoot)): DiagnosisReport {
  return getUiData(projectRoot, dbPath).diagnosis;
}

export function getLatestDoctorPatch(projectRoot: string): UiDoctorLatest {
  const patchesDir = join(defaultDataDir(projectRoot), 'patches');
  if (!existsSync(patchesDir)) return null;

  const latest = readdirSync(patchesDir)
    .map((name) => join(patchesDir, name))
    .filter((path) => statSync(path).isDirectory())
    .sort()
    .at(-1);

  if (!latest) return null;

  const summaryPath = join(latest, 'SUMMARY.md');
  const diffPath = join(latest, 'patch.diff');

  return {
    patchDir: latest,
    summaryPath,
    diffPath,
    summary: existsSync(summaryPath) ? readFileSync(summaryPath, 'utf8') : '',
    diff: existsSync(diffPath) ? readFileSync(diffPath, 'utf8') : ''
  };
}

export function getSetupStatus(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiSetupStatus {
  const eventsPath = defaultEventsPath(projectRoot);
  const settingsPath = defaultClaudeSettingsPath(projectRoot);
  const claudeSettingsExists = existsSync(settingsPath);

  return {
    projectRoot,
    dbPath,
    databaseExists: existsSync(dbPath),
    eventsPath,
    eventsJsonlExists: existsSync(eventsPath),
    settingsPath,
    claudeSettingsExists,
    hooksInstalled: claudeSettingsExists ? hasTokenTitheHooks(settingsPath, dbPath, eventsPath) : false
  };
}

export function runUiInit(projectRoot: string, dbPath = defaultDbPath(projectRoot)): InitProjectResult {
  return initializeProject({ projectRoot, dbPath });
}

export function runUiDoctor(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiDoctorRunResult {
  const result = generateDoctorPatches(projectRoot, new Date(), { dbPath });

  return {
    patchDir: result.patchDir,
    summaryPath: result.summaryPath,
    diffPath: result.diffPath,
    files: result.files,
    latest: getLatestDoctorPatch(projectRoot)
  };
}

export function exportMarkdownReport(projectRoot: string, dbPath = defaultDbPath(projectRoot)): string {
  const data = getUiData(projectRoot, dbPath);
  const lines = [
    '# Mr Token AI Fuel Report',
    '',
    `Project root: ${projectRoot}`,
    `Time generated: ${data.diagnosis.generatedAt}`,
    `Database: ${data.setup.dbPath}`,
    '',
    formatDiagnosisMarkdown(data.diagnosis),
    '',
    '## Summary',
    '',
    `- Total estimated tokens: ${data.summary.totalEstimatedTokens.toLocaleString()}`,
    `- Sessions: ${data.summary.sessions.toLocaleString()}`,
    `- Prompts: ${data.summary.prompts.toLocaleString()}`,
    `- Tool calls: ${data.summary.toolCalls.toLocaleString()}`,
    `- Estimated savings: ${data.summary.estimatedSavingsRange[0].toLocaleString()}-${data.summary.estimatedSavingsRange[1].toLocaleString()} tokens`,
    '',
    '## Deterministic Audit Findings',
    '',
    ...(data.findings.length === 0
      ? ['No deterministic waste patterns detected.']
      : data.findings.flatMap((finding) => [
          `### ${finding.category}`,
          '',
          `- Confidence: ${finding.confidence}`,
          `- Estimated waste: ${finding.estimatedWasteTokens.toLocaleString()} tokens`,
          `- Estimated savings: ${finding.savingsRange[0].toLocaleString()}-${finding.savingsRange[1].toLocaleString()} tokens`,
          '- Recommended fixes:',
          ...finding.recommendedFixes.map((fix) => `  - ${fix}`),
          ''
        ])),
    '',
    '## Doctor',
    '',
    data.doctorLatest
      ? `Latest patch bundle: ${data.doctorLatest.patchDir}`
      : 'No patch bundle generated yet.',
    '',
    'Patches are proposals only and are never applied automatically.'
    ,
    '',
    '## Privacy Note',
    '',
    'This report was generated locally from `.token-tithe/token-tithe.db`. No source upload, cloud backend, telemetry, auth, or external AI call is required by default.'
  ];

  return `${lines.join('\n')}\n`;
}

function toUiSummary(
  summary: ReturnType<typeof getSummary>,
  findings: AuditFinding[]
): UiSummary {
  return {
    totalEstimatedTokens: summary.totalTokens,
    sessions: summary.sessionCount,
    prompts: summary.promptCount,
    toolCalls: summary.toolCallCount,
    estimatedSavingsRange: findings.reduce(
      (range, finding): [number, number] => [
        range[0] + finding.savingsRange[0],
        range[1] + finding.savingsRange[1]
      ],
      [0, 0] as [number, number]
    )
  };
}

function toUiFinding(finding: AuditFinding): UiFinding {
  return {
    category: finding.category,
    confidence: finding.confidence,
    estimatedWasteTokens: finding.estimatedWasteTokens,
    savingsRange: finding.savingsRange,
    recommendedFixes: finding.recommendedFixes,
    evidence: finding.evidence
  };
}

function toUiEvent(event: StoredEvent): UiEvent {
  return {
    id: event.id,
    eventType: event.eventType,
    toolName: event.toolName,
    estimatedTokens: event.estimatedTokens,
    filePath: event.filePath,
    command: event.command,
    timestamp: event.createdAt
  };
}
