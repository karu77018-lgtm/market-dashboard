#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

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


def ensure_schema(connection, migration_path: Path) -> None:
    sql = migration_path.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.split("-- statement-breakpoint") if part.strip()]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    connection.commit()


def lookup(connection, run_id: int, snapshot_sha256: str, manifest_sha256: str, code_sha: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute("""SELECT snapshot_sha256, manifest_sha256, code_sha, drive_file_id, drive_file_name
            FROM research_snapshot_manifests WHERE github_run_id = %s""", (run_id,))
        row = cursor.fetchone()
    if row is None:
        write_github_output({"exists": "false", "drive_file_id": "", "drive_file_name": ""})
        print(json.dumps({"exists": False, "github_run_id": str(run_id)}))
        return 0
    actual_snapshot, actual_manifest, actual_code, drive_id, drive_name = row
    if (actual_snapshot, actual_manifest, actual_code) != (snapshot_sha256, manifest_sha256, code_sha):
        raise SystemExit("github_run_id already exists with different immutable hashes")
    write_github_output({"exists": "true", "drive_file_id": drive_id, "drive_file_name": drive_name})
    print(json.dumps({"exists": True, "github_run_id": str(run_id), "drive_file_id": drive_id}))
    return 0


def record(connection, args: argparse.Namespace) -> int:
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO research_snapshot_manifests (
              session_date, github_run_id, github_run_attempt, github_actions_started_at, recorded_at,
              code_sha, repository, workflow_ref, snapshot_sha256, manifest_sha256, snapshot_bytes,
              drive_file_id, drive_file_name, copy_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'success')""",
            (args.session_date, args.run_id, args.run_attempt, args.actions_started_at, args.recorded_at,
             args.code_sha, args.repository, args.workflow_ref, args.snapshot_sha256, args.manifest_sha256,
             args.snapshot_bytes, args.drive_file_id, args.drive_file_name))
    connection.commit()
    print(json.dumps({"status": "success", "github_run_id": str(args.run_id),
                      "drive_file_id": args.drive_file_id}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lookup or append a Phase A-0 Neon snapshot manifest")
    parser.add_argument("--database-url", default=os.environ.get("NEON_DATABASE_URL"))
    parser.add_argument("--migration", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("--run-id", type=int, required=True)
    lookup_parser.add_argument("--snapshot-sha256", required=True)
    lookup_parser.add_argument("--manifest-sha256", required=True)
    lookup_parser.add_argument("--code-sha", required=True)
    record_parser = subparsers.add_parser("record")
    for name in ("session-date", "actions-started-at", "recorded-at", "code-sha", "repository",
                 "workflow-ref", "snapshot-sha256", "manifest-sha256", "drive-file-id", "drive-file-name"):
        record_parser.add_argument(f"--{name}", required=True)
    record_parser.add_argument("--run-id", type=int, required=True)
    record_parser.add_argument("--run-attempt", type=int, required=True)
    record_parser.add_argument("--snapshot-bytes", type=int, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.database_url:
        raise SystemExit("NEON_DATABASE_URL is not configured")
    with connect(args.database_url) as connection:
        ensure_schema(connection, Path(args.migration))
        if args.command == "lookup":
            return lookup(connection, args.run_id, args.snapshot_sha256, args.manifest_sha256, args.code_sha)
        return record(connection, args)


if __name__ == "__main__":
    raise SystemExit(main())
