#!/usr/bin/env python3
"""Record a research snapshot manifest and storage-copy event in Neon.

The connection should use a dedicated role that can INSERT/SELECT only on the
snapshot manifest tables. Failures are recorded to a local JSON and do not stop
the market publication pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-result", required=True)
    parser.add_argument("--drive-result", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    archive = json.loads(Path(args.archive_result).read_text(encoding="utf-8"))
    drive = json.loads(Path(args.drive_result).read_text(encoding="utf-8"))
    result_path = Path(args.result_json)

    base = {
        "session_date": archive["session_date"],
        "github_run_id": archive["github_run_id"],
        "archive_sha256": archive["archive_sha256"],
        "attempted_at": utc_now(),
    }

    database_url = os.getenv("SNAPSHOT_DATABASE_URL", "").strip()
    if not database_url:
        write_json(result_path, {**base, "record_status": "not_configured"})
        print("Neon snapshot manifest recording is not configured.")
        return 0

    try:
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO snapshot_manifests (
                        session_date,
                        github_run_id,
                        archive_name,
                        archive_sha256,
                        manifest_sha256,
                        byte_size,
                        schema_version,
                        code_sha,
                        generated_at,
                        metadata
                    )
                    VALUES (
                        %(session_date)s,
                        %(github_run_id)s,
                        %(archive_name)s,
                        %(archive_sha256)s,
                        %(manifest_sha256)s,
                        %(byte_size)s,
                        %(schema_version)s,
                        %(code_sha)s,
                        %(generated_at)s,
                        %(metadata)s
                    )
                    ON CONFLICT (github_run_id) DO NOTHING
                    RETURNING id, recorded_at
                    """,
                    {
                        "session_date": archive["session_date"],
                        "github_run_id": int(archive["github_run_id"]),
                        "archive_name": archive["archive_name"],
                        "archive_sha256": archive["archive_sha256"],
                        "manifest_sha256": archive["manifest_sha256"],
                        "byte_size": int(archive["byte_size"]),
                        "schema_version": archive["schema_version"],
                        "code_sha": archive["code_sha"],
                        "generated_at": archive.get("generated_at"),
                        "metadata": Jsonb(
                            {
                                "archive_created_at": archive.get("archive_created_at"),
                                "file_count": archive.get("file_count"),
                            }
                        ),
                    },
                )
                inserted = cur.fetchone()

                if inserted:
                    record_id, recorded_at = inserted
                    status = "success"
                else:
                    cur.execute(
                        """
                        SELECT id, recorded_at, archive_sha256
                        FROM snapshot_manifests
                        WHERE github_run_id = %s
                        """,
                        (int(archive["github_run_id"]),),
                    )
                    existing = cur.fetchone()
                    if not existing:
                        raise RuntimeError("snapshot manifest conflict without existing row")
                    record_id, recorded_at, existing_hash = existing
                    if existing_hash != archive["archive_sha256"]:
                        raise RuntimeError("github_run_id already exists with a different archive hash")
                    status = "duplicate"

                cur.execute(
                    """
                    INSERT INTO snapshot_storage_copies (
                        snapshot_manifest_id,
                        provider,
                        copy_status,
                        storage_object_id,
                        attempted_at,
                        completed_at,
                        metadata
                    )
                    VALUES (
                        %(snapshot_manifest_id)s,
                        'google_drive',
                        %(copy_status)s,
                        %(storage_object_id)s,
                        %(attempted_at)s,
                        %(completed_at)s,
                        %(metadata)s
                    )
                    ON CONFLICT (snapshot_manifest_id, provider, copy_attempt_key) DO NOTHING
                    RETURNING id
                    """,
                    {
                        "snapshot_manifest_id": record_id,
                        "copy_status": drive.get("copy_status", "failed"),
                        "storage_object_id": drive.get("drive_file_id"),
                        "attempted_at": drive.get("attempted_at") or utc_now(),
                        "completed_at": drive.get("uploaded_at") or drive.get("failed_at"),
                        "metadata": Jsonb(
                            {
                                "drive_file_name": drive.get("drive_file_name"),
                                "drive_file_size": drive.get("drive_file_size"),
                                "drive_created_time": drive.get("drive_created_time"),
                                "drive_md5": drive.get("drive_md5"),
                                "error_type": drive.get("error_type"),
                                "error": drive.get("error"),
                            }
                        ),
                    },
                )
                copy_inserted = cur.fetchone()

            conn.commit()

        write_json(
            result_path,
            {
                **base,
                "record_status": status,
                "snapshot_manifest_id": record_id,
                "snapshot_storage_copy_recorded": bool(copy_inserted),
                "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            },
        )
        print(f"Neon snapshot manifest recording: {status}")
    except Exception as exc:
        write_json(
            result_path,
            {
                **base,
                "record_status": "failed",
                "failed_at": utc_now(),
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        )
        print(f"Neon snapshot manifest recording failed: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
