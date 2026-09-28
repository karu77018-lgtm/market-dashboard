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
    parser = argparse.ArgumentParser(description="Write one immutable GitHub hash record per Actions run")
    parser.add_argument("--root", default=".")
    for name in ("session-date", "run-id", "actions-started-at", "recorded-at", "code-sha", "sha256",
                 "manifest-sha256", "drive-file-id", "drive-file-name", "repository", "workflow-ref"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    args = parser.parse_args()
    year, month, day = args.session_date.split("-")
    path = Path(args.root) / "research-hashes" / year / month / day / f"{args.run_id}.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite immutable hash record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"session_date": args.session_date, "github_run_id": str(args.run_id),
        "github_run_attempt": args.run_attempt, "github_actions_started_at": args.actions_started_at,
        "sha256": args.sha256, "manifest_sha256": args.manifest_sha256, "recorded_at": args.recorded_at,
        "code_sha": args.code_sha, "repository": args.repository, "workflow_ref": args.workflow_ref,
        "drive_file_id": args.drive_file_id, "drive_file_name": args.drive_file_name, "copy_status": "success"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    relative = path.relative_to(Path(args.root)).as_posix()
    write_github_output({"hash_record_path": relative})
    print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
