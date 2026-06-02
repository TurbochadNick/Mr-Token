export const schemaSql = `
create table if not exists events (
  id integer primary key autoincrement,
  timestamp text,
  project_path text,
  session_id text,
  event_name text not null,
  event_type text,
  tool_name text,
  file_path text,
  command text,
  prompt_text text,
  prompt_length integer not null default 0,
  stdout_length integer not null default 0,
  stderr_length integer not null default 0,
  result_length integer not null default 0,
  estimated_tokens integer not null,
  cwd text,
  transcript_path text,
  raw_json text not null,
  created_at text not null default (datetime('now'))
);

create index if not exists events_created_at_idx on events (created_at);
create index if not exists events_timestamp_idx on events (timestamp);
create index if not exists events_project_path_idx on events (project_path);
create index if not exists events_session_id_idx on events (session_id);
create index if not exists events_event_name_idx on events (event_name);
create index if not exists events_event_type_idx on events (event_type);
`;
