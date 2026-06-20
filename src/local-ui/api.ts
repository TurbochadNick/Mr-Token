import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { runAuditRules, type AuditFinding } from '../audit/rules.js';
import { initializeProject, type InitProjectResult } from '../core/init.js';
import { openDatabase, type DbClient } from '../db/client.js';
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

// Accurate, transcript-derived usage from the Python backend's session_summary
// view (the bridge). available=false when the backend has not populated this DB
// (e.g. the Stop hook has not run), in which case the UI shows estimated only.
export type UiAccurate = {
  available: boolean;
  sessions: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens: number;
  estCostUsd: number;
  cacheHitRatio: number | null;
  highRecommendations: number;
  wasteSavingsTokens: number; // sum of recommendation.est_savings_tokens (real)
  profiles: string[];
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
  accurate: UiAccurate;
  findings: UiFinding[];
  events: UiEvent[];
  doctorLatest: UiDoctorLatest;
  setup: UiSetupStatus;
  diagnosis: DiagnosisReport;
};

const EMPTY_ACCURATE: UiAccurate = {
  available: false, sessions: 0, inputTokens: 0, outputTokens: 0, cacheReadTokens: 0,
  cacheWriteTokens: 0, totalTokens: 0, estCostUsd: 0, cacheHitRatio: null,
  highRecommendations: 0, wasteSavingsTokens: 0, profiles: []
};

// Read the Python backend's session_summary view (real token counts) if present.
// Falls back to EMPTY_ACCURATE (available=false) when the view does not exist,
// so a TS-only database never errors here.
export function readAccurateUsage(db: DbClient): UiAccurate {
  try {
    const row = db
      .prepare(
        `select count(*) as sessions,
          coalesce(sum(input_tokens), 0) as inputTokens,
          coalesce(sum(output_tokens), 0) as outputTokens,
          coalesce(sum(cache_read_tokens), 0) as cacheReadTokens,
          coalesce(sum(cache_write_tokens), 0) as cacheWriteTokens,
          coalesce(sum(total_tokens), 0) as totalTokens,
          coalesce(sum(est_cost_usd), 0) as estCostUsd,
          coalesce(sum(high_recommendations), 0) as highRecommendations
        from session_summary`
      )
      .get() as Omit<UiAccurate, 'available' | 'cacheHitRatio' | 'profiles' | 'wasteSavingsTokens'>;
    if (!row || row.sessions === 0) return EMPTY_ACCURATE;
    const profiles = (
      db.prepare('select distinct profile from session_summary where profile is not null').all() as Array<{
        profile: string;
      }>
    ).map((r) => r.profile);
    // real recoverable waste = sum of the backend rules' est_savings_tokens.
    // Resilient on its own: session_summary can exist without the recommendation
    // table (older/partial backend), and that must not void the accurate data.
    let wasteSavingsTokens = 0;
    try {
      wasteSavingsTokens = (
        db.prepare('select coalesce(sum(est_savings_tokens), 0) as t from recommendation').get() as { t: number }
      ).t;
    } catch {
      wasteSavingsTokens = 0;
    }
    const inputSide = row.inputTokens + row.cacheReadTokens + row.cacheWriteTokens;
    return {
      ...row,
      available: true,
      cacheHitRatio: inputSide > 0 ? row.cacheReadTokens / inputSide : null,
      wasteSavingsTokens,
      profiles
    };
  } catch {
    return EMPTY_ACCURATE; // session_summary view not present (backend has not run)
  }
}

export function getUiData(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiData {
  const db = openDatabase(dbPath);
  const summary = getSummary(db);
  const events = listEvents(db);
  const accurate = readAccurateUsage(db);
  db.close();

  const findings = runAuditRules({ events, projectRoot });
  const diagnosis = diagnoseFuel({
    events, projectRoot, totalTokens: summary.totalTokens,
    // prefer REAL transcript totals for the fuel score when the backend has run,
    // so the headline rating reflects reality not char-counted estimates
    realTotalTokens: accurate.available ? accurate.totalTokens : undefined,
    realWasteTokens: accurate.available ? accurate.wasteSavingsTokens : undefined
  });

  return {
    summary: toUiSummary(summary, findings),
    accurate,
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
    '## Actual Usage (from transcripts)',
    '',
    ...(data.accurate.available
      ? [
          `- Actual total tokens: ${data.accurate.totalTokens.toLocaleString()} (vs estimated ${data.summary.totalEstimatedTokens.toLocaleString()})`,
          `- Input / output: ${data.accurate.inputTokens.toLocaleString()} / ${data.accurate.outputTokens.toLocaleString()}`,
          `- Cache read / write: ${data.accurate.cacheReadTokens.toLocaleString()} / ${data.accurate.cacheWriteTokens.toLocaleString()}`,
          `- Cache hit ratio: ${data.accurate.cacheHitRatio === null ? 'n/a' : `${Math.round(data.accurate.cacheHitRatio * 100)}%`}`,
          `- Estimated API-equivalent cost: $${data.accurate.estCostUsd.toFixed(2)} (not a subscription bill)`,
          `- Sessions: ${data.accurate.sessions.toLocaleString()}; profiles: ${data.accurate.profiles.join(', ') || 'n/a'}`,
          `- High-priority recommendations: ${data.accurate.highRecommendations.toLocaleString()}`
        ]
      : ['Accurate usage is not available yet. Run the mrtoken-transcript backend (or its Stop hook) to populate real token counts.']),
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
