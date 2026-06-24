-- MR Token MVP schema. See docs/DATA_MODEL.md.
CREATE TABLE IF NOT EXISTS trace (
  id                INTEGER PRIMARY KEY,
  source            TEXT NOT NULL DEFAULT 'claude_code',
  session_id        TEXT NOT NULL UNIQUE,
  parent_session_id TEXT,           -- set for subagent transcripts
  project_path      TEXT,
  git_branch        TEXT,
  cc_version        TEXT,
  entrypoint        TEXT,
  started_at        TEXT,
  ended_at          TEXT,
  title             TEXT,
  ingested_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_call (
  id                          INTEGER PRIMARY KEY,
  trace_id                    INTEGER NOT NULL REFERENCES trace(id),
  request_id                  TEXT,
  message_uuid                TEXT,
  parent_uuid                 TEXT,
  model                       TEXT,
  timestamp                   TEXT,
  input_tokens                INTEGER NOT NULL DEFAULT 0,
  output_tokens               INTEGER NOT NULL DEFAULT 0,
  cache_read_input_tokens     INTEGER NOT NULL DEFAULT 0,
  cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
  ephemeral_1h_tokens         INTEGER NOT NULL DEFAULT 0,
  ephemeral_5m_tokens         INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens            INTEGER,
  service_tier                TEXT,
  stop_reason                 TEXT,
  is_sidechain                INTEGER NOT NULL DEFAULT 0,
  est_cost_usd                REAL,
  price_version               TEXT
);

CREATE TABLE IF NOT EXISTS tool_call (
  id                INTEGER PRIMARY KEY,
  trace_id          INTEGER NOT NULL REFERENCES trace(id),
  model_call_id     INTEGER REFERENCES model_call(id),
  tool_use_id       TEXT,
  tool_name         TEXT,
  input_chars       INTEGER,
  input_hash        TEXT,
  output_chars      INTEGER,
  output_tokens_est INTEGER,
  output_hash       TEXT,
  is_error          INTEGER DEFAULT 0,
  started_at        TEXT,
  ended_at          TEXT
);

CREATE TABLE IF NOT EXISTS event (
  id        INTEGER PRIMARY KEY,
  trace_id  INTEGER NOT NULL REFERENCES trace(id),
  kind      TEXT NOT NULL,
  timestamp TEXT,
  meta_json TEXT
);

CREATE TABLE IF NOT EXISTS context_block (
  id           INTEGER PRIMARY KEY,
  trace_id     INTEGER NOT NULL REFERENCES trace(id),
  block_type   TEXT NOT NULL,
  hash         TEXT NOT NULL,
  token_count  INTEGER,
  char_count   INTEGER,
  repeat_count INTEGER NOT NULL DEFAULT 1,
  first_seen   TEXT,
  last_seen    TEXT,
  source_path  TEXT,
  sensitivity  TEXT,
  UNIQUE(trace_id, hash, block_type)
);

CREATE TABLE IF NOT EXISTS recommendation (
  id                 INTEGER PRIMARY KEY,
  trace_id           INTEGER NOT NULL REFERENCES trace(id),
  rule               TEXT NOT NULL,
  severity           TEXT NOT NULL,
  message            TEXT NOT NULL,
  evidence_json      TEXT,
  est_savings_tokens INTEGER,
  created_at         TEXT NOT NULL
);

-- internal feedback: human labels on fired recommendations (ROADMAP 5D.2).
-- Upgrades validate's automated proxy into real precision/recall from real usage.
CREATE TABLE IF NOT EXISTS feedback (
  id          INTEGER PRIMARY KEY,
  trace_id    INTEGER,
  session_id  TEXT NOT NULL,
  rule        TEXT NOT NULL,
  verdict     TEXT NOT NULL,        -- right | wrong | unsure
  note        TEXT,
  created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mc_trace   ON model_call(trace_id);
CREATE INDEX IF NOT EXISTS idx_fb_session ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_tc_trace   ON tool_call(trace_id);
CREATE INDEX IF NOT EXISTS idx_cb_trace   ON context_block(trace_id);
CREATE INDEX IF NOT EXISTS idx_rec_trace  ON recommendation(trace_id);
