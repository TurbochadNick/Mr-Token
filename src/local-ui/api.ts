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
  apiBillingSessions: number;
  subscriptionBillingSessions: number;
  unknownBillingSessions: number;
  providerReportedTotals: number;
  computedTotals: number;
  unknownTotals: number;
  cacheHitRatio: number | null;
  highRecommendations: number;
  addressableWasteTokens: number | null; // recommendation estimate; null when unavailable
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

// One row of the per-session token ledger (token-native counter). Keyed by session_id.
// A `measured` row carries the transcript-derived breakdown from the backend
// session_summary view; an `estimated` row falls back to the char-counted TS event total
// and carries NO measured breakdown — the two are never silently mixed. Token counts
// only; no dollars live in this ledger by design.
export type UiSessionLedgerRow = {
  session: string;        // short, privacy-safe session prefix for display
  measured: boolean;      // true iff the backend actually measured this session
                          // (>=1 model_call recorded), NOT merely that a row exists
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens: number;    // measured total when measured; TS event estimate otherwise
};

export type UiData = {
  summary: UiSummary;
  accurate: UiAccurate;
  sessionLedger: UiSessionLedgerRow[];
  findings: UiFinding[];
  events: UiEvent[];
  doctorLatest: UiDoctorLatest;
  setup: UiSetupStatus;
  diagnosis: DiagnosisReport;
};

const EMPTY_ACCURATE: UiAccurate = {
  available: false, sessions: 0, inputTokens: 0, outputTokens: 0, cacheReadTokens: 0,
  cacheWriteTokens: 0, totalTokens: 0, estCostUsd: 0,
  apiBillingSessions: 0, subscriptionBillingSessions: 0, unknownBillingSessions: 0,
  providerReportedTotals: 0, computedTotals: 0, unknownTotals: 0, cacheHitRatio: null,
  highRecommendations: 0, addressableWasteTokens: null, profiles: []
};

// Read the Python backend's session_summary view (real token counts) if present.
// Falls back to EMPTY_ACCURATE (available=false) when the view does not exist,
// so a TS-only database never errors here.
export function readAccurateUsage(db: DbClient): UiAccurate {
  // Each catch below is scoped to ONE database read, because a missing view/column is the
  // only failure here that legitimately means "absent". Everything after the reads — the
  // arithmetic and the result construction — is deliberately OUTSIDE any catch: a defect
  // there is a defect, and must surface rather than be reported to the user as the benign
  // "backend has not run" state. Absence and failure must stay distinguishable.
  type AccurateRow = Omit<UiAccurate, 'available' | 'cacheHitRatio' | 'profiles' | 'addressableWasteTokens'>;

  const selectAccurate = (includeBilling: boolean) => `select count(*) as sessions,
    coalesce(sum(input_tokens), 0) as inputTokens,
    coalesce(sum(output_tokens), 0) as outputTokens,
    coalesce(sum(cache_read_tokens), 0) as cacheReadTokens,
    coalesce(sum(cache_write_tokens), 0) as cacheWriteTokens,
    coalesce(sum(total_tokens), 0) as totalTokens,
    coalesce(sum(est_cost_usd), 0) as estCostUsd,
    ${includeBilling ? `coalesce(sum(case when billing_mode = 'api' then 1 else 0 end), 0) as apiBillingSessions,
    coalesce(sum(case when billing_mode = 'subscription' then 1 else 0 end), 0) as subscriptionBillingSessions,
    coalesce(sum(case when billing_mode = 'unknown' then 1 else 0 end), 0) as unknownBillingSessions,
    coalesce(sum(case when cumulative_expenditure_provenance = 'provider-reported' then 1 else 0 end), 0) as providerReportedTotals,
    coalesce(sum(case when cumulative_expenditure_provenance = 'computed-disjoint-components' then 1 else 0 end), 0) as computedTotals,
    coalesce(sum(case when cumulative_expenditure_provenance = 'unknown' then 1 else 0 end), 0) as unknownTotals,` : ''}
    coalesce(sum(high_recommendations), 0) as highRecommendations
    from session_summary`;

  let row: AccurateRow | undefined;
  let hasBillingProvenance = true;
  try {
    row = db.prepare(selectAccurate(true)).get() as AccurateRow;
  } catch (error) {
    if (
      error instanceof Error &&
      (error as { code?: unknown }).code === 'SQLITE_ERROR' &&
      error.message === 'no such table: session_summary'
    ) {
      return EMPTY_ACCURATE; // session_summary view not present (backend has not run)
    }
    if (
      error instanceof Error &&
      (error as { code?: unknown }).code === 'SQLITE_ERROR' &&
      /^no such column: (billing_mode|cumulative_expenditure_provenance)$/.test(error.message)
    ) {
      // A pre-billing backend still has measured tokens, but no evidence to classify
      // billing or cumulative-total provenance. Surface it as explicitly UNKNOWN.
      row = db.prepare(selectAccurate(false)).get() as AccurateRow;
      hasBillingProvenance = false;
    } else {
      throw error;
    }
  }
  if (!row || row.sessions === 0) return EMPTY_ACCURATE;

  let profileRows: Array<{ profile: string }>;
  try {
    profileRows = db
      .prepare('select distinct profile from session_summary where profile is not null')
      .all() as Array<{ profile: string }>;
  } catch (error) {
    if (
      error instanceof Error &&
      (error as { code?: unknown }).code === 'SQLITE_ERROR' &&
      error.message === 'no such column: profile'
    ) {
      return EMPTY_ACCURATE; // session_summary lacks the profile column (older backend)
    }
    throw error;
  }
  const profiles = profileRows.map((r) => r.profile);

  // Addressable estimate from backend recommendations. An empty table is an
  // observed zero; a missing table is unavailable and must remain distinct.
  let addressableWasteTokens: number | null = null;
  try {
    addressableWasteTokens = (
      db.prepare('select coalesce(sum(est_savings_tokens), 0) as t from recommendation').get() as { t: number }
    ).t;
  } catch (error) {
    if (
      error instanceof Error &&
      (error as { code?: unknown }).code === 'SQLITE_ERROR' &&
      error.message === 'no such table: recommendation'
    ) {
      addressableWasteTokens = null;
    } else {
      throw error;
    }
  }

  const inputSide = row.inputTokens + row.cacheReadTokens + row.cacheWriteTokens;
  return {
    ...row,
    apiBillingSessions: hasBillingProvenance ? row.apiBillingSessions : 0,
    subscriptionBillingSessions: hasBillingProvenance ? row.subscriptionBillingSessions : 0,
    unknownBillingSessions: hasBillingProvenance ? row.unknownBillingSessions : row.sessions,
    providerReportedTotals: hasBillingProvenance ? row.providerReportedTotals : 0,
    computedTotals: hasBillingProvenance ? row.computedTotals : 0,
    unknownTotals: hasBillingProvenance ? row.unknownTotals : row.sessions,
    available: true,
    cacheHitRatio: inputSide > 0 ? row.cacheReadTokens / inputSide : null,
    addressableWasteTokens,
    profiles
  };
}

// Per-session token ledger keyed by events.session_id (the TS-owned table), LEFT JOINed
// to the backend session_summary view — the documented estimated↔actual join. A row in
// that view is NOT by itself evidence of measurement: the view LEFT JOINs model_call, so
// an ingested trace that recorded no model calls still yields a row whose SUMs are all
// COALESCEd to 0. Provenance is `model_calls > 0`. When provenance is present the ledger
// row is MEASURED (real transcript fields, including a genuinely observed zero); otherwise it
// falls back to the char-counted event total and is EXPLICITLY estimated, carrying no
// measured breakdown (never mixed). Resilient: if session_summary is absent the join
// throws and we degrade to an estimated-only ledger from events alone. Metadata-only:
// the session id is truncated to a short prefix for display.
export function readPerSessionUsage(db: DbClient): UiSessionLedgerRow[] {
  const shorten = (id: string | null): string =>
    !id ? 'unknown' : id.length <= 8 ? id : `${id.slice(0, 8)}…`;
  try {
    const rows = db
      .prepare(
        `select e.session_id as sessionId,
            coalesce(sum(e.estimated_tokens), 0) as estimatedTokens,
            s.session_id as measuredSessionId,
            s.model_calls as modelCalls,
            s.input_tokens as inputTokens,
            s.output_tokens as outputTokens,
            s.cache_read_tokens as cacheReadTokens,
            s.cache_write_tokens as cacheWriteTokens,
            s.total_tokens as measuredTotal
          from events e
          left join session_summary s on s.session_id = e.session_id
          group by e.session_id
          order by e.session_id`
      )
      .all() as Array<{
        sessionId: string | null;
        estimatedTokens: number;
        measuredSessionId: string | null;
        modelCalls: number | null;
        inputTokens: number | null;
        outputTokens: number | null;
        cacheReadTokens: number | null;
        cacheWriteTokens: number | null;
        measuredTotal: number | null;
      }>;
    return rows.map((r) =>
      r.measuredSessionId != null && (r.modelCalls ?? 0) > 0
        ? {
            session: shorten(r.sessionId),
            measured: true,
            inputTokens: r.inputTokens ?? 0,
            outputTokens: r.outputTokens ?? 0,
            cacheReadTokens: r.cacheReadTokens ?? 0,
            cacheWriteTokens: r.cacheWriteTokens ?? 0,
            totalTokens: r.measuredTotal ?? 0
          }
        : {
            session: shorten(r.sessionId),
            measured: false,
            inputTokens: 0,
            outputTokens: 0,
            cacheReadTokens: 0,
            cacheWriteTokens: 0,
            totalTokens: r.estimatedTokens
          }
    );
  } catch {
    // session_summary view (or its session_id column) not present → estimated-only ledger
    const rows = db
      .prepare(
        `select session_id as sessionId, coalesce(sum(estimated_tokens), 0) as estimatedTokens
          from events group by session_id order by session_id`
      )
      .all() as Array<{ sessionId: string | null; estimatedTokens: number }>;
    return rows.map((r) => ({
      session: shorten(r.sessionId),
      measured: false,
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
      totalTokens: r.estimatedTokens
    }));
  }
}

export function getUiData(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiData {
  const db = openDatabase(dbPath);
  const summary = getSummary(db);
  const events = listEvents(db);
  const accurate = readAccurateUsage(db);
  const sessionLedger = readPerSessionUsage(db);
  db.close();

  const findings = runAuditRules({ events, projectRoot });
  const diagnosis = diagnoseFuel({
    events, projectRoot, totalTokens: summary.totalTokens,
    // The UI has a measured total but no measured waste source. Its recommendation
    // sum is addressable estimated waste and must not be passed as measured waste.
    measuredTotalTokens: accurate.available ? accurate.totalTokens : undefined
  });

  return {
    summary: toUiSummary(summary, findings),
    accurate,
    sessionLedger,
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
          '- Source: MEASURED — real API token counts from the transcript backend',
          `- Actual total tokens: ${data.accurate.totalTokens.toLocaleString()} (vs estimated ${data.summary.totalEstimatedTokens.toLocaleString()})`,
          `- Input / output: ${data.accurate.inputTokens.toLocaleString()} / ${data.accurate.outputTokens.toLocaleString()}`,
          `- Cache read / write: ${data.accurate.cacheReadTokens.toLocaleString()} / ${data.accurate.cacheWriteTokens.toLocaleString()}`,
          `- Cache hit ratio: ${data.accurate.cacheHitRatio === null ? 'n/a' : `${Math.round(data.accurate.cacheHitRatio * 100)}%`}`,
          `- Billing evidence: API ${data.accurate.apiBillingSessions}; subscription ${data.accurate.subscriptionBillingSessions}; UNKNOWN ${data.accurate.unknownBillingSessions}. Dollar usage is shown only for session-owned API evidence.`,
          `- Cumulative-token provenance: provider-reported ${data.accurate.providerReportedTotals}; computed from documented disjoint components ${data.accurate.computedTotals}; UNKNOWN ${data.accurate.unknownTotals}. These routes are not combined.`,
          `- Sessions: ${data.accurate.sessions.toLocaleString()}; profiles: ${data.accurate.profiles.join(', ') || 'n/a'}`,
          `- High-priority recommendations: ${data.accurate.highRecommendations.toLocaleString()}`
        ]
      : [
          '- Source: ESTIMATED only — char-counted from hook events, not yet reconciled with real API usage',
          'Accurate usage is not available yet. Run the mrtoken-transcript backend (or its Stop hook) to populate real token counts.'
        ]),
    '',
    '## Token evidence by session',
    '',
    'Metadata only: token counts per session, each labeled measured (transcript-derived) or estimated (char-counted fallback), never mixed. No prompt text, source, secrets, full paths, or money-spend claim; sessions are shown by a short prefix.',
    '',
    '| Session | Status | Input | Output | Cache read | Cache write | Total tokens |',
    '| --- | --- | --- | --- | --- | --- | --- |',
    ...(data.sessionLedger.length === 0
      ? ['| (none) | — | — | — | — | — | — |']
      : data.sessionLedger.map((s) =>
          s.measured
            ? `| ${s.session} | measured | ${s.inputTokens.toLocaleString()} | ${s.outputTokens.toLocaleString()} | ${s.cacheReadTokens.toLocaleString()} | ${s.cacheWriteTokens.toLocaleString()} | ${s.totalTokens.toLocaleString()} |`
            : `| ${s.session} | estimated | — | — | — | — | ${s.totalTokens.toLocaleString()} |`
        )),
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
