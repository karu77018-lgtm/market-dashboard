#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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

DELTA_EXTERNAL_PATHS = {
    "source-mc57.html",
    "chart-data",
    "latest-manifest.json",
}


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


def first_observed_session_in_month(ohlcv_path: Path, session_date: str) -> str:
    month = session_date[:7]
    observed: set[str] = set()
    with ohlcv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "date" not in (reader.fieldnames or []):
            raise ValueError("work/ohlcv.csv does not contain a date column")
        for row in reader:
            value = str(row.get("date") or "")
            if value.startswith(month + "-"):
                observed.add(value)
    if session_date not in observed:
        raise ValueError(f"work/ohlcv.csv has no rows for session {session_date}")
    return min(observed)


def resolve_snapshot_mode(root: Path, requested_mode: str, session_date: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    ohlcv_path = root / "work/ohlcv.csv"
    if not ohlcv_path.is_file():
        return "full"
    return "full" if first_observed_session_in_month(ohlcv_path, session_date) == session_date else "delta"


def write_session_ohlcv(source: Path, destination: Path, session_date: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with source.open(newline="", encoding="utf-8") as src, destination.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src)
        if "date" not in (reader.fieldnames or []):
            raise ValueError("work/ohlcv.csv does not contain a date column")
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if str(row.get("date") or "") == session_date:
                writer.writerow(row)
                rows += 1
    if not rows:
        raise ValueError(f"work/ohlcv.csv has no rows for session {session_date}")


def write_session_massive_grouped(source: Path, destination: Path, session_date: str) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict) or not isinstance(sessions.get(session_date), dict):
        raise ValueError(f"work/massive-grouped.json has no session {session_date}")
    reduced = dict(payload)
    reduced["sessions"] = {session_date: sessions[session_date]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(reduced, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def stage_delta_file(root: Path, source: Path, staging: Path, session_date: str) -> Path:
    relative = source.relative_to(root).as_posix()
    destination = staging / relative
    if relative == "work/ohlcv.csv":
        write_session_ohlcv(source, destination, session_date)
        return destination
    if relative == "work/massive-grouped.json":
        write_session_massive_grouped(source, destination, session_date)
        return destination
    return source


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
    parser.add_argument("--snapshot-mode", choices=("auto", "full", "delta"), default="auto")
    parser.add_argument("--path", action="append", dest="paths")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    requested_paths = args.paths or list(DEFAULT_PATHS)
    files = collect_files(root, requested_paths)
    snapshot_mode = resolve_snapshot_mode(root, args.snapshot_mode, args.session_date)
    recorded_at = iso_utc(args.recorded_at)

    with tempfile.TemporaryDirectory(dir=output_dir) as temp_raw:
        temp = Path(temp_raw)
        staging = temp / "staging"
        archived: list[tuple[Path, str]] = []
        external: list[Path] = []
        for path in files:
            relative = path.relative_to(root).as_posix()
            top_level = relative.split("/", 1)[0]
            if snapshot_mode == "delta" and (
                relative in DELTA_EXTERNAL_PATHS or top_level in DELTA_EXTERNAL_PATHS
            ):
                external.append(path)
                continue
            staged = stage_delta_file(root, path, staging, args.session_date) if snapshot_mode == "delta" else path
            archived.append((staged, relative))

        manifest = {
            "schema_version": "phase-a0-v2", "session_date": args.session_date,
            "github_run_id": str(args.run_id),
            "github_actions_started_at": iso_utc(args.actions_started_at),
            "code_sha": args.code_sha, "repository": args.repository, "workflow_ref": args.workflow_ref,
            "snapshot_mode": snapshot_mode,
            "full_snapshot_policy": "first observed US market session of each calendar month",
            "recovery_contract": (
                "self-contained" if snapshot_mode == "full"
                else "apply after the latest preceding full snapshot and each intervening delta; "
                     "external_files are preserved in the linked Git commit"
            ),
            "files": [
                {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path, relative in archived
            ],
            "external_files": [
                {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                 "sha256": sha256_file(path)} for path in external
            ],
        }
        manifest_path = output_dir / "snapshot-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_sha256 = sha256_file(manifest_path)
        tar_path, gzip_path = temp / "snapshot.tar", temp / "snapshot.tar.gz"
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
            for path, relative in archived:
                archive.add(path, arcname=relative, recursive=False, filter=normalized_tar_info)
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
        "recorded_at": recorded_at, "snapshot_mode": snapshot_mode,
    }
    write_github_output(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
