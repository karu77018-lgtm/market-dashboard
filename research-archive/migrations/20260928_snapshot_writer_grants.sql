-- Apply after creating a login role named snapshot_writer.
-- This role can append/read snapshot metadata and copy events but cannot modify history.

GRANT USAGE ON SCHEMA public TO snapshot_writer;

GRANT SELECT, INSERT ON snapshot_manifests TO snapshot_writer;
GRANT SELECT, INSERT ON snapshot_storage_copies TO snapshot_writer;

GRANT USAGE, SELECT ON SEQUENCE snapshot_manifests_id_seq TO snapshot_writer;
GRANT USAGE, SELECT ON SEQUENCE snapshot_storage_copies_id_seq TO snapshot_writer;

REVOKE UPDATE, DELETE, TRUNCATE ON snapshot_manifests FROM snapshot_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON snapshot_storage_copies FROM snapshot_writer;
