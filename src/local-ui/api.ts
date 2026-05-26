import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { runAuditRules, type AuditFinding } from '../audit/rules.js';
import { openDatabase } from '../db/client.js';
import { getSummary, listEvents } from '../db/events.js';
import type { StoredEvent } from '../schemas/events.js';
import { defaultDataDir, defaultDbPath } from '../utils/paths.js';

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
  summary: string;
  diff: string;
} | null;

export type UiData = {
  summary: UiSummary;
  findings: UiFinding[];
  events: UiEvent[];
  doctorLatest: UiDoctorLatest;
};

export function getUiData(projectRoot: string, dbPath = defaultDbPath(projectRoot)): UiData {
  const db = openDatabase(dbPath);
  const summary = getSummary(db);
  const events = listEvents(db);
  db.close();

  const findings = runAuditRules({ events, projectRoot });

  return {
    summary: toUiSummary(summary, findings),
    findings: findings.map(toUiFinding),
    events: events.map(toUiEvent).reverse(),
    doctorLatest: getLatestDoctorPatch(projectRoot)
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
    summary: existsSync(summaryPath) ? readFileSync(summaryPath, 'utf8') : '',
    diff: existsSync(diffPath) ? readFileSync(diffPath, 'utf8') : ''
  };
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
