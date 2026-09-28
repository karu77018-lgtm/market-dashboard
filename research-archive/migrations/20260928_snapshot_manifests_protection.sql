-- Compatibility protection migration.
-- The main 20260928_snapshot_manifests.sql migration already installs these guards.
-- This file is safe to run after the main migration because every trigger is existence-checked.

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
