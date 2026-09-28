from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scripts.phase_a0.common import sha256_file
from scripts.phase_a0.recover_interim_snapshot import github_artifact_created_at


ROOT = Path(__file__).resolve().parents[1]


def run_script(script: str, *args: str, cwd: Path,
               extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env.update(extra_env or {})
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


def test_secret_scan_detects_unquoted_assignment(tmp_path: Path) -> None:
    key_name = "api" + "_key"
    (tmp_path / "bad.yml").write_text(f"{key_name}: super-secret-value-123\n", encoding="utf-8")
    result = run_script("scripts/phase_a0/scan_secrets.py", "bad.yml", cwd=tmp_path)
    assert result.returncode == 2
    assert "credential-assignment" in result.stdout


def test_secret_scan_detects_url_dsn_and_bearer_forms(tmp_path: Path) -> None:
    query_key = "api" + "Key"
    database_scheme = "postgre" + "sql://"
    bearer_prefix = "Bear" + "er"
    (tmp_path / "leaks.txt").write_text(
        f"https://example.test/data?{query_key}=abcd1234efgh5678\n"
        f"{database_scheme}writer:p4ssword-value@db.example.test/app\n"
        f"Authorization: {bearer_prefix} abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )
    result = run_script("scripts/phase_a0/scan_secrets.py", "leaks.txt", cwd=tmp_path)
    assert result.returncode == 2
    assert "credential-in-url-query" in result.stdout
    assert "postgres-credentials-in-url" in result.stdout
    assert "bearer-token" in result.stdout


def test_secret_scan_matches_raw_and_url_encoded_environment_values(tmp_path: Path) -> None:
    raw_secret = "abc/def+ghi=jkl"
    (tmp_path / "encoded.txt").write_text("abc%2Fdef%2Bghi%3Djkl\n", encoding="utf-8")
    result = run_script(
        "scripts/phase_a0/scan_secrets.py",
        "encoded.txt",
        cwd=tmp_path,
        extra_env={"MASSIVE_API_KEY": raw_secret},
    )
    assert result.returncode == 2
    assert "exact-secret:MASSIVE_API_KEY" in result.stdout


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
        "--drive-created-at", "2026-09-28T01:03:10Z",
        "--repository", "owner/repo", "--workflow-ref", "owner/repo/test.yml@refs/heads/main")
    args += ("--snapshot-mode", "full")
    assert run_script("scripts/phase_a0/write_hash_record.py", *args, cwd=tmp_path).returncode == 0
    assert run_script("scripts/phase_a0/write_hash_record.py", *args, cwd=tmp_path).returncode != 0
    record = json.loads((tmp_path / "research-hashes/2026/09/28/123456789.json").read_text())
    assert record["copy_status"] == "success"
    assert record["drive_file_id"] == "drive-id-1"
    assert record["drive_created_at"] == "2026-09-28T01:03:10Z"
    assert record["source"] == "google_drive_live"


def test_snapshot_hash_is_stable_across_run_attempts(tmp_path: Path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    for directory in (tmp_path / "first", tmp_path / "second"):
        (directory / "payload.json").write_text('{"value":1}\n', encoding="utf-8")
    common = (
        "--root", ".", "--session-date", "2026-09-28", "--run-id", "123456789",
        "--actions-started-at", "2026-09-28T01:02:03Z", "--code-sha", "a" * 40,
        "--repository", "owner/repo", "--workflow-ref", "owner/repo/test.yml@refs/heads/main",
        "--path", "payload.json",
    )
    first = run_script("scripts/phase_a0/build_snapshot.py", *common, "--run-attempt", "1",
                       "--recorded-at", "2026-09-28T01:03:04Z",
                       cwd=tmp_path / "first")
    second = run_script("scripts/phase_a0/build_snapshot.py", *common, "--run-attempt", "2",
                        "--recorded-at", "2026-09-28T01:15:00Z",
                        cwd=tmp_path / "second")
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["snapshot_sha256"] == json.loads(second.stdout)["snapshot_sha256"]
    assert json.loads(first.stdout)["manifest_sha256"] == json.loads(second.stdout)["manifest_sha256"]
    manifest = json.loads((tmp_path / "first/.preservation/private/snapshot-manifest.json").read_text())
    assert "recorded_at" not in manifest
    assert "github_run_attempt" not in manifest


def test_snapshot_auto_uses_monthly_full_then_daily_delta(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "chart-data").mkdir()
    (tmp_path / "data").mkdir()
    base_ohlcv = "ticker,date,close\n" + "".join(
        f"T{index:04d},2026-09-01,{10 + index / 100}\n" for index in range(500)
    )
    base_grouped = {f"T{index:04d}": {"c": 10 + index / 100} for index in range(500)}
    (tmp_path / "work/ohlcv.csv").write_text(base_ohlcv, encoding="utf-8")
    (tmp_path / "work/massive-grouped.json").write_text(json.dumps({
        "schema": "grouped", "sessions": {"2026-09-01": base_grouped},
    }), encoding="utf-8")
    for relative in ("source-mc57.html", "chart-data/index.json", "latest-manifest.json",
                     "data/value.json", "work/massive-reference.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"value":1}\n', encoding="utf-8")

    common = (
        "--root", ".", "--output-dir", ".preservation/private",
        "--run-attempt", "1", "--actions-started-at", "2026-09-28T01:02:03Z",
        "--code-sha", "a" * 40, "--repository", "owner/repo",
        "--workflow-ref", "owner/repo/test.yml@refs/heads/main",
    )
    requested = []
    for relative in ("source-mc57.html", "chart-data", "latest-manifest.json", "data/value.json",
                     "work/ohlcv.csv", "work/massive-reference.json", "work/massive-grouped.json"):
        requested.extend(("--path", relative))

    full = run_script("scripts/phase_a0/build_snapshot.py", *common, "--session-date", "2026-09-01",
                      "--run-id", "1", *requested, cwd=tmp_path)
    (tmp_path / "work/ohlcv.csv").write_text(
        base_ohlcv + "AAA,2026-09-28,11\nBBB,2026-09-28,12\n",
        encoding="utf-8",
    )
    (tmp_path / "work/massive-grouped.json").write_text(json.dumps({
        "schema": "grouped", "sessions": {
            "2026-09-01": base_grouped,
            "2026-09-28": {"AAA": {"c": 11}, "BBB": {"c": 12}},
        },
    }), encoding="utf-8")
    delta = run_script("scripts/phase_a0/build_snapshot.py", *common, "--session-date", "2026-09-28",
                       "--run-id", "2", *requested, cwd=tmp_path)
    assert full.returncode == delta.returncode == 0, full.stderr + delta.stderr
    full_output, delta_output = json.loads(full.stdout), json.loads(delta.stdout)
    assert full_output["snapshot_mode"] == "full"
    assert delta_output["snapshot_mode"] == "delta"
    assert delta_output["snapshot_bytes"] < full_output["snapshot_bytes"]

    with tarfile.open(tmp_path / delta_output["snapshot_path"], "r:gz") as archive:
        names = set(archive.getnames())
        assert "source-mc57.html" not in names
        assert "chart-data/index.json" not in names
        assert "latest-manifest.json" not in names
        ohlcv = archive.extractfile("work/ohlcv.csv").read().decode()
        assert "2026-09-01" not in ohlcv
        assert ohlcv.count("2026-09-28") == 2
        grouped = json.load(archive.extractfile("work/massive-grouped.json"))
        assert list(grouped["sessions"]) == ["2026-09-28"]
        manifest = json.load(archive.extractfile("snapshot-manifest.json"))
        assert manifest["snapshot_mode"] == "delta"
        assert {row["path"] for row in manifest["external_files"]} == {
            "source-mc57.html", "chart-data/index.json", "latest-manifest.json",
        }

    restored = run_script(
        "scripts/phase_a0/restore_snapshot_chain.py",
        full_output["snapshot_path"], delta_output["snapshot_path"],
        "--output", "restored", cwd=tmp_path,
    )
    assert restored.returncode == 0, restored.stderr
    restored_ohlcv = (tmp_path / "restored/work/ohlcv.csv").read_text(encoding="utf-8")
    assert restored_ohlcv.count("2026-09-01") == 500
    assert restored_ohlcv.count("2026-09-28") == 2
    restored_grouped = json.loads(
        (tmp_path / "restored/work/massive-grouped.json").read_text(encoding="utf-8")
    )
    assert set(restored_grouped["sessions"]) == {"2026-09-01", "2026-09-28"}
    report = json.loads(
        (tmp_path / "restored/.preservation/reconstruction-report.json").read_text(encoding="utf-8")
    )
    assert [row["snapshot_mode"] for row in report["applied"]] == ["full", "delta"]


def test_recovery_fetches_artifact_created_at_from_github() -> None:
    payload = json.dumps({"artifacts": [{
        "name": "private-encrypted-snapshot-123-2", "expired": False,
        "created_at": "2026-09-28T08:00:00Z", "workflow_run": {"id": 123},
    }]}).encode()
    with patch("urllib.request.urlopen", return_value=BytesIO(payload)) as mocked:
        actual = github_artifact_created_at("owner/repo", "123", 2, "token")
    assert actual == "2026-09-28T08:00:00Z"
    request = mocked.call_args.args[0]
    assert request.headers["Authorization"] == "Bearer token"
    assert "private-encrypted-snapshot-123-2" in request.full_url


def test_workflow_keeps_vendor_raw_out_of_public_artifact() -> None:
    workflow = (ROOT / ".github/workflows/refresh-source-mc57.yml").read_text(encoding="utf-8")
    artifact = workflow.split("Save public reproducibility artifact", 1)[1].split(
        "Report private preservation failure", 1
    )[0]
    assert "retention-days: 90" in artifact
    assert "include-hidden-files: true" in artifact
    assert "work/ohlcv.csv" not in artifact
    assert "data/mktcap.json" not in artifact
    assert "work/massive-reference.json" not in artifact
    assert "work/massive-grouped.json" not in artifact
    assert "data/market_inputs.json" not in artifact
    assert "data/provider_inputs.json" not in artifact


def test_actions_never_runs_the_neon_migration() -> None:
    workflow = (ROOT / ".github/workflows/refresh-source-mc57.yml").read_text(encoding="utf-8")
    assert "--migration" not in workflow
    assert "continue-on-error: true" in workflow
    assert "if: always() && steps.publication_gates.outcome == 'success'" in workflow
    assert workflow.index("id: publish") < workflow.index(
        "Fail after publication when private preservation failed"
    )
    assert "steps.publish.outcome == 'success'" in workflow
    assert "--drive-created-at" in workflow
    assert "ARCHIVE_PASSPHRASE" in workflow
    assert "private-encrypted-snapshot-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "if: always() && steps.snapshot.outcome == 'success'" in workflow
    assert "steps.interim_artifact.outcome != 'success'" in workflow
