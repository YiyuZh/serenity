BEGIN;

CREATE TABLE IF NOT EXISTS source_accounts (
  id BIGSERIAL PRIMARY KEY,
  source VARCHAR(32) NOT NULL DEFAULT 'x',
  handle VARCHAR(128) NOT NULL,
  user_id VARCHAR(64),
  since_id VARCHAR(64),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  poll_interval_seconds INT NOT NULL DEFAULT 180,
  last_checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_source_accounts_source_handle UNIQUE (source, handle),
  CONSTRAINT ck_source_accounts_poll_interval CHECK (poll_interval_seconds >= 60)
);

CREATE INDEX IF NOT EXISTS idx_source_accounts_active
ON source_accounts (active, last_checked_at);

CREATE TABLE IF NOT EXISTS posts (
  id BIGSERIAL PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES source_accounts(id) ON DELETE CASCADE,
  source VARCHAR(32) NOT NULL DEFAULT 'x',
  post_id VARCHAR(64) NOT NULL,
  post_url TEXT NOT NULL,
  post_type VARCHAR(32) NOT NULL DEFAULT 'original',
  referenced_post_id VARCHAR(64),
  conversation_id VARCHAR(64),
  original_text TEXT,
  translated_text TEXT,
  lang VARCHAR(16),
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  translated_at TIMESTAMPTZ,
  pushed_at TIMESTAMPTZ,
  ready_event_emitted_at TIMESTAMPTZ,
  fetch_status VARCHAR(32) NOT NULL DEFAULT 'succeeded',
  media_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  translation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  push_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  raw_json JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_posts_source_post_id UNIQUE (source, post_id),
  CONSTRAINT ck_posts_post_type CHECK (post_type IN ('original','quote','reply','retweet')),
  CONSTRAINT ck_posts_fetch_status CHECK (fetch_status IN ('pending','running','succeeded','failed','retrying','skipped')),
  CONSTRAINT ck_posts_media_status CHECK (media_status IN ('pending','running','succeeded','failed','retrying','skipped')),
  CONSTRAINT ck_posts_translation_status CHECK (translation_status IN ('pending','running','succeeded','failed','retrying','skipped')),
  CONSTRAINT ck_posts_push_status CHECK (push_status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_posts_account_published
ON posts (account_id, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_push_status_created
ON posts (push_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_translation_status_created
ON posts (translation_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_failed_partial
ON posts (created_at DESC)
WHERE fetch_status IN ('failed','retrying')
   OR media_status IN ('failed','retrying')
   OR translation_status IN ('failed','retrying')
   OR push_status IN ('failed','retrying');

CREATE TABLE IF NOT EXISTS media_assets (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  media_key VARCHAR(128),
  media_type VARCHAR(32),
  original_url TEXT,
  preview_url TEXT,
  storage_path TEXT,
  storage_url TEXT,
  alt_text TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  retry_count INT NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_media_assets_post_key UNIQUE (post_id, media_key),
  CONSTRAINT ck_media_assets_status CHECK (status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_media_assets_post_id
ON media_assets (post_id);

CREATE INDEX IF NOT EXISTS idx_media_assets_status_created
ON media_assets (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_assets_failed_partial
ON media_assets (created_at DESC)
WHERE status IN ('failed','retrying');

CREATE TABLE IF NOT EXISTS translation_jobs (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  model_name VARCHAR(64) NOT NULL,
  input_text TEXT NOT NULL,
  output_text TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  retry_count INT NOT NULL DEFAULT 0,
  prompt_tokens INT,
  completion_tokens INT,
  total_tokens INT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT ck_translation_jobs_status CHECK (status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_translation_jobs_post_id
ON translation_jobs (post_id);

CREATE INDEX IF NOT EXISTS idx_translation_jobs_status_created
ON translation_jobs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_translation_jobs_failed_partial
ON translation_jobs (created_at DESC)
WHERE status IN ('failed','retrying');

CREATE TABLE IF NOT EXISTS push_targets (
  id BIGSERIAL PRIMARY KEY,
  channel VARCHAR(32) NOT NULL DEFAULT 'feishu',
  name VARCHAR(128) NOT NULL,
  env_key VARCHAR(128) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_push_targets_channel_env_key UNIQUE (channel, env_key)
);

CREATE INDEX IF NOT EXISTS idx_push_targets_active
ON push_targets (active, channel);

CREATE TABLE IF NOT EXISTS push_logs (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  target_id BIGINT NOT NULL REFERENCES push_targets(id) ON DELETE RESTRICT,
  payload JSONB,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  retry_count INT NOT NULL DEFAULT 0,
  response_json JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  pushed_at TIMESTAMPTZ,
  CONSTRAINT ck_push_logs_status CHECK (status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_push_logs_post_id
ON push_logs (post_id);

CREATE INDEX IF NOT EXISTS idx_push_logs_target_id
ON push_logs (target_id);

CREATE INDEX IF NOT EXISTS idx_push_logs_status_created
ON push_logs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS sync_runs (
  id BIGSERIAL PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES source_accounts(id) ON DELETE CASCADE,
  triggered_by VARCHAR(32) NOT NULL DEFAULT 'scheduler',
  status VARCHAR(32) NOT NULL DEFAULT 'running',
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  fetched_count INT NOT NULL DEFAULT 0,
  new_count INT NOT NULL DEFAULT 0,
  error_message TEXT,
  CONSTRAINT ck_sync_runs_triggered_by CHECK (triggered_by IN ('scheduler','manual')),
  CONSTRAINT ck_sync_runs_status CHECK (status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_account_started
ON sync_runs (account_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status_started
ON sync_runs (status, started_at DESC);

CREATE TABLE IF NOT EXISTS task_attempts (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT REFERENCES posts(id) ON DELETE CASCADE,
  task_type VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  attempt_no INT NOT NULL DEFAULT 1,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  duration_ms INT,
  error_message TEXT,
  metadata JSONB,
  CONSTRAINT ck_task_attempts_task_type CHECK (task_type IN ('sync','media','translation','push')),
  CONSTRAINT ck_task_attempts_status CHECK (status IN ('pending','running','succeeded','failed','retrying','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_task_attempts_post_id
ON task_attempts (post_id);

CREATE INDEX IF NOT EXISTS idx_task_attempts_type_status_started
ON task_attempts (task_type, status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_attempts_failed_partial
ON task_attempts (started_at DESC)
WHERE status IN ('failed','retrying');

COMMIT;
