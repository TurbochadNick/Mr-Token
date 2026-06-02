import { openDatabase } from '../db/client.js';
import { getSummary, listEvents } from '../db/events.js';
import { runAuditRules } from '../audit/rules.js';
import { formatAuditReport } from '../report/audit.js';
import { runAnthropicAudit } from '../ai/anthropic.js';
import { buildRedactedAuditSummary } from '../ai/redacted-summary.js';
import { loadTokenTitheConfig } from '../config.js';
import { defaultDbPath, findProjectRoot } from '../utils/paths.js';

type AuditOptions = {
  db?: string;
};

export async function runAudit(options: AuditOptions): Promise<void> {
  const projectRoot = findProjectRoot();
  const config = loadTokenTitheConfig(projectRoot);
  const dbPath = options.db ?? defaultDbPath(projectRoot);
  const db = openDatabase(dbPath);
  const events = listEvents(db);
  const summary = getSummary(db);
  const findings = runAuditRules({ events, projectRoot });
  const aiSummary = buildRedactedAuditSummary({
    summary,
    findings,
    redaction: config.ai.redaction,
    fullContext: config.ai.fullContext
  });
  const aiReview = await runAnthropicAudit({ config, summary: aiSummary });

  const report = formatAuditReport({
    dbPath,
    summary,
    findings,
    aiReview
  });

  db.close();
  console.log(report);
}
