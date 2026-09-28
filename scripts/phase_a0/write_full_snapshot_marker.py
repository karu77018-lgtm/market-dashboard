#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.phase_a0.common import write_github_output
except ModuleNotFoundError:
    from common import write_github_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the first successfully preserved monthly full snapshot")
    parser.add_argument("--root", default=".")
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--preservation-source", choices=("google_drive_live", "interim_encrypted_artifact"), required=True)
    parser.add_argument("--preservation-reference", required=True)
    args = parser.parse_args()

    year, month, _day = args.session_date.split("-")
    path = Path(args.root) / "research-snapshot-index" / year / month / "full.json"
    payload = {
        "schema_version": "phase-a0-monthly-full-v1",
        "month": f"{year}-{month}",
        "session_date": args.session_date,
        "github_run_id": str(args.run_id),
        "github_run_attempt": args.run_attempt,
        "code_sha": args.code_sha,
        "snapshot_mode": "full",
        "snapshot_sha256": args.snapshot_sha256,
        "manifest_sha256": args.manifest_sha256,
        "preservation_source": args.preservation_source,
        "preservation_reference": args.preservation_reference,
        "copy_status": "success",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(f"refusing to replace monthly-full marker: {path}")
    else:
        path.write_text(encoded, encoding="utf-8")
    relative = path.relative_to(Path(args.root)).as_posix()
    write_github_output({"full_marker_path": relative})
    print(json.dumps({"full_marker_path": relative}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
