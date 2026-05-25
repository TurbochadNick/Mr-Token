import type { DbClient } from './client.js';
import type { ClaudeHookEvent, NormalizedHookEvent, StoredEvent } from '../schemas/events.js';
import { normalizeHookEvent } from '../hooks/normalize.js';

type EventRow = {
  id: number;
  timestamp: string | null;
  project_path: string | null;
  session_id: string | null;
  event_name: string;
  event_type: string | null;
  tool_name: string | null;
  file_path: string | null;
  command: string | null;
  prompt_text: string | null;
  prompt_length: number;
  stdout_length: number;
  stderr_length: number;
  result_length: number;
  estimated_tokens: number;
  cwd: string | null;
  transcript_path: string | null;
  raw_json: string;
  created_at: string;
};

export function insertEvent(db: DbClient, event: ClaudeHookEvent): number {
  return insertNormalizedEvent(db, normalizeHookEvent({ event }));
}

export function insertNormalizedEvent(db: DbClient, event: NormalizedHookEvent): number {
  const result = db
    .prepare(
      `insert into events (
        timestamp,
        project_path,
        session_id,
        event_name,
        event_type,
        tool_name,
        file_path,
        command,
        prompt_text,
        prompt_length,
        stdout_length,
        stderr_length,
        result_length,
        estimated_tokens,
        cwd,
        transcript_path,
        raw_json
      ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      event.timestamp,
      event.projectPath,
      event.sessionId,
      event.eventType,
      event.eventType,
      event.toolName,
      event.filePath,
      event.command,
      event.rawEvent.prompt ?? null,
      event.promptLength,
      event.stdoutLength,
      event.stderrLength,
      event.resultLength,
      event.estimatedTokens,
      event.projectPath,
      event.rawEvent.transcript_path ?? null,
      JSON.stringify(event.rawEvent)
    );

  return Number(result.lastInsertRowid);
}

export function listRecentEvents(db: DbClient, limit: number): StoredEvent[] {
  const rows = db
    .prepare('select * from events order by id desc limit ?')
    .all(limit) as EventRow[];

  return rows.map(mapRow);
}

export function listEvents(db: DbClient): StoredEvent[] {
  const rows = db.prepare('select * from events order by id asc').all() as EventRow[];
  return rows.map(mapRow);
}

export function getSummary(db: DbClient): {
  eventCount: number;
  totalTokens: number;
  sessionCount: number;
  toolCallCount: number;
  promptCount: number;
} {
  const row = db
    .prepare(
      `select
        count(*) as eventCount,
        coalesce(sum(estimated_tokens), 0) as totalTokens,
        count(distinct session_id) as sessionCount,
        coalesce(sum(case when tool_name is not null then 1 else 0 end), 0) as toolCallCount,
        coalesce(sum(case when prompt_length > 0 then 1 else 0 end), 0) as promptCount
      from events`
    )
    .get() as {
    eventCount: number;
    totalTokens: number;
    sessionCount: number;
    toolCallCount: number;
    promptCount: number;
  };

  return row;
}

export function getTokensByEvent(db: DbClient): Array<{ eventName: string; tokens: number; count: number }> {
  return db
    .prepare(
      `select event_name as eventName, sum(estimated_tokens) as tokens, count(*) as count
       from events
       group by event_name
       order by tokens desc`
    )
    .all() as Array<{ eventName: string; tokens: number; count: number }>;
}

export function getTokensByTool(db: DbClient): Array<{ toolName: string; tokens: number; count: number }> {
  return db
    .prepare(
      `select tool_name as toolName, sum(estimated_tokens) as tokens, count(*) as count
       from events
       where tool_name is not null
       group by tool_name
       order by tokens desc`
    )
    .all() as Array<{ toolName: string; tokens: number; count: number }>;
}

function mapRow(row: EventRow): StoredEvent {
  return {
    id: row.id,
    sessionId: row.session_id,
    eventType: row.event_type ?? row.event_name,
    toolName: row.tool_name,
    filePath: row.file_path,
    command: row.command,
    promptText: row.prompt_text,
    promptLength: row.prompt_length,
    stdoutLength: row.stdout_length,
    stderrLength: row.stderr_length,
    resultLength: row.result_length,
    estimatedTokens: row.estimated_tokens,
    projectPath: row.project_path ?? row.cwd,
    transcriptPath: row.transcript_path,
    rawJson: row.raw_json,
    createdAt: row.timestamp ?? row.created_at
  };
}
