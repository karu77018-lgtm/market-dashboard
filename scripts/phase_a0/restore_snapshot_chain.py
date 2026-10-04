#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

try:
    from scripts.phase_a0.common import sha256_file
except ModuleNotFoundError:
    from common import sha256_file


def safe_member_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe snapshot member path: {name}")
    return path.as_posix()


def verified_archive(snapshot: Path) -> tuple[dict, dict[str, bytes]]:
    with tarfile.open(snapshot, "r:gz") as archive:
        members: dict[str, tarfile.TarInfo] = {}
        for member in archive.getmembers():
            name = safe_member_name(member.name)
            if name in members:
                raise ValueError(f"snapshot contains a duplicate member: {name}")
            members[name] = member
        if any(not member.isfile() for member in members.values()):
            raise ValueError(f"snapshot contains a non-regular member: {snapshot}")
        manifest_member = members.get("snapshot-manifest.json")
        if not manifest_member:
            raise ValueError(f"snapshot manifest is missing: {snapshot}")
        manifest = json.load(archive.extractfile(manifest_member))
        payloads: dict[str, bytes] = {}
        expected_paths = {row["path"] for row in manifest.get("files", [])}
        unexpected = set(members) - expected_paths - {"snapshot-manifest.json"}
        if unexpected:
            raise ValueError(f"snapshot contains unmanifested files: {sorted(unexpected)}")
        for row in manifest.get("files", []):
            name = safe_member_name(row["path"])
            member = members.get(name)
            if not member:
                raise ValueError(f"manifested file is missing from snapshot: {name}")
            data = archive.extractfile(member).read()
            if len(data) != int(row["bytes"]):
                raise ValueError(f"size mismatch for snapshot member: {name}")
            with tempfile.NamedTemporaryFile() as handle:
                handle.write(data)
                handle.flush()
                if sha256_file(Path(handle.name)) != row["sha256"]:
                    raise ValueError(f"SHA-256 mismatch for snapshot member: {name}")
            payloads[name] = data
    return manifest, payloads


def merge_ohlcv(existing: Path, delta: bytes) -> bytes:
    def rows(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
        text = raw.decode("utf-8").splitlines()
        reader = csv.DictReader(text)
        return list(reader.fieldnames or []), list(reader)

    old_fields, old_rows = rows(existing.read_bytes()) if existing.is_file() else ([], [])
    new_fields, new_rows = rows(delta)
    if not new_fields or "ticker" not in new_fields or "date" not in new_fields:
        raise ValueError("delta work/ohlcv.csv is missing ticker/date columns")
    if old_fields and old_fields != new_fields:
        raise ValueError("full and delta OHLCV columns do not match")
    merged = {(row["ticker"], row["date"]): row for row in old_rows}
    merged.update({(row["ticker"], row["date"]): row for row in new_rows})
    with tempfile.TemporaryFile(mode="w+", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=new_fields)
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])
        handle.seek(0)
        return handle.read().encode("utf-8")


def merge_massive_grouped(existing: Path, delta: bytes) -> bytes:
    current = json.loads(existing.read_text(encoding="utf-8")) if existing.is_file() else {}
    incoming = json.loads(delta)
    sessions = current.get("sessions") if isinstance(current.get("sessions"), dict) else {}
    sessions.update(incoming.get("sessions") or {})
    fallbacks = current.get("fallback_sessions") if isinstance(current.get("fallback_sessions"), dict) else {}
    fallbacks.update(incoming.get("fallback_sessions") or {})
    current.update({key: value for key, value in incoming.items()
                    if key not in {"sessions", "fallback_sessions"}})
    current["sessions"] = dict(sorted(sessions.items()))
    if fallbacks:
        current["fallback_sessions"] = dict(sorted(fallbacks.items()))
    return (json.dumps(current, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        handle.write(data)
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_external(applied: list[dict], output: Path, external_root: Path | None) -> list[dict]:
    """External files (kept in Git, not in the delta) of the latest snapshot must be
    present with the recorded hash; copy them from ``external_root`` when given.
    Returns the files that are still missing or different."""
    import shutil
    latest = applied[-1].get("external_files") or [] if applied else []
    unresolved = []
    for row in latest:
        rel, want = str(row.get("path") or ""), str(row.get("sha256") or "")
        if not rel or not want:
            unresolved.append({"path": rel, "reason": "no recorded hash"})
            continue
        target = output / rel
        if not (target.is_file() and _sha256(target) == want) and external_root is not None:
            source = external_root / rel
            if source.is_file() and _sha256(source) == want:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if not (target.is_file() and _sha256(target) == want):
            unresolved.append({"path": rel, "reason": "missing or hash mismatch"})
    return unresolved


def restore_chain(snapshots: list[Path], output: Path, external_root: Path | None = None) -> dict:
    if not snapshots:
        raise ValueError("at least one snapshot is required")
    if output.exists() and any(output.iterdir()):
        raise ValueError("reconstruction output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    applied: list[dict] = []
    previous_key: tuple[str, int] | None = None
    for index, snapshot in enumerate(snapshots):
        manifest, payloads = verified_archive(snapshot)
        mode = manifest.get("snapshot_mode", "full")
        session = str(manifest.get("session_date") or "")
        run_id_text = str(manifest.get("github_run_id") or "")
        if not run_id_text.isdigit():
            raise ValueError("snapshot github_run_id must be an integer")
        order_key = (session, int(run_id_text))
        if index == 0 and mode != "full":
            raise ValueError("the first snapshot in a reconstruction chain must be full")
        if index > 0 and mode != "delta":
            raise ValueError("only delta snapshots may follow the first full snapshot")
        if not session or (previous_key is not None and order_key <= previous_key):
            raise ValueError("snapshots must be strictly increasing by (session_date, github_run_id)")
        previous_key = order_key
        for name, data in payloads.items():
            target = output / name
            if mode == "delta" and name == "work/ohlcv.csv":
                data = merge_ohlcv(target, data)
            elif mode == "delta" and name == "work/massive-grouped.json":
                data = merge_massive_grouped(target, data)
            atomic_write(target, data)
        manifest_path = (
            output / ".preservation/applied-manifests" /
            f"{session}-{manifest.get('github_run_id', 'unknown')}.json"
        )
        atomic_write(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        applied.append({
            "session_date": session,
            "github_run_id": str(manifest.get("github_run_id") or ""),
            "snapshot_mode": mode,
            "external_files": manifest.get("external_files", []),
        })
    unresolved = resolve_external(applied, output, external_root)
    # A reconstruction is complete only when every external file matches its hash.
    result = {"status": "success" if not unresolved else "incomplete_external",
              "output": str(output), "applied": applied, "unresolved_external": unresolved}
    atomic_write(
        output / ".preservation/reconstruction-report.json",
        (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore one monthly full snapshot and its daily deltas")
    parser.add_argument("snapshots", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--external-root", help="Git checkout of the snapshot's commit, for external files")
    args = parser.parse_args()
    result = restore_chain([Path(value) for value in args.snapshots], Path(args.output),
                           Path(args.external_root) if args.external_root else None)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
