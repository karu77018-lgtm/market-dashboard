#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts.phase_a0.common import sha256_file
    from scripts.phase_a0.neon_manifest import assert_writer_contract, connect, record
    from scripts.phase_a0.upload_google_drive import access_token, assert_private_folder, upload_create_only
except ModuleNotFoundError:
    from common import sha256_file
    from neon_manifest import assert_writer_contract, connect, record
    from upload_google_drive import access_token, assert_private_folder, upload_create_only


REQUIRED_METADATA = {
    "session_date", "github_run_id", "github_run_attempt", "github_actions_started_at",
    "recorded_at", "code_sha", "repository", "workflow_ref", "snapshot_sha256",
    "manifest_sha256", "encrypted_sha256",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover an interim encrypted Artifact into Drive and Neon")
    parser.add_argument("encrypted_snapshot")
    parser.add_argument("metadata")
    parser.add_argument("--artifact-created-at", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--passphrase", default=os.environ.get("ARCHIVE_PASSPHRASE"))
    parser.add_argument("--folder-id", default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID"))
    parser.add_argument("--client-id", default=os.environ.get("GOOGLE_DRIVE_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET"))
    parser.add_argument("--refresh-token", default=os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN"))
    parser.add_argument("--database-url", default=os.environ.get("NEON_DATABASE_URL"))
    args = parser.parse_args()

    missing_config = [name for name, value in {
        "ARCHIVE_PASSPHRASE": args.passphrase,
        "GOOGLE_DRIVE_FOLDER_ID": args.folder_id,
        "GOOGLE_DRIVE_CLIENT_ID": args.client_id,
        "GOOGLE_DRIVE_CLIENT_SECRET": args.client_secret,
        "GOOGLE_DRIVE_REFRESH_TOKEN": args.refresh_token,
        "NEON_DATABASE_URL": args.database_url,
    }.items() if not value]
    if missing_config:
        raise SystemExit("Missing recovery configuration: " + ", ".join(missing_config))

    encrypted = Path(args.encrypted_snapshot)
    metadata_path = Path(args.metadata)
    if not encrypted.is_file() or not metadata_path.is_file():
        raise SystemExit("encrypted snapshot or metadata file is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    missing_metadata = sorted(REQUIRED_METADATA - metadata.keys())
    if missing_metadata:
        raise SystemExit("Missing interim metadata: " + ", ".join(missing_metadata))
    if sha256_file(encrypted) != metadata["encrypted_sha256"]:
        raise SystemExit("encrypted snapshot SHA-256 does not match interim metadata")
    if metadata.get("source") != "interim_encrypted_artifact":
        raise SystemExit("unexpected interim metadata source")
    year, month, day = metadata["session_date"].split("-")
    hash_path = Path(args.root) / "research-hashes" / year / month / day / f"{metadata['github_run_id']}.json"
    if hash_path.exists():
        raise SystemExit(f"immutable hash record already exists: {hash_path}")
    with connect(args.database_url) as connection:
        assert_writer_contract(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM research_snapshot_manifests WHERE github_run_id = %s)",
                (int(metadata["github_run_id"]),),
            )
            if cursor.fetchone()[0]:
                raise SystemExit("Neon manifest already exists for this github_run_id")

    with tempfile.TemporaryDirectory() as temp_raw:
        snapshot_name = (
            f"snapshot-{metadata['session_date']}-{metadata['github_run_id']}-"
            f"{metadata['snapshot_sha256'][:12]}.tar.gz"
        )
        snapshot = Path(temp_raw) / snapshot_name
        recovery_env = os.environ.copy()
        recovery_env["ARCHIVE_PASSPHRASE"] = args.passphrase
        subprocess.run([
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
            "-in", str(encrypted), "-out", str(snapshot), "-pass", "env:ARCHIVE_PASSPHRASE",
        ], check=True, env=recovery_env)
        if sha256_file(snapshot) != metadata["snapshot_sha256"]:
            raise SystemExit("decrypted snapshot SHA-256 does not match interim metadata")

        token = access_token(args.client_id, args.client_secret, args.refresh_token)
        assert_private_folder(token, args.folder_id)
        created = upload_create_only(token, args.folder_id, snapshot)
        drive_id = created.get("id")
        drive_name = created.get("name", snapshot.name)
        drive_created_at = created.get("createdTime")
        if not drive_id or not drive_created_at:
            raise SystemExit("Drive recovery upload did not return id and createdTime")

        record_args = argparse.Namespace(
            session_date=metadata["session_date"], run_id=int(metadata["github_run_id"]),
            run_attempt=int(metadata["github_run_attempt"]),
            actions_started_at=metadata["github_actions_started_at"],
            recorded_at=metadata["recorded_at"], code_sha=metadata["code_sha"],
            repository=metadata["repository"], workflow_ref=metadata["workflow_ref"],
            snapshot_sha256=metadata["snapshot_sha256"],
            manifest_sha256=metadata["manifest_sha256"], snapshot_bytes=snapshot.stat().st_size,
            drive_file_id=drive_id, drive_file_name=drive_name, drive_created_at=drive_created_at,
            source="interim_artifact_recovery", artifact_created_at=args.artifact_created_at,
        )
        with connect(args.database_url) as connection:
            assert_writer_contract(connection)
            record(connection, record_args)

        hash_script = Path(__file__).with_name("write_hash_record.py")
        subprocess.run([
            sys.executable, str(hash_script), "--root", args.root,
            "--session-date", metadata["session_date"], "--run-id", str(metadata["github_run_id"]),
            "--run-attempt", str(metadata["github_run_attempt"]),
            "--actions-started-at", metadata["github_actions_started_at"],
            "--recorded-at", metadata["recorded_at"], "--code-sha", metadata["code_sha"],
            "--sha256", metadata["snapshot_sha256"],
            "--manifest-sha256", metadata["manifest_sha256"],
            "--drive-file-id", drive_id, "--drive-file-name", drive_name,
            "--drive-created-at", drive_created_at, "--repository", metadata["repository"],
            "--workflow-ref", metadata["workflow_ref"], "--source", "interim_artifact_recovery",
            "--artifact-created-at", args.artifact_created_at,
        ], check=True)

    print(json.dumps({
        "status": "success", "github_run_id": str(metadata["github_run_id"]),
        "drive_file_id": drive_id, "source": "interim_artifact_recovery",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
