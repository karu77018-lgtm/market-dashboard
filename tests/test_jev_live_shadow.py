from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_jev_live_shadow import (  # noqa: E402
    ShadowRunError,
    candidate_state,
    canonical_hash,
    embedded_json,
    evaluate_jev,
    load_dashboard,
    normalize_news,
    validate_jev_url,
)


def test_embedded_json_and_dashboard_candidate_order(tmp_path: Path):
    html = (
        '<script>window.DET={"BBB":{"sec":"Tech"},"AAA":{"sec":"Health"}};</script>'
        '<script>window.CALC={"color":"Blue","names":['
        '{"t":"BBB","rk":2,"rs":98},{"t":"AAA","rk":1,"rs":99},'
        '{"t":"AAA","rk":3}]};</script>'
    )
    path = tmp_path / "dashboard.html"
    path.write_text(html, encoding="utf-8")

    assert embedded_json(html, "CALC")["color"] == "Blue"
    candidates, calc = load_dashboard(path, 12)
    assert [row["ticker"] for row in candidates] == ["AAA", "BBB"]
    assert candidates[0]["detail"]["sec"] == "Health"
    assert calc["color"] == "Blue"


def test_normalize_news_enforces_point_in_time_and_deduplicates():
    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    start = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    rows = [
        {
            "published_utc": "2026-09-28T11:00:00Z",
            "tickers": ["AAA"],
            "title": "  Current   item ",
            "description": " useful   evidence ",
            "article_url": "https://example.com/a",
            "publisher": {"name": "Wire"},
        },
        {
            "published_utc": "2026-09-28T11:00:00Z",
            "tickers": ["AAA"],
            "title": "Current item",
            "article_url": "https://example.com/a",
        },
        {
            "published_utc": "2026-09-28T13:00:00Z",
            "tickers": ["AAA"],
            "title": "Future item",
        },
        {
            "published_utc": "2026-09-27T11:00:00Z",
            "tickers": ["BBB"],
            "title": "Wrong ticker",
        },
    ]

    result = normalize_news(rows, ticker="AAA", start=start, cutoff=cutoff, limit=8)
    assert result == [
        {
            "source": "massive_news",
            "published_utc": "2026-09-28T11:00:00Z",
            "title": "Current item",
            "description": "useful evidence",
            "publisher": "Wire",
            "article_url": "https://example.com/a",
        }
    ]


def test_state_hash_is_stable_and_state_marks_evidence_boundary():
    candidate = {
        "ticker": "AAA",
        "selection": {"rk": 1, "rs": 99, "px": 12.5, "r5": 4.2, "d52": -3.0},
        "detail": {"sec": "Tech", "sth": "Software", "cap": "Small"},
    }
    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    documents = [{"title": "Evidence", "published_utc": "2026-09-28T10:00:00Z"}]
    state = candidate_state(
        candidate,
        company_name="AAA Inc.",
        documents=documents,
        manifest={"session_date": "2026-09-25", "mc57": 31.6, "mc57_status": "READY"},
        calc={"color": "Blue"},
        cutoff=cutoff,
        lookback_days=30,
    )

    assert state["available_at"] == "2026-09-28T12:00:00Z"
    assert state["evidence"]["documents"] == documents
    assert state["selection"]["mc57_rank"] == 1
    assert canonical_hash(state) == canonical_hash(json.loads(json.dumps(state)))


@pytest.mark.parametrize(
    "url",
    ["https://jev.example/api/jev", "http://localhost:3000/api/jev", "http://127.0.0.1/api/jev"],
)
def test_validate_jev_url_accepts_https_and_localhost(url: str):
    assert validate_jev_url(url) == url


def test_validate_jev_url_rejects_remote_http():
    with pytest.raises(ShadowRunError):
        validate_jev_url("http://jev.example/api/jev")


def test_evaluate_jev_uses_fixed_persisted_shadow_contract():
    class Response:
        status_code = 200
        text = "Jev OK\nEvaluation: #42\nCost: $0.000321\n"

    class Session:
        request = None

        def post(self, url, *, headers, json, timeout):
            self.request = {"url": url, "headers": headers, "json": json, "timeout": timeout}
            return Response()

    client = Session()
    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    result = evaluate_jev(
        client,
        url="https://jev.example/api/jev",
        secret="not-a-real-secret",
        ticker="AAA",
        state={"evidence": {"documents": [{"title": "Item"}]}},
        cutoff=cutoff,
        timeout=180,
    )

    assert result == {"evaluation_id": "42", "duplicate": False, "gateway_cost_usd": 0.000321}
    assert client.request["headers"]["Authorization"] == "Bearer not-a-real-secret"
    assert client.request["json"]["runs"] == 3
    assert client.request["json"]["persist"] is True
    assert client.request["json"]["questionSetVersion"] == "jev-text-v1"
    assert client.request["json"]["evaluationKind"] == "live"
    assert client.request["json"]["validationEligible"] is False
    assert client.request["json"]["asofTimestamp"] == "2026-09-28T12:00:00Z"
