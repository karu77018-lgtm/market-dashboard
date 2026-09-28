-- Jev Phase 1 / Stage 1
-- Apply BEFORE the hardened API is promoted.
-- This stage is additive and intentionally keeps evaluation_kind nullable.

ALTER TABLE jev_evaluations
  ADD COLUMN evaluation_kind text NULL,
  ADD COLUMN validation_eligible boolean NOT NULL DEFAULT false;

ALTER TABLE jev_evaluations
  ADD CONSTRAINT jev_evaluations_evaluation_kind_check
    CHECK (evaluation_kind IS NULL OR evaluation_kind IN ('smoke','manual_shadow','backfill','live')),
  ADD CONSTRAINT jev_evaluations_validation_eligible_check
    CHECK (
      validation_eligible = false
      OR (
        evaluation_kind IN ('backfill','live')
        AND source_document_id IS NOT NULL
        AND status = 'success'
      )
    );

UPDATE jev_evaluations
SET evaluation_kind = CASE
  WHEN id BETWEEN 1 AND 5 THEN 'smoke'
  WHEN id = 6 THEN 'manual_shadow'
  ELSE evaluation_kind
END,
validation_eligible = false
WHERE id BETWEEN 1 AND 6;

CREATE TABLE jev_attempts (
  id bigserial PRIMARY KEY,
  ticker text NOT NULL,
  asof_timestamp timestamptz NOT NULL,
  question_set_id bigint NOT NULL REFERENCES question_sets(id) ON DELETE RESTRICT,
  evaluation_kind text NOT NULL CHECK (evaluation_kind IN ('smoke','manual_shadow','backfill','live')),
  source_document_id bigint NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
  state_text_hash text NOT NULL CHECK (state_text_hash ~ '^[0-9a-f]{64}$'),
  dedupe_key text NOT NULL CHECK (dedupe_key ~ '^[0-9a-f]{64}$'),
  run_count smallint NOT NULL DEFAULT 3 CHECK (run_count = 3),
  status text NOT NULL CHECK (status IN ('started','success','duplicate','validation_error','gateway_error','timeout','db_error','partial')),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  duration_ms integer NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
  http_status integer NULL CHECK (http_status IS NULL OR (http_status BETWEEN 100 AND 599)),
  error_code text NULL,
  error_message text NULL,
  successful_runs smallint NOT NULL DEFAULT 0 CHECK (successful_runs BETWEEN 0 AND 3),
  gateway_cost_usd numeric(18,8) NOT NULL DEFAULT 0 CHECK (gateway_cost_usd >= 0),
  input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  evaluation_id bigint NULL REFERENCES jev_evaluations(id) ON DELETE RESTRICT,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_jev_attempts_status_started
  ON jev_attempts(status, started_at DESC);
CREATE INDEX idx_jev_attempts_ticker_asof
  ON jev_attempts(ticker, asof_timestamp DESC);
CREATE INDEX idx_jev_attempts_dedupe
  ON jev_attempts(dedupe_key);
