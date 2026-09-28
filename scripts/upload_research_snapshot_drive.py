#!/usr/bin/env python3
"""Upload a research snapshot to Google Drive using a refresh token.

This script only creates new files. It never updates or deletes Drive files.
Failures are written to a result JSON and return exit code 0 so the market
publication pipeline can continue; callers decide whether a fallback is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configured() -> bool:
    required = (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
    )
    return all(os.getenv(name) for name in required)


def get_access_token() -> str:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Google OAuth token response did not contain access_token")
    return str(token)


def upload_file(access_token: str, archive: Path, sha256: str, session_date: str) -> dict:
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    metadata: dict = {
        "name": archive.name,
        "appProperties": {
            "sha256": sha256,
            "session_date": session_date,
            "archive_schema": "research.snapshot.archive.v1",
        },
    }
    if folder_id:
        metadata["parents"] = [folder_id]

    init = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        params={
            "uploadType": "resumable",
            "fields": "id,name,size,createdTime,md5Checksum",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/gzip",
            "X-Upload-Content-Length": str(archive.stat().st_size),
        },
        json=metadata,
        timeout=30,
    )
    init.raise_for_status()
    location = init.headers.get("Location")
    if not location:
        raise RuntimeError("Google Drive resumable upload did not return Location")

    with archive.open("rb") as handle:
        upload = requests.put(
            location,
            headers={
                "Content-Type": "application/gzip",
                "Content-Length": str(archive.stat().st_size),
            },
            data=handle,
            timeout=180,
        )
    upload.raise_for_status()
    payload = upload.json()

    if str(payload.get("size")) != str(archive.stat().st_size):
        raise RuntimeError("Google Drive uploaded size does not match local archive")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-result", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    archive_result_path = Path(args.archive_result)
    result_path = Path(args.result_json)
    archive_result = json.loads(archive_result_path.read_text(encoding="utf-8"))
    archive = Path(archive_result["archive_path"])
    if not archive.is_absolute():
        archive = Path.cwd() / archive

    base = {
        "session_date": archive_result["session_date"],
        "github_run_id": archive_result["github_run_id"],
        "github_run_attempt": archive_result["github_run_attempt"],
        "archive_sha256": archive_result["archive_sha256"],
        "archive_name": archive_result["archive_name"],
        "attempted_at": utc_now(),
    }

    if not configured():
        write_json(result_path, {**base, "copy_status": "not_configured"})
        print("Google Drive archive is not configured; keeping fallback preservation.")
        return 0

    try:
        local_sha = sha256_file(archive)
        if local_sha != archive_result["archive_sha256"]:
            raise RuntimeError("archive hash changed before Drive upload")

        access_token = get_access_token()
        drive = upload_file(
            access_token,
            archive,
            local_sha,
            str(archive_result["session_date"]),
        )
        result = {
            **base,
            "copy_status": "success",
            "uploaded_at": utc_now(),
            "drive_file_id": drive.get("id"),
            "drive_file_name": drive.get("name"),
            "drive_file_size": drive.get("size"),
            "drive_created_time": drive.get("createdTime"),
            "drive_md5": drive.get("md5Checksum"),
        }
        write_json(result_path, result)
        print(f"Google Drive upload succeeded: {archive.name}")
    except Exception as exc:
        result = {
            **base,
            "copy_status": "failed",
            "failed_at": utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
        write_json(result_path, result)
        print(f"Google Drive upload failed: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
