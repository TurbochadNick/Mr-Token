import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { openDatabase, type DbClient } from '../src/db/client.js';
import { insertNormalizedEvent } from '../src/db/events.js';
import { exportMarkdownReport, getSetupStatus, getUiData, readAccurateUsage, runUiDoctor, runUiInit } from '../src/local-ui/api.js';

describe('Mr Token UI API', () => {
  it('returns dashboard, findings, events, and latest doctor patch data', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-ui-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8'); // mark as a real project so data resolves per-project
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const patchDir = join(projectRoot, '.token-tithe', 'patches', '20260525-101112');
    mkdirSync(patchDir, { recursive: true });
    writeFileSync(join(patchDir, 'SUMMARY.md'), '# summary\n', 'utf8');
    writeFileSync(join(patchDir, 'patch.diff'), 'diff --git a/CLAUDE.md b/CLAUDE.md\n', 'utf8');

    const db = openDatabase(dbPath);
    insertNormalizedEvent(db, {
      timestamp: '2026-05-25T10:00:00.000Z',
      projectPath: projectRoot,
      sessionId: 's1',
      eventType: 'PostToolUse',
      toolName: 'Bash',
      filePath: null,
      command: 'pnpm test',
      promptLength: 0,
      stdoutLength: 20000,
      stderrLength: 0,
      resultLength: 0,
      estimatedTokens: 5000,
      rawEvent: {
        session_id: 's1',
        hook_event_name: 'PostToolUse',
        cwd: projectRoot,
        tool_name: 'Bash',
        tool_input: { command: 'pnpm test' },
        tool_response: { stdout: 'x'.repeat(20000) }
      }
    });
    db.close();

    const data = getUiData(projectRoot, dbPath);

    expect(data.summary).toMatchObject({
      totalEstimatedTokens: 5000,
      sessions: 1,
      prompts: 0,
      toolCalls: 1
    });
    expect(data.summary.estimatedSavingsRange[1]).toBeGreaterThan(0);
    expect(data.findings[0]?.category).toBe('Huge bash/tool outputs');
    expect(data.events[0]).toMatchObject({
      eventType: 'PostToolUse',
      toolName: 'Bash',
      estimatedTokens: 5000,
      command: 'pnpm test'
    });
    expect(data.doctorLatest?.summary).toContain('# summary');
    expect(data.doctorLatest?.diff).toContain('diff --git');
  });

  it('supports setup, init, doctor, and report API helpers', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-ui-actions-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8'); // mark as a real project so data resolves per-project
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');

    expect(getSetupStatus(projectRoot, dbPath)).toMatchObject({
      projectRoot,
      databaseExists: false,
      eventsJsonlExists: false,
      claudeSettingsExists: false,
      hooksInstalled: false
    });

    const init = runUiInit(projectRoot, dbPath);
    expect(init.dbPath).toBe(dbPath);
    expect(getSetupStatus(projectRoot, dbPath)).toMatchObject({
      databaseExists: true,
      eventsJsonlExists: true,
      claudeSettingsExists: true,
      hooksInstalled: true
    });

    const doctor = runUiDoctor(projectRoot, dbPath);
    expect(doctor.patchDir).toContain('.token-tithe');
    expect(doctor.summaryPath.endsWith('SUMMARY.md')).toBe(true);
    expect(doctor.diffPath.endsWith('patch.diff')).toBe(true);
    expect(doctor.latest?.summary).toContain('token-tithe doctor patch bundle');

    const report = exportMarkdownReport(projectRoot, dbPath);
    expect(report).toContain('# Mr Token AI Fuel Report');
    expect(report).toContain('## Summary');
    expect(report).toContain('## Doctor');
  });

  it('reports accurate usage as unavailable on a TS-only database', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-acc-none-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8');
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    openDatabase(dbPath).close(); // events table only, no session_summary
    const data = getUiData(projectRoot, dbPath);
    expect(data.accurate.available).toBe(false);
    expect(data.accurate.totalTokens).toBe(0);
  });

  it('reads accurate usage from the session_summary contract when present', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-acc-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8');
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const db = openDatabase(dbPath);
    // mimic the Python backend's session_summary columns (the shared contract)
    db.exec(`create table session_summary (
      profile text, input_tokens integer, output_tokens integer,
      cache_read_tokens integer, cache_write_tokens integer, total_tokens integer,
      est_cost_usd real, high_recommendations integer
    );
    create table recommendation (est_savings_tokens integer);
    insert into session_summary values ('code', 100, 50, 850, 0, 150, 1.25, 2);`);
    const accurate = readAccurateUsage(db);
    db.close();
    expect(accurate.available).toBe(true);
    expect(accurate.totalTokens).toBe(150);
    expect(accurate.estCostUsd).toBeCloseTo(1.25);
    expect(accurate.cacheHitRatio).toBeCloseTo(850 / (100 + 850 + 0));
    expect(accurate.addressableWasteTokens).toBe(0);
    expect(accurate.profiles).toContain('code');
  });

  it('does not score a measured total with missing measured waste as perfect', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-measured-pair-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8');
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const db = openDatabase(dbPath);
    insertNormalizedEvent(db, {
      timestamp: '2026-09-19T00:00:00.000Z', projectPath: projectRoot, sessionId: 'measured',
      eventType: 'PostToolUse', toolName: 'Bash', filePath: null, command: 'x',
      promptLength: 0, stdoutLength: 20000, stderrLength: 0, resultLength: 0, estimatedTokens: 5000,
      rawEvent: { session_id: 'measured', hook_event_name: 'PostToolUse', cwd: projectRoot, tool_name: 'Bash', tool_input: {}, tool_response: {} }
    });
    // A measured transcript total is present, but the recommendation table — the
    // only current UI-path waste source — is intentionally absent.
    db.exec(`create table session_summary (
      session_id text, profile text, model_calls integer, input_tokens integer, output_tokens integer,
      cache_read_tokens integer, cache_write_tokens integer, total_tokens integer,
      est_cost_usd real, high_recommendations integer
    );
    insert into session_summary values ('measured','code',1,700,300,0,0,1000,0,0);`);
    db.close();

    const data = getUiData(projectRoot, dbPath);
    expect(data.accurate.available).toBe(true);
    expect(data.accurate.addressableWasteTokens).toBeNull();
    expect(data.diagnosis.findings.some((finding) => finding.category === 'Huge Tool Output')).toBe(true);
    expect(data.diagnosis.fuelScore).toBe(50);
    expect(data.diagnosis.fuelRating).toBe('Waste detected');
    expect(data.diagnosis.burnProfile.wastePercentage).toBe(50);
  });

  it('builds a per-session token ledger: measured from session_summary, estimated fallback, money-free Markdown', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-ledger-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8');
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const db = openDatabase(dbPath);
    // two sessions of TS events; s1 will also have a measured backend row, s$debug will not
    insertNormalizedEvent(db, {
      timestamp: '2026-08-21T10:00:00.000Z', projectPath: projectRoot, sessionId: 's1',
      eventType: 'PostToolUse', toolName: 'Bash', filePath: null, command: 'x',
      promptLength: 0, stdoutLength: 0, stderrLength: 0, resultLength: 0, estimatedTokens: 5000,
      rawEvent: { session_id: 's1', hook_event_name: 'PostToolUse', cwd: projectRoot, tool_name: 'Bash', tool_input: {}, tool_response: {} }
    });
    insertNormalizedEvent(db, {
      timestamp: '2026-08-21T10:05:00.000Z', projectPath: projectRoot, sessionId: 's$debug',
      eventType: 'PostToolUse', toolName: 'Bash', filePath: null, command: 'y',
      promptLength: 0, stdoutLength: 0, stderrLength: 0, resultLength: 0, estimatedTokens: 300,
      rawEvent: { session_id: 's$debug', hook_event_name: 'PostToolUse', cwd: projectRoot, tool_name: 'Bash', tool_input: {}, tool_response: {} }
    });
    // backend session_summary contract (WITH session_id) — only s1 is measured
    // model_calls is part of the real backend view contract (ingest._SESSION_SUMMARY_VIEW)
    // and is what proves measurement provenance; s1 has real calls behind its numbers.
    db.exec(`create table session_summary (
      session_id text, profile text, model_calls integer, input_tokens integer, output_tokens integer,
      cache_read_tokens integer, cache_write_tokens integer, total_tokens integer,
      est_cost_usd real, high_recommendations integer
    );
    insert into session_summary values ('s1','code',7,100,50,850,0,1000,1.25,2);`);
    db.close();

    const data = getUiData(projectRoot, dbPath);
    const bySession = Object.fromEntries(data.sessionLedger.map((r) => [r.session, r]));

    // (a) measured session: exact transcript breakdown, not marked estimated
    expect(bySession.s1).toMatchObject({
      measured: true, inputTokens: 100, outputTokens: 50,
      cacheReadTokens: 850, cacheWriteTokens: 0, totalTokens: 1000
    });
    // (b) estimated session: event total, explicitly estimated, no measured breakdown mixed in
    expect(bySession['s$debug']).toMatchObject({ measured: false, totalTokens: 300 });
    expect(bySession['s$debug'].inputTokens).toBe(0);

    // (c) Markdown token-evidence table distinguishes both rows with totals and shows no dollars
    const report = exportMarkdownReport(projectRoot, dbPath);
    expect(report).toContain('## Token evidence by session');
    const evidence = report.slice(report.indexOf('## Token evidence by session'));
    expect(evidence).toContain('measured');
    expect(evidence).toContain('estimated');
    expect(evidence).toContain((1000).toLocaleString()); // s1 measured total (locale-independent)
    expect(evidence).toContain((300).toLocaleString());   // s$debug estimated total
    expect(evidence).not.toMatch(/\$\s?\d/);             // token counts only — no money in the ledger
    expect('$1.25').toMatch(/\$\s?\d/);                  // a real currency claim is still detected
    expect(() => expect('$1.25').not.toMatch(/\$\s?\d/)).toThrow();
    expect(report).not.toMatch(/\bspent\b/i);             // no money-spend claim anywhere in the report
  });

  // F1 regression: `measured` must require measurement PROVENANCE, not merely the
  // existence of a session_summary row. This drives the REAL zero-model-call path —
  // the backend `trace`/`model_call` tables plus the actual session_summary VIEW
  // (LEFT JOIN + COUNT + COALESCE SUMs) — because a hand-built summary TABLE cannot
  // reproduce the defect: the all-zero row only arises from the view's own LEFT JOIN.
  it('does not mark a zero-model-call trace as measured (F1: provenance, not row existence)', () => {
    const projectRoot = mkdtempSync(join(tmpdir(), 'token-tithe-f1-'));
    writeFileSync(join(projectRoot, 'package.json'), '{}', 'utf8');
    const dbPath = join(projectRoot, '.token-tithe', 'token-tithe.db');
    const db = openDatabase(dbPath);

    // TS-side events exist for both sessions (this is what the ledger keys on)
    for (const [sessionId, estimatedTokens] of [['z1', 4200], ['m1', 900]] as const) {
      insertNormalizedEvent(db, {
        timestamp: '2026-09-15T10:00:00.000Z', projectPath: projectRoot, sessionId,
        eventType: 'PostToolUse', toolName: 'Bash', filePath: null, command: 'x',
        promptLength: 0, stdoutLength: 0, stderrLength: 0, resultLength: 0, estimatedTokens,
        rawEvent: { session_id: sessionId, hook_event_name: 'PostToolUse', cwd: projectRoot, tool_name: 'Bash', tool_input: {}, tool_response: {} }
      });
    }

    // Real backend shape: trace + model_call tables, and session_summary as a VIEW
    // over them — mirroring ingest._SESSION_SUMMARY_VIEW's aggregation semantics.
    db.exec(`create table trace (
        id integer primary key, session_id text, source text, profile text,
        project_path text, title text, started_at text, ended_at text
      );
      create table model_call (
        id integer primary key, trace_id integer, input_tokens integer,
        output_tokens integer, cache_read_input_tokens integer,
        cache_creation_input_tokens integer, est_cost_usd real
      );
      create view session_summary as
        select t.id as trace_id, t.session_id as session_id, t.source as source,
               t.profile as profile, t.project_path as project_path, t.title as title,
               t.started_at as started_at, t.ended_at as ended_at,
               count(mc.id) as model_calls,
               coalesce(sum(mc.input_tokens), 0) as input_tokens,
               coalesce(sum(mc.output_tokens), 0) as output_tokens,
               coalesce(sum(mc.cache_read_input_tokens), 0) as cache_read_tokens,
               coalesce(sum(mc.cache_creation_input_tokens), 0) as cache_write_tokens,
               coalesce(sum(mc.input_tokens + mc.output_tokens), 0) as total_tokens,
               round(coalesce(sum(mc.est_cost_usd), 0), 6) as est_cost_usd,
               0 as high_recommendations
          from trace t
          left join model_call mc on mc.trace_id = t.id
         group by t.id;
      -- z1: an ingested trace that recorded NO model calls at all (provenance absent).
      -- The view still yields a row for it, with every SUM coalesced to 0.
      insert into trace (id, session_id, source) values (1, 'z1', 'claude');
      -- m1: a trace with a real model call whose measured token counts are all ZERO.
      -- This is a legitimately OBSERVED zero and must stay measured.
      insert into trace (id, session_id, source) values (2, 'm1', 'claude');
      insert into model_call (id, trace_id, input_tokens, output_tokens,
                              cache_read_input_tokens, cache_creation_input_tokens, est_cost_usd)
        values (1, 2, 0, 0, 0, 0, 0.0);`);
    db.close();

    const data = getUiData(projectRoot, dbPath);
    const bySession = Object.fromEntries(data.sessionLedger.map((r) => [r.session, r]));

    // (a) THE DEFECT: no model calls => no measurement provenance => NOT measured.
    // It must fall back to the TS event estimate rather than assert a measured zero.
    expect(bySession.z1.measured).toBe(false);
    expect(bySession.z1.totalTokens).toBe(4200);

    // (b) THE GUARD: a real model call with zero tokens is an OBSERVED zero and
    // must survive as measured — the fix distinguishes provenance-absent from zero,
    // it does not treat zero as suspect.
    expect(bySession.m1.measured).toBe(true);
    expect(bySession.m1.totalTokens).toBe(0);
    expect(bySession.m1.inputTokens).toBe(0);
  });

  // FINDING 1 regression: readAccurateUsage's catch must cover ONLY the boundary where a
  // missing session_summary view/column can legitimately throw. A defect anywhere else —
  // notably the arithmetic and object construction after the reads — must propagate, not be
  // rendered to the user as the benign "backend has not run" absence (available: false).
  //
  // These two cases pull in opposite directions on purpose. Narrowing the catch too little
  // fails the first; narrowing it too much fails the second.
  describe('readAccurateUsage failure boundary', () => {
    // A row whose construction-time read throws — i.e. a genuine defect, NOT a missing view.
    const poisonedRow = {
      sessions: 1,
      inputTokens: 10,
      outputTokens: 5,
      get cacheReadTokens(): number {
        throw new Error('construction defect: not a missing-view condition');
      },
      cacheWriteTokens: 0,
      totalTokens: 15,
      estCostUsd: 0,
      highRecommendations: 0
    };

    it('propagates a non-missing-view error instead of reporting absence', () => {
      const db = {
        prepare: (sql: string) => ({
          get: () => (sql.includes('from recommendation') ? { t: 0 } : poisonedRow),
          all: () => [] as Array<{ profile: string }>
        })
      } as unknown as DbClient;

      // Must throw. Returning EMPTY_ACCURATE here would be the defect: a real bug
      // indistinguishable from "the Python backend has not run yet".
      expect(() => readAccurateUsage(db)).toThrow(/construction defect/);
    });

    it('still reports absence when the session_summary view is genuinely missing', () => {
      const db = {
        prepare: () => {
          throw Object.assign(new Error('no such table: session_summary'), {
            code: 'SQLITE_ERROR'
          });
        }
      } as unknown as DbClient;

      // The legitimate boundary: a TS-only database must not error here.
      const accurate = readAccurateUsage(db);
      expect(accurate.available).toBe(false);
      expect(accurate.sessions).toBe(0);
    });

    it('still reports absence when an older summary lacks profile', () => {
      const db = {
        prepare: (sql: string) => ({
          get: () => ({
            sessions: 1,
            inputTokens: 10,
            outputTokens: 5,
            cacheReadTokens: 0,
            cacheWriteTokens: 0,
            totalTokens: 15,
            estCostUsd: 0,
            highRecommendations: 0
          }),
          all: () => {
            if (sql.includes('select distinct profile')) {
              throw Object.assign(new Error('no such column: profile'), {
                code: 'SQLITE_ERROR'
              });
            }
            return [];
          }
        })
      } as unknown as DbClient;

      expect(readAccurateUsage(db).available).toBe(false);
    });

    it('propagates a corrupt database error instead of reporting absence', () => {
      const db = {
        prepare: () => {
          throw Object.assign(new Error('database disk image is malformed'), {
            code: 'SQLITE_CORRUPT'
          });
        }
      } as unknown as DbClient;

      expect(() => readAccurateUsage(db)).toThrow('database disk image is malformed');
    });
  });
});
