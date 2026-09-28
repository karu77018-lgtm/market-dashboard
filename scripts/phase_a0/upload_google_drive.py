#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import Any

import requests

try:
    from scripts.phase_a0.common import write_github_output
except ModuleNotFoundError:
    from common import write_github_output


TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


def request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
                 body: bytes | Any | None = None, timeout: int = 60) -> tuple[dict[str, Any], requests.Response]:
    try:
        response = requests.request(method, url, headers=headers or {}, data=body, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = getattr(exc.response, "text", "")[:2000]
        raise RuntimeError(f"Google API request failed: {detail or exc}") from exc
    value = response.json() if response.content else {}
    if not isinstance(value, dict):
        raise RuntimeError("Google API returned a non-object response")
    return value, response


def access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    body = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret,
                                   "refresh_token": refresh_token, "grant_type": "refresh_token"}).encode("ascii")
    value, _ = request_json(TOKEN_URL, method="POST",
                            headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body)
    token = value.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("OAuth token response did not contain access_token")
    return token


def assert_private_folder(token: str, folder_id: str) -> None:
    fields = "id,name,mimeType,trashed,capabilities(canAddChildren),permissions(id,type,role,allowFileDiscovery)"
    url = f"{DRIVE_API}/files/{urllib.parse.quote(folder_id)}?" + urllib.parse.urlencode(
        {"fields": fields, "supportsAllDrives": "true"})
    folder, _ = request_json(url, headers={"Authorization": f"Bearer {token}"})
    if folder.get("trashed"):
        raise RuntimeError("Google Drive destination folder is trashed")
    if folder.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID is not a folder")
    if not folder.get("capabilities", {}).get("canAddChildren"):
        raise RuntimeError("OAuth user cannot create files in the Google Drive destination folder")
    if any(permission.get("type") == "anyone" for permission in folder.get("permissions", [])):
        raise RuntimeError("Google Drive destination folder has an 'anyone' permission; refusing private upload")


def upload_create_only(token: str, folder_id: str, path: Path) -> dict[str, Any]:
    content_type = mimetypes.guess_type(path.name)[0] or "application/gzip"
    metadata = json.dumps({"name": path.name, "parents": [folder_id]}, separators=(",", ":")).encode("utf-8")
    query = urllib.parse.urlencode({"uploadType": "resumable", "supportsAllDrives": "true",
                                    "fields": "id,name,createdTime,md5Checksum,size"})
    _, response = request_json(f"{DRIVE_UPLOAD_API}/files?{query}", method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": content_type, "X-Upload-Content-Length": str(path.stat().st_size)},
        body=metadata)
    location = response.headers.get("Location")
    if not location:
        raise RuntimeError("Google Drive did not return a resumable upload URL")
    with path.open("rb") as handle:
        created, _ = request_json(location, method="PUT",
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type,
                     "Content-Length": str(path.stat().st_size)}, body=handle, timeout=900)
    if not created.get("id"):
        raise RuntimeError("Google Drive create response did not contain a file id")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a new private Google Drive snapshot file")
    parser.add_argument("snapshot")
    parser.add_argument("--folder-id", default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID"))
    parser.add_argument("--client-id", default=os.environ.get("GOOGLE_DRIVE_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET"))
    parser.add_argument("--refresh-token", default=os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN"))
    args = parser.parse_args()
    missing = [name for name, value in {"GOOGLE_DRIVE_FOLDER_ID": args.folder_id,
        "GOOGLE_DRIVE_CLIENT_ID": args.client_id, "GOOGLE_DRIVE_CLIENT_SECRET": args.client_secret,
        "GOOGLE_DRIVE_REFRESH_TOKEN": args.refresh_token}.items() if not value]
    if missing:
        raise SystemExit("Missing Google Drive configuration: " + ", ".join(missing))
    snapshot = Path(args.snapshot)
    if not snapshot.is_file():
        raise SystemExit(f"snapshot not found: {snapshot}")
    token = access_token(args.client_id, args.client_secret, args.refresh_token)
    assert_private_folder(token, args.folder_id)
    created = upload_create_only(token, args.folder_id, snapshot)
    result = {"drive_file_id": created["id"], "drive_file_name": created.get("name", snapshot.name),
              "drive_created_time": created.get("createdTime", ""),
              "drive_md5_checksum": created.get("md5Checksum", ""),
              "drive_size": created.get("size", str(snapshot.stat().st_size))}
    write_github_output(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
