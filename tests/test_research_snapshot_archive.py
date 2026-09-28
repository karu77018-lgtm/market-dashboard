from pathlib import Path

import pytest

from scripts import research_snapshot_archive as archive


def test_deterministic_json_is_stable():
    left = archive.deterministic_json_bytes({"b": 2, "a": 1})
    right = archive.deterministic_json_bytes({"a": 1, "b": 2})
    assert left == right
    assert left == b'{"a":1,"b":2}\n'


def test_secret_scan_rejects_exact_secret(tmp_path: Path, monkeypatch):
    payload = tmp_path / "payload.json"
    payload.write_text('{"token":"super-secret-value"}', encoding="utf-8")
    monkeypatch.setenv("MASSIVE_API_KEY", "super-secret-value")

    with pytest.raises(RuntimeError, match="secret scan failed"):
        archive.scan_for_secrets(tmp_path, [payload])


def test_secret_scan_rejects_api_key_query(tmp_path: Path, monkeypatch):
    payload = tmp_path / "payload.json"
    payload.write_text(
        '{"url":"https://example.test/data?apiKey=abcdef123456"}',
        encoding="utf-8",
    )
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="api_key_query"):
        archive.scan_for_secrets(tmp_path, [payload])


def test_secret_scan_rejects_bearer_token(tmp_path: Path, monkeypatch):
    payload = tmp_path / "payload.txt"
    payload.write_text("Authorization: Bearer abcdefghijklmnop123456", encoding="utf-8")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="bearer_token"):
        archive.scan_for_secrets(tmp_path, [payload])


def test_secret_scan_allows_safe_provider_url(tmp_path: Path, monkeypatch):
    payload = tmp_path / "payload.json"
    payload.write_text('{"url":"https://example.test/data"}', encoding="utf-8")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    archive.scan_for_secrets(tmp_path, [payload])
