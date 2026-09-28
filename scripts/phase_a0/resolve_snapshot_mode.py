#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from scripts.phase_a0.common import write_github_output
except ModuleNotFoundError:
    from common import write_github_output


def marker_relative_path(session_date: str) -> str:
    year, month, _day = session_date.split("-")
    return f"research-snapshot-index/{year}/{month}/full.json"


def valid_marker(payload: dict, session_date: str) -> bool:
    return (
        payload.get("schema_version") == "phase-a0-monthly-full-v1"
        and payload.get("month") == session_date[:7]
        and payload.get("snapshot_mode") == "full"
        and payload.get("copy_status") == "success"
        and str(payload.get("github_run_id") or "").isdigit()
    )


def github_marker(repository: str, ref: str, relative: str, token: str) -> dict | None:
    encoded_path = urllib.parse.quote(relative, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise ValueError("GitHub monthly-full marker response is malformed")
    return json.loads(base64.b64decode(payload["content"]).decode("utf-8"))


def resolve(root: Path, session_date: str, repository: str, ref: str, token: str) -> dict:
    relative = marker_relative_path(session_date)
    local = root / relative
    marker = json.loads(local.read_text(encoding="utf-8")) if local.is_file() else None
    marker_source = "local"
    if repository:
        remote = None
        try:
            remote = github_marker(repository, ref, relative, token)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            if marker is not None and valid_marker(marker, session_date):
                print(f"warning: remote marker lookup failed; using valid checked-out marker: {error}")
            else:
                print(f"warning: monthly-full marker lookup failed; choosing full: {error}")
                return {"snapshot_mode": "full", "marker_path": relative, "marker_source": "lookup-failed"}
        if remote is not None:
            marker = remote
            marker_source = "github"
    if marker is None:
        mode = "full"
        marker_source = "missing"
    elif valid_marker(marker, session_date):
        mode = "delta"
    else:
        raise ValueError(f"invalid monthly-full marker: {relative}")
    return {"snapshot_mode": mode, "marker_path": relative, "marker_source": marker_source}


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose full until this month's first full copy succeeds")
    parser.add_argument("--root", default=".")
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--ref", default="main")
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    args = parser.parse_args()
    result = resolve(Path(args.root), args.session_date, args.repository, args.ref, args.token)
    write_github_output(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
