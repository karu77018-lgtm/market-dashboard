-- Phase A-0: append-only integrity metadata for daily research snapshots.
-- Payload archives live outside Neon; this schema stores provenance and copy events only.

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
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (archive_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS snapshot_manifests_session_date_idx
    ON snapshot_manifests (session_date, github_run_id);

CREATE TABLE IF NOT EXISTS snapshot_storage_copies (
    id bigserial PRIMARY KEY,
    snapshot_manifest_id bigint NOT NULL REFERENCES snapshot_manifests(id),
    provider text NOT NULL,
    copy_status text NOT NULL CHECK (copy_status IN ('success', 'failed', 'not_configured')),
    storage_object_id text,
    attempted_at timestamptz NOT NULL,
    completed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (
        (copy_status = 'success' AND storage_object_id IS NOT NULL AND completed_at IS NOT NULL)
        OR
        (copy_status = 'failed' AND completed_at IS NOT NULL)
        OR
        (copy_status = 'not_configured')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS snapshot_storage_copies_attempt_uidx
    ON snapshot_storage_copies (
        snapshot_manifest_id,
        provider,
        attempted_at,
        copy_status,
        coalesce(storage_object_id, '')
    );

CREATE INDEX IF NOT EXISTS snapshot_storage_copies_manifest_idx
    ON snapshot_storage_copies (snapshot_manifest_id, provider, recorded_at);

CREATE OR REPLACE FUNCTION reject_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; % is not allowed', TG_TABLE_NAME, TG_OP;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'snapshot_manifests_no_update_delete'
          AND tgrelid = 'snapshot_manifests'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER snapshot_manifests_no_update_delete
        BEFORE UPDATE OR DELETE ON snapshot_manifests
        FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'snapshot_manifests_no_truncate'
          AND tgrelid = 'snapshot_manifests'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER snapshot_manifests_no_truncate
        BEFORE TRUNCATE ON snapshot_manifests
        FOR EACH STATEMENT EXECUTE FUNCTION reject_snapshot_mutation();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'snapshot_storage_copies_no_update_delete'
          AND tgrelid = 'snapshot_storage_copies'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER snapshot_storage_copies_no_update_delete
        BEFORE UPDATE OR DELETE ON snapshot_storage_copies
        FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'snapshot_storage_copies_no_truncate'
          AND tgrelid = 'snapshot_storage_copies'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER snapshot_storage_copies_no_truncate
        BEFORE TRUNCATE ON snapshot_storage_copies
        FOR EACH STATEMENT EXECUTE FUNCTION reject_snapshot_mutation();
    END IF;
END;
$$;
