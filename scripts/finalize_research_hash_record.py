#!/usr/bin/env python3
"""Write the public, append-only hash record for one research snapshot run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"hash record already exists: {path}")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-result", required=True)
    parser.add_argument("--drive-result", required=True)
    parser.add_argument("--neon-result", required=True)
    parser.add_argument("--output-root", default="research-hashes")
    args = parser.parse_args()

    archive = read_json(args.archive_result)
    drive = read_json(args.drive_result)
    neon = read_json(args.neon_result)

    session = str(archive["session_date"])
    year, month, day = session.split("-")
    run_id = str(archive["github_run_id"])
    output = Path(args.output_root) / year / month / day / f"{run_id}.json"

    payload = {
        "schema_version": "research.snapshot.hash-record.v1",
        "session_date": session,
        "github_run_id": run_id,
        "archive_sha256": archive["archive_sha256"],
        "manifest_sha256": archive["manifest_sha256"],
        "archive_name": archive["archive_name"],
        "archive_byte_size": archive["byte_size"],
        "code_sha": archive["code_sha"],
        "generated_at": archive.get("generated_at"),
        "archive_created_at": archive.get("archive_created_at"),
        "drive_copy_status": drive.get("copy_status"),
        "neon_record_status": neon.get("record_status"),
        "neon_recorded_at": neon.get("recorded_at"),
    }

    write_json(output, payload)
    print(output.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
