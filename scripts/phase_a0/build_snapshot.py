#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.phase_a0.common import sha256_file, write_github_output
except ModuleNotFoundError:
    from common import sha256_file, write_github_output


DEFAULT_PATHS = (
    "source-mc57.html", "chart-data", "latest-manifest.json", "data/mc57.json",
    "data/state.json", "data/rs.json", "data/market_inputs.json", "data/mktcap.json",
    "data/theme_membership.json", "data/provider_inputs.json", "work/ohlcv.csv",
    "work/massive-reference.json", "work/massive-grouped.json",
)


def iso_utc(value: str | None = None) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def collect_files(root: Path, requested: list[str]) -> list[Path]:
    files: set[Path] = set()
    for raw in requested:
        path = root / raw
        if not path.exists():
            raise FileNotFoundError(f"required snapshot path is missing: {raw}")
        files.update(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else files.add(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def normalized_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the private Phase A-0 preservation snapshot")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", default=".preservation/private")
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--actions-started-at", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--recorded-at")
    parser.add_argument("--path", action="append", dest="paths")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    files = collect_files(root, args.paths or list(DEFAULT_PATHS))
    recorded_at = iso_utc(args.recorded_at)
    manifest = {
        "schema_version": "phase-a0-v1", "session_date": args.session_date,
        "github_run_id": str(args.run_id),
        "github_actions_started_at": iso_utc(args.actions_started_at),
        "code_sha": args.code_sha, "repository": args.repository, "workflow_ref": args.workflow_ref,
        "files": [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256_file(path)} for path in files],
    }
    manifest_path = output_dir / "snapshot-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha256 = sha256_file(manifest_path)

    with tempfile.TemporaryDirectory(dir=output_dir) as temp_raw:
        temp = Path(temp_raw)
        tar_path, gzip_path = temp / "snapshot.tar", temp / "snapshot.tar.gz"
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False, filter=normalized_tar_info)
            archive.add(manifest_path, arcname="snapshot-manifest.json", recursive=False, filter=normalized_tar_info)
        with tar_path.open("rb") as source, gzip_path.open("wb") as destination:
            with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressor:
                shutil.copyfileobj(source, compressor, length=1024 * 1024)
        snapshot_sha256 = sha256_file(gzip_path)
        final_path = output_dir / f"snapshot-{args.session_date}-{args.run_id}-{snapshot_sha256[:12]}.tar.gz"
        if final_path.exists():
            raise FileExistsError(f"refusing to overwrite snapshot: {final_path}")
        os.replace(gzip_path, final_path)

    result = {
        "snapshot_path": final_path.relative_to(root).as_posix(), "snapshot_name": final_path.name,
        "snapshot_sha256": snapshot_sha256, "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": manifest_sha256, "snapshot_bytes": final_path.stat().st_size,
        "recorded_at": recorded_at,
    }
    write_github_output(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
