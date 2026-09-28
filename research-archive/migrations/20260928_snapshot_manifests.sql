-- Phase A-0: append-only manifest for immutable daily research snapshots.
-- Data payloads live outside Neon; this table stores provenance and integrity metadata only.

CREATE TABLE IF NOT EXISTS snapshot_manifests (
    id bigserial PRIMARY KEY,
    session_date date NOT NULL,
    github_run_id bigint NOT NULL UNIQUE,
    archive_name text NOT NULL,
    archive_sha256 text NOT NULL,
    manifest_sha256 text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    schema_version text NOT NULL,
    code_sha text NOT NULL,
    generated_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    drive_file_id text,
    copy_status text NOT NULL CHECK (copy_status IN ('success', 'failed', 'not_configured')),
    storage_uris jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (archive_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS snapshot_manifests_session_date_idx
    ON snapshot_manifests (session_date, github_run_id);

CREATE OR REPLACE FUNCTION protect_snapshot_manifests_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'snapshot_manifests is append-only; % is not allowed', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS snapshot_manifests_no_update_delete ON snapshot_manifests;
CREATE TRIGGER snapshot_manifests_no_update_delete
BEFORE UPDATE OR DELETE ON snapshot_manifests
FOR EACH ROW
EXECUTE FUNCTION protect_snapshot_manifests_append_only();

CREATE OR REPLACE FUNCTION protect_snapshot_manifests_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'snapshot_manifests is append-only; TRUNCATE is not allowed';
END;
$$;

DROP TRIGGER IF EXISTS snapshot_manifests_no_truncate ON snapshot_manifests;
CREATE TRIGGER snapshot_manifests_no_truncate
BEFORE TRUNCATE ON snapshot_manifests
FOR EACH STATEMENT
EXECUTE FUNCTION protect_snapshot_manifests_truncate();
