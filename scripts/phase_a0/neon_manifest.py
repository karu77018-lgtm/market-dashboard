#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

try:
    from scripts.phase_a0.common import write_github_output
except ModuleNotFoundError:
    from common import write_github_output


def connect(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url, connect_timeout=15)


def assert_writer_contract(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.research_snapshot_manifests')")
        if cursor.fetchone()[0] is None:
            raise SystemExit("research_snapshot_manifests is missing; apply the migration once as an administrator")
        cursor.execute(
            """SELECT count(*) = 3 FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'research_snapshot_manifests'
                   AND column_name IN ('drive_created_at', 'source', 'artifact_created_at')"""
        )
        if not cursor.fetchone()[0]:
            raise SystemExit("current preservation columns are missing; apply the migration as an administrator")
        cursor.execute(
            """
            SELECT
              current_user,
              has_table_privilege(current_user, 'public.research_snapshot_manifests', 'SELECT'),
              has_table_privilege(current_user, 'public.research_snapshot_manifests', 'INSERT'),
              has_table_privilege(current_user, 'public.research_snapshot_manifests', 'UPDATE'),
              has_table_privilege(current_user, 'public.research_snapshot_manifests', 'DELETE'),
              has_table_privilege(current_user, 'public.research_snapshot_manifests', 'TRUNCATE'),
              has_sequence_privilege(current_user, 'public.research_snapshot_manifests_id_seq', 'USAGE'),
              (SELECT pg_get_userbyid(relowner) = current_user
                 FROM pg_class WHERE oid = 'public.research_snapshot_manifests'::regclass),
              (SELECT NOT rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole
                      OR rolreplication OR rolbypassrls
                 FROM pg_roles WHERE rolname = current_user)
              OR EXISTS (
                SELECT 1 FROM pg_auth_members membership
                JOIN pg_roles role ON role.oid = membership.member
                WHERE role.rolname = current_user
              )
            """
        )
        (role, can_select, can_insert, can_update, can_delete, can_truncate,
         can_use_sequence, owns_table, elevated_role) = cursor.fetchone()
    if role != "snapshot_writer":
        raise SystemExit(f"database role {role} is not the dedicated snapshot_writer role")
    if not (can_select and can_insert and can_use_sequence):
        raise SystemExit(f"database role {role} lacks SELECT, INSERT, or sequence USAGE")
    if can_update or can_delete or can_truncate or owns_table or elevated_role:
        raise SystemExit(f"database role {role} is over-privileged; use the snapshot_writer connection")


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def lookup(connection, run_id: int, snapshot_sha256: str, manifest_sha256: str, code_sha: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute("""SELECT snapshot_sha256, manifest_sha256, code_sha, drive_file_id, drive_file_name,
                   drive_created_at, recorded_at, github_run_attempt, source, artifact_created_at
            FROM research_snapshot_manifests WHERE github_run_id = %s""", (run_id,))
        row = cursor.fetchone()
    if row is None:
        write_github_output({"exists": "false", "drive_file_id": "", "drive_file_name": ""})
        print(json.dumps({"exists": False, "github_run_id": str(run_id)}))
        return 0
    (actual_snapshot, actual_manifest, actual_code, drive_id, drive_name,
     drive_created_at, recorded_at, run_attempt, source, artifact_created_at) = row
    if (actual_snapshot, actual_manifest, actual_code) != (snapshot_sha256, manifest_sha256, code_sha):
        raise SystemExit("github_run_id already exists with different immutable hashes")
    write_github_output({
        "exists": "true", "drive_file_id": drive_id, "drive_file_name": drive_name,
        "drive_created_at": iso_utc(drive_created_at), "recorded_at": iso_utc(recorded_at),
        "run_attempt": run_attempt, "source": source,
        "artifact_created_at": iso_utc(artifact_created_at) if artifact_created_at else "",
    })
    print(json.dumps({"exists": True, "github_run_id": str(run_id), "drive_file_id": drive_id}))
    return 0


def record(connection, args: argparse.Namespace) -> int:
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO research_snapshot_manifests (
              session_date, github_run_id, github_run_attempt, github_actions_started_at, recorded_at,
              code_sha, repository, workflow_ref, snapshot_sha256, manifest_sha256, snapshot_bytes,
              drive_file_id, drive_file_name, drive_created_at, source, artifact_created_at, copy_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'success')""",
            (args.session_date, args.run_id, args.run_attempt, args.actions_started_at, args.recorded_at,
             args.code_sha, args.repository, args.workflow_ref, args.snapshot_sha256, args.manifest_sha256,
             args.snapshot_bytes, args.drive_file_id, args.drive_file_name, args.drive_created_at,
             args.source, args.artifact_created_at))
    connection.commit()
    print(json.dumps({"status": "success", "github_run_id": str(args.run_id),
                      "drive_file_id": args.drive_file_id}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lookup or append a Phase A-0 Neon snapshot manifest")
    parser.add_argument("--database-url", default=os.environ.get("NEON_DATABASE_URL"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("--run-id", type=int, required=True)
    lookup_parser.add_argument("--snapshot-sha256", required=True)
    lookup_parser.add_argument("--manifest-sha256", required=True)
    lookup_parser.add_argument("--code-sha", required=True)
    record_parser = subparsers.add_parser("record")
    for name in ("session-date", "actions-started-at", "recorded-at", "code-sha", "repository",
                 "workflow-ref", "snapshot-sha256", "manifest-sha256", "drive-file-id", "drive-file-name",
                 "drive-created-at"):
        record_parser.add_argument(f"--{name}", required=True)
    record_parser.add_argument("--run-id", type=int, required=True)
    record_parser.add_argument("--run-attempt", type=int, required=True)
    record_parser.add_argument("--snapshot-bytes", type=int, required=True)
    record_parser.add_argument(
        "--source", choices=("google_drive_live", "interim_artifact_recovery"),
        default="google_drive_live",
    )
    record_parser.add_argument("--artifact-created-at")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.database_url:
        raise SystemExit("NEON_DATABASE_URL is not configured")
    with connect(args.database_url) as connection:
        assert_writer_contract(connection)
        if args.command == "lookup":
            return lookup(connection, args.run_id, args.snapshot_sha256, args.manifest_sha256, args.code_sha)
        if args.source == "interim_artifact_recovery" and not args.artifact_created_at:
            raise SystemExit("--artifact-created-at is required for interim_artifact_recovery")
        if args.source == "google_drive_live" and args.artifact_created_at:
            raise SystemExit("--artifact-created-at is only valid for interim_artifact_recovery")
        return record(connection, args)


if __name__ == "__main__":
    raise SystemExit(main())
