-- Phase A-0 private preservation manifest. Additive, append-only, and rerunnable.
CREATE TABLE IF NOT EXISTS research_snapshot_manifests (
  id bigserial PRIMARY KEY,
  session_date date NOT NULL,
  github_run_id bigint NOT NULL UNIQUE,
  github_run_attempt integer NOT NULL CHECK (github_run_attempt > 0),
  github_actions_started_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL,
  code_sha text NOT NULL CHECK (code_sha ~ '^[0-9a-f]{40}$'),
  repository text NOT NULL,
  workflow_ref text NOT NULL,
  snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
  snapshot_bytes bigint NOT NULL CHECK (snapshot_bytes > 0),
  drive_file_id text NOT NULL UNIQUE,
  drive_file_name text NOT NULL,
  copy_status text NOT NULL CHECK (copy_status = 'success'),
  inserted_at timestamptz NOT NULL DEFAULT now()
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_research_snapshot_manifests_session
  ON research_snapshot_manifests(session_date DESC, github_run_id DESC);
-- statement-breakpoint
CREATE OR REPLACE FUNCTION protect_research_snapshot_manifests()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'research_snapshot_manifests is append-only';
END;
$$;
-- statement-breakpoint
DROP TRIGGER IF EXISTS trg_research_snapshot_manifests_immutable ON research_snapshot_manifests;
-- statement-breakpoint
CREATE TRIGGER trg_research_snapshot_manifests_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON research_snapshot_manifests
FOR EACH STATEMENT EXECUTE FUNCTION protect_research_snapshot_manifests();
