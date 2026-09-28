#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.parse

try:
    from scripts.phase_a0.common import write_github_output
    from scripts.phase_a0.upload_google_drive import DRIVE_API, access_token, assert_private_folder, request_json
except ModuleNotFoundError:
    from common import write_github_output
    from upload_google_drive import DRIVE_API, access_token, assert_private_folder, request_json


FOLDER_MIME = "application/vnd.google-apps.folder"


def drive_query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_app_folder(token: str, name: str) -> list[dict[str, str]]:
    query = f"name = '{drive_query_literal(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    url = f"{DRIVE_API}/files?" + urllib.parse.urlencode(
        {"q": query, "spaces": "drive", "fields": "files(id,name)", "pageSize": "10"}
    )
    result, _ = request_json(url, headers={"Authorization": f"Bearer {token}"})
    return result.get("files", [])


def create_folder(token: str, name: str) -> dict[str, str]:
    body = json.dumps({"name": name, "mimeType": FOLDER_MIME}, separators=(",", ":")).encode("utf-8")
    result, _ = request_json(
        f"{DRIVE_API}/files?fields=id,name",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        body=body,
    )
    if not result.get("id"):
        raise RuntimeError("Google Drive folder create response did not contain an id")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the private Drive folder with the same OAuth app used by Actions")
    parser.add_argument("--name", default="market-dashboard-private-snapshots")
    parser.add_argument("--client-id", default=os.environ.get("GOOGLE_DRIVE_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET"))
    parser.add_argument("--refresh-token", default=os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN"))
    args = parser.parse_args()
    missing = [name for name, value in {
        "GOOGLE_DRIVE_CLIENT_ID": args.client_id,
        "GOOGLE_DRIVE_CLIENT_SECRET": args.client_secret,
        "GOOGLE_DRIVE_REFRESH_TOKEN": args.refresh_token,
    }.items() if not value]
    if missing:
        raise SystemExit("Missing Google Drive configuration: " + ", ".join(missing))

    token = access_token(args.client_id, args.client_secret, args.refresh_token)
    matches = find_app_folder(token, args.name)
    if len(matches) > 1:
        raise SystemExit("multiple app-visible folders have the requested name; refusing to guess")
    folder = matches[0] if matches else create_folder(token, args.name)
    assert_private_folder(token, folder["id"])
    result = {"drive_folder_id": folder["id"], "drive_folder_name": folder.get("name", args.name),
              "created": str(not matches).lower()}
    write_github_output(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
