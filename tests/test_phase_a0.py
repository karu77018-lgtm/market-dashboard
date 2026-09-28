from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.phase_a0.common import sha256_file


ROOT = Path(__file__).resolve().parents[1]


def run_script(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, str(ROOT / script), *args], cwd=cwd, text=True,
                          capture_output=True, check=False, env=env)


def test_secret_scan_detects_embedded_api_key(tmp_path: Path) -> None:
    fake_value = "super-" + "secret-value-123"
    (tmp_path / "bad.json").write_text(json.dumps({"api_key": fake_value}) + "\n", encoding="utf-8")
    result = run_script("scripts/phase_a0/scan_secrets.py", "bad.json", cwd=tmp_path)
    assert result.returncode == 2
    assert "credential-assignment" in result.stdout


def test_secret_scan_allows_environment_reference(tmp_path: Path) -> None:
    (tmp_path / "safe.yml").write_text('api_key: "${{ secrets.API_KEY }}"\n', encoding="utf-8")
    assert run_script("scripts/phase_a0/scan_secrets.py", "safe.yml", cwd=tmp_path).returncode == 0


def test_snapshot_and_hash_record_are_immutable(tmp_path: Path) -> None:
    (tmp_path / "payload.json").write_text('{"value":1}\n', encoding="utf-8")
    result = run_script("scripts/phase_a0/build_snapshot.py", "--root", ".", "--output-dir",
        ".preservation/private", "--session-date", "2026-09-28", "--run-id", "123456789",
        "--run-attempt", "1", "--actions-started-at", "2026-09-28T01:02:03Z",
        "--recorded-at", "2026-09-28T01:03:04Z", "--code-sha", "a" * 40,
        "--repository", "owner/repo", "--workflow-ref", "owner/repo/test.yml@refs/heads/main",
        "--path", "payload.json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    snapshot = tmp_path / output["snapshot_path"]
    assert sha256_file(snapshot) == output["snapshot_sha256"]
    args = ("--root", ".", "--session-date", "2026-09-28", "--run-id", "123456789",
        "--run-attempt", "1", "--actions-started-at", "2026-09-28T01:02:03Z",
        "--recorded-at", output["recorded_at"], "--code-sha", "a" * 40,
        "--sha256", output["snapshot_sha256"], "--manifest-sha256", output["manifest_sha256"],
        "--drive-file-id", "drive-id-1", "--drive-file-name", snapshot.name,
        "--repository", "owner/repo", "--workflow-ref", "owner/repo/test.yml@refs/heads/main")
    assert run_script("scripts/phase_a0/write_hash_record.py", *args, cwd=tmp_path).returncode == 0
    assert run_script("scripts/phase_a0/write_hash_record.py", *args, cwd=tmp_path).returncode != 0
    record = json.loads((tmp_path / "research-hashes/2026/09/28/123456789.json").read_text())
    assert record["copy_status"] == "success"
    assert record["drive_file_id"] == "drive-id-1"
