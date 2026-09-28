-- Phase A-0 private preservation manifest.
-- Run ONCE with a direct administrator connection. Never run this from GitHub Actions.
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
CREATE INDEX IF NOT EXISTS idx_research_snapshot_manifests_session
  ON research_snapshot_manifests(session_date DESC, github_run_id DESC);
CREATE OR REPLACE FUNCTION protect_research_snapshot_manifests()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'research_snapshot_manifests is append-only';
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'trg_research_snapshot_manifests_immutable'
      AND tgrelid = 'public.research_snapshot_manifests'::regclass
  ) THEN
    CREATE TRIGGER trg_research_snapshot_manifests_immutable
    BEFORE UPDATE OR DELETE OR TRUNCATE ON research_snapshot_manifests
    FOR EACH STATEMENT EXECUTE FUNCTION protect_research_snapshot_manifests();
  END IF;
END;
$$;

DO $$
DECLARE
  role_is_elevated boolean;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'snapshot_writer') THEN
    CREATE ROLE snapshot_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  ELSE
    SELECT NOT r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
           OR r.rolreplication OR r.rolbypassrls
           OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid)
      INTO role_is_elevated
      FROM pg_roles r
      WHERE r.rolname = 'snapshot_writer';
    IF role_is_elevated THEN
      RAISE EXCEPTION 'existing snapshot_writer is elevated or inherits another role; refusing grants';
    END IF;
  END IF;
END;
$$;

REVOKE ALL PRIVILEGES ON TABLE research_snapshot_manifests FROM snapshot_writer;
REVOKE ALL PRIVILEGES ON SEQUENCE research_snapshot_manifests_id_seq FROM snapshot_writer;
GRANT USAGE ON SCHEMA public TO snapshot_writer;
GRANT SELECT, INSERT ON TABLE research_snapshot_manifests TO snapshot_writer;
GRANT USAGE ON SEQUENCE research_snapshot_manifests_id_seq TO snapshot_writer;

DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO snapshot_writer', current_database());
END;
$$;

-- Set a strong password separately, without committing it:
-- ALTER ROLE snapshot_writer PASSWORD '<strong-random-password>';
-- Store only snapshot_writer's connection string in GitHub secret NEON_DATABASE_URL.
