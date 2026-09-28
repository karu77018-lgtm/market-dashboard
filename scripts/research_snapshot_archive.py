#!/usr/bin/env python3
"""Create a deterministic, secret-scanned research snapshot archive.

The archive is content-addressed. Run-specific metadata (GitHub run id,
recorded time, Drive file id) lives outside the tarball so rerunning the same
commit with the same source files produces the same archive hash.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "research.snapshot.archive.v1"

REQUIRED_FILES = (
    "source-mc57.html",
    "latest-manifest.json",
    "work/ohlcv.csv",
    "work/massive-reference.json",
    "work/massive-grouped.json",
)

OPTIONAL_GLOBS = (
    "data/*.json",
)

SECRET_ENV_NAMES = (
    "FRED_API_KEY",
    "MASSIVE_API_KEY",
    "SNAPSHOT_DATABASE_URL",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REFRESH_TOKEN",
)

SUSPICIOUS_PATTERNS = (
    ("api_key_query", re.compile(rb"(?i)(?:api[_-]?key|apikey)=[^&\s\"'<>]{6,}")),
    ("bearer_token", re.compile(rb"(?i)\bbearer\s+[A-Za-z0-9._~+\-/=]{12,}")),
    ("postgres_url", re.compile(rb"(?i)\bpostgres(?:ql)?://[^\s\"'<>]+")),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def changed_chart_files(root: Path) -> list[Path]:
    """Return chart-data files changed relative to HEAD plus untracked files."""
    commands = (
        ["git", "diff", "--name-only", "HEAD", "--", "chart-data"],
        ["git", "ls-files", "--others", "--exclude-standard", "--", "chart-data"],
    )
    names: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            value = line.strip()
            if value:
                names.add(value)
    return sorted(
        (root / name for name in names if (root / name).is_file()),
        key=lambda p: p.as_posix(),
    )


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    missing: list[str] = []

    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        else:
            files.append(path)

    if missing:
        raise RuntimeError("required snapshot files are missing: " + ", ".join(missing))

    for pattern in OPTIONAL_GLOBS:
        files.extend(path for path in root.glob(pattern) if path.is_file())

    files.extend(changed_chart_files(root))

    unique = {path.relative_to(root).as_posix(): path for path in files}
    return [unique[key] for key in sorted(unique)]


def scan_for_secrets(root: Path, files: Iterable[Path]) -> None:
    exact_values: list[tuple[str, bytes]] = []
    for name in SECRET_ENV_NAMES:
        value = os.getenv(name, "")
        if len(value) >= 6:
            exact_values.append((name, value.encode("utf-8")))

    findings: list[str] = []
    for path in files:
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix()

        for name, secret in exact_values:
            if secret in data:
                findings.append(f"{rel}: exact value from {name}")

        for label, pattern in SUSPICIOUS_PATTERNS:
            if pattern.search(data):
                findings.append(f"{rel}: suspicious pattern {label}")

    if findings:
        raise RuntimeError(
            "secret scan failed; snapshot not created:\n- " + "\n- ".join(findings)
        )


def deterministic_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    import io
    tar.addfile(info, io.BytesIO(data))


def add_file(tar: tarfile.TarFile, root: Path, path: Path) -> None:
    data = path.read_bytes()
    add_bytes(tar, path.relative_to(root).as_posix(), data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default="work/research-snapshot")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument(
        "--result-json",
        default="work/research-snapshot/archive-result.json",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source_manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
    session_date = str(source_manifest["session_date"])
    generated_at = source_manifest.get("generated_at")

    files = collect_files(root)
    scan_for_secrets(root, files)

    file_entries = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        file_entries.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    payload_manifest = {
        "schema_version": SCHEMA_VERSION,
        "session_date": session_date,
        "generated_at": generated_at,
        "code_sha": args.code_sha,
        "source_schema_version": source_manifest.get("schema_version"),
        "calculation_version": source_manifest.get("calculation_version"),
        "files": file_entries,
    }
    payload_manifest_bytes = deterministic_json_bytes(payload_manifest)
    manifest_sha256 = sha256_bytes(payload_manifest_bytes)

    temp_path = output_dir / "snapshot.tar.gz.tmp"
    with temp_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                add_bytes(tar, "snapshot-manifest.json", payload_manifest_bytes)
                for path in files:
                    add_file(tar, root, path)

    archive_sha256 = sha256_file(temp_path)
    archive_name = (
        f"snapshot-{session_date}-{args.run_id}-a{args.run_attempt}-{archive_sha256[:12]}.tar.gz"
    )
    archive_path = output_dir / archive_name
    temp_path.replace(archive_path)

    result = {
        "schema_version": SCHEMA_VERSION,
        "session_date": session_date,
        "github_run_id": str(args.run_id),
        "github_run_attempt": int(args.run_attempt),
        "code_sha": args.code_sha,
        "generated_at": generated_at,
        "archive_created_at": utc_now(),
        "archive_name": archive_name,
        "archive_path": archive_path.relative_to(root).as_posix(),
        "archive_sha256": archive_sha256,
        "manifest_sha256": manifest_sha256,
        "byte_size": archive_path.stat().st_size,
        "file_count": len(file_entries),
    }

    result_path = root / args.result_json
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_bytes(deterministic_json_bytes(result))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
