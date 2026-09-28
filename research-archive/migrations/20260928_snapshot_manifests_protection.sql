-- Phase A-0 stage 2: make snapshot_manifests append-only.
-- Validated on a temporary Neon branch before production rollout.

CREATE OR REPLACE FUNCTION protect_snapshot_manifests_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS 'BEGIN RAISE EXCEPTION ''snapshot_manifests is append-only; operation is not allowed''; END;';

CREATE TRIGGER snapshot_manifests_no_update_delete
BEFORE UPDATE OR DELETE ON snapshot_manifests
FOR EACH ROW
EXECUTE FUNCTION protect_snapshot_manifests_append_only();

CREATE OR REPLACE FUNCTION protect_snapshot_manifests_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS 'BEGIN RAISE EXCEPTION ''snapshot_manifests is append-only; truncate is not allowed''; END;';

CREATE TRIGGER snapshot_manifests_no_truncate
BEFORE TRUNCATE ON snapshot_manifests
FOR EACH STATEMENT
EXECUTE FUNCTION protect_snapshot_manifests_truncate();
