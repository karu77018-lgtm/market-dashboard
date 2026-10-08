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
    fetch_news_bulk,
    load_dashboard,
    wall_near,
    main,
    normalize_news,
    ranking_row,
    validate_jev_url,
)


def _swing_card(sections: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<div class="sw-sec"><span>{title}<small>note</small></span>'
        + (f'<button class="cp" data-tk="{tks}" onclick="copyTk(event,this)">コピー <span class="n">1</span></button>' if tks else "")
        + '</div><div class="sw-t">tile</div>'
        for title, tks in sections)
    return f'<section id="t-alloc"><div class="card" id="mc57-swing-screener">{body}</div></section>'


def test_embedded_json_and_swing_candidate_order(tmp_path: Path):
    html = (
        '<script>window.DET={"BBB":{"sec":"Tech"},"AAA":{"sec":"Health"},"CCC":{}};</script>'
        '<script>window.CALC={"color":"Blue","names":[{"t":"ZZZ","rk":1,"rs":99}]};</script>'
        + _swing_card([("本命", "BBB"), ("まだ入れる", ""), ("次の候補", "AAA,CCC"),
                       ("テーマ枠", "THEME")])
    )
    path = tmp_path / "dashboard.html"
    path.write_text(html, encoding="utf-8")

    assert embedded_json(html, "CALC")["color"] == "Blue"
    candidates, calc = load_dashboard(path, 12)
    tickers = [row["ticker"] for row in candidates]
    assert tickers[:3] == ["BBB", "AAA", "CCC"]
    assert "ZZZ" not in tickers  # archived Core 12 excluded
    assert tickers[3] == "THEME" and candidates[3]["sources"] == ["テーマ枠"]  # Positions tab list
    assert candidates[0]["sources"] == ["本命"]
    assert candidates[1]["sources"] == ["次の候補"]
    assert candidates[1]["detail"]["sec"] == "Health"
    assert calc["color"] == "Blue"


def test_dashboard_candidates_are_only_positions_and_setups_tabs(tmp_path: Path):
    details = {
        "CORE": {"loc": ["Core 12 #1"], "rs21": 10, "rs": 10, "rs189": 10},
        "PICK": {"loc": ["ピックアップ"], "rs21": 40, "rs": 40, "rs189": 40},
        "SHORT": {"loc": [], "rs21": 99, "rs": 20, "rs189": 20},
        "SWING": {"loc": [], "rs21": 50, "rs": 50, "rs189": 50},
    }
    setups = (
        '<section id="t-today"><div class="card"><h2>大化け候補<span class="h2en">Re-Leader</span></h2>'
        '<button class="cp" data-tk="BAG1,SWING" onclick="copyTk(event,this)">コピー</button></div>'
        '<div class="card" id="ipo-base-watch"><h2>IPOベース監視</h2>'
        '<button class="cp" data-tk="IPO1">コピー</button></div></section>'
    )
    midcap = (
        '<div class="card"><h2>拾う枠（監視）<span class="h2en">Mid-cap Leaders</span></h2>'
        '<button class="cp" data-tk="MID1,MID2">コピー</button></div>'
    )
    outside = '<section id="t-rs"><div class="card"><h2>RS</h2><button class="cp" data-tk="RSX"></button></div></section>'
    html = (
        f'<script>window.DET={json.dumps(details)};</script>'
        + setups
        + _swing_card([("本命", ""), ("まだ入れる", "SWING"), ("次の候補", "")]).replace(
            "</section>", midcap + "</section>")
        + outside
    )
    path = tmp_path / "dashboard.html"
    path.write_text(html, encoding="utf-8")

    candidates, _ = load_dashboard(path, 60)
    assert [row["ticker"] for row in candidates] == ["SWING", "MID1", "MID2", "BAG1", "IPO1"]
    by_ticker = {row["ticker"]: row for row in candidates}
    assert by_ticker["SWING"]["sources"] == ["まだ入れる", "大化け候補"]
    assert by_ticker["MID1"]["sources"] == ["拾う枠（監視）"]
    assert by_ticker["IPO1"]["sources"] == ["IPOベース監視"]
    for excluded in ("CORE", "PICK", "SHORT", "RSX"):
        assert excluded not in by_ticker
    candidates, _ = load_dashboard(path, 2)
    assert [row["ticker"] for row in candidates] == ["SWING", "MID1"]


def test_news_filters_drop_passing_mentions_and_price_recaps_and_prefer_releases():
    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    start = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    rows = [
        {"published_utc": "2026-09-28T11:00:00Z", "tickers": ["AAA"],
         "title": "Acme (AAA) Dipped More Than Broader Market Today", "publisher": {"name": "Zacks"}},
        {"published_utc": "2026-09-28T10:00:00Z", "tickers": ["BB", "CC", "DD", "AAA"],
         "title": "BlackBerry: Hold or Sell?", "publisher": {"name": "Zacks"}},
        {"published_utc": "2026-09-28T09:00:00Z", "tickers": ["BB", "CC", "DD", "AAA"],
         "title": "Acme Robotics wins Navy order", "publisher": {"name": "Reuters"}},
        {"published_utc": "2026-09-27T09:00:00Z", "tickers": ["AAA"],
         "title": "Acme raises full-year guidance", "publisher": {"name": "GlobeNewswire Inc."}},
    ]
    result = normalize_news(rows, ticker="AAA", start=start, cutoff=cutoff, limit=8,
                            company_name="Acme Robotics, Inc.")
    assert [item["title"] for item in result] == [
        "Acme raises full-year guidance",  # company release first, despite being older
        "Acme Robotics wins Navy order",   # many tags but the company is named in the title
    ]


def test_fetch_news_bulk_uses_page_calls_not_ticker_calls():
    class Response:
        def __init__(self, payload):
            self.status_code = 200
            self.headers = {}
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class Session:
        def __init__(self):
            self.calls = []
            self.pages = [
                {
                    "results": [
                        {
                            "published_utc": "2026-09-28T11:00:00Z",
                            "tickers": ["AAA", "BBB"],
                            "title": "Shared catalyst",
                            "description": "Evidence",
                            "article_url": "https://example.com/shared",
                            "publisher": {"name": "Wire"},
                        },
                        {
                            "published_utc": "2026-09-28T10:00:00Z",
                            "tickers": ["AAA"],
                            "title": "AAA only",
                            "article_url": "https://example.com/aaa",
                        },
                    ],
                    "next_url": "https://api.massive.com/v2/reference/news?cursor=next",
                },
                {
                    "results": [
                        {
                            "published_utc": "2026-09-27T10:00:00Z",
                            "tickers": ["BBB"],
                            "title": "BBB only",
                            "article_url": "https://example.com/bbb",
                        }
                    ]
                },
            ]

        def get(self, url, *, params, timeout):
            self.calls.append((url, params, timeout))
            return Response(self.pages.pop(0))

    client = Session()
    cutoff = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    start = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    documents, stats = fetch_news_bulk(
        client,
        tickers=["AAA", "BBB"],
        api_key="test-key",
        start=start,
        cutoff=cutoff,
        limit=8,
        timeout=45,
        min_interval=0,
        page_size=1000,
        max_pages=5,
    )

    assert len(client.calls) == 2
    assert [item["title"] for item in documents["AAA"]] == ["Shared catalyst", "AAA only"]
    assert [item["title"] for item in documents["BBB"]] == ["Shared catalyst", "BBB only"]
    assert stats["mode"] == "bulk_window_pagination"
    assert stats["api_calls"] == 2
    assert stats["articles_scanned"] == 3
    assert stats["tickers_with_news"] == 2


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
    assert state["selection"]["rs63_percentile"] is None
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

        @staticmethod
        def json():
            return {
                "ok": True,
                "duplicate": False,
                "evaluationId": "42",
                "gatewayCostUsd": 0.000321,
                "aggregate": {"CAT01_guidance_raise": {"probabilityMean": 0.7}},
            }

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

    assert result == {
        "evaluation_id": "42",
        "duplicate": False,
        "gateway_cost_usd": 0.000321,
        "aggregate": {"CAT01_guidance_raise": {"probabilityMean": 0.7}},
    }
    assert client.request["headers"]["Authorization"] == "Bearer not-a-real-secret"
    assert client.request["json"]["runs"] == 3
    assert client.request["json"]["persist"] is True
    assert client.request["json"]["questionSetVersion"] == "jev-text-v1"
    assert client.request["json"]["evaluationKind"] == "live"
    assert client.request["json"]["validationEligible"] is False
    assert client.request["json"]["asofTimestamp"] == "2026-09-28T12:00:00Z"
    assert client.request["json"]["responseMode"] == "json"


def test_ranking_row_is_positive_minus_risk_probability():
    aggregate = {
        key: {"probabilityMean": 0.6}
        for key in (
            "CAT01_guidance_raise", "CAT02_demand_acceleration", "CAT03_major_contract",
            "CAT04_new_product", "CAT05_regulatory_approval", "CAT06_company_specific",
            "TXT01_management_tone_improved",
        )
    }
    aggregate.update({
        key: {"probabilityMean": 0.2}
        for key in (
            "RF01_dilution", "RF02_going_concern", "RF03_accounting",
            "RF04_management_change", "RF05_legal_regulatory", "RF06_guidance_cut",
            "TXT02_margin_pressure",
        )
    })
    row = ranking_row(
        ticker="AAA", mc57_rank=2, state_sha256="a" * 64,
        evaluation_id="42", news_count=3, aggregate=aggregate,
    )
    assert row["expected_value_score"] == 40.0
    assert row["catalyst_probability"] == 0.6
    assert row["risk_probability"] == 0.2
    assert row["candidate_sources"] == []


def test_missing_required_configuration_is_a_failed_shadow_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "latest-manifest.json").write_text(
        json.dumps({"session_date": "2026-09-25", "generated_at": "2026-09-28T12:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "source-mc57.html").write_text(
        '<script>window.DET={"AAA":{"sec":"Tech"}};</script>'
        '<script>window.CALC={"names":[{"t":"AAA","rk":1,"rs":99}]};</script>'
        + _swing_card([("本命", "AAA")]),
        encoding="utf-8",
    )
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_API_SECRET", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_jev_live_shadow.py", "--root", str(tmp_path)])

    assert main() == 1
    summary = json.loads(
        (tmp_path / ".preservation/jev/live-shadow-summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "configuration_missing"
    assert summary["missing"] == ["MASSIVE_API_KEY", "JEV_API_SECRET"]


def test_jev_is_decoupled_and_audit_artifact_is_private():
    main_workflow = (ROOT / ".github/workflows/refresh-source-mc57.yml").read_text(
        encoding="utf-8"
    )
    jev_workflow = (ROOT / ".github/workflows/refresh-jev-shadow.yml").read_text(
        encoding="utf-8"
    )

    assert "- name: Run Jev live shadow research" not in main_workflow
    assert 'workflows: ["Refresh source-mc57"]' in jev_workflow
    block = jev_workflow.split("- name: Save Jev shadow audit summary", 1)[1].split(
        "- name: Render isolated Jev expected-value ranking tab", 1
    )[0]
    assert "include-hidden-files: true" in block
    assert "cancel-in-progress: true" in jev_workflow


def test_wall_near_is_kept_but_not_a_target(tmp_path: Path):
    details = {
        "FAR": {"opt": {"cw": 120, "cwp": 0.20, "grp": "rs21"}, "rs189": 99},
        "NEARDV": {"opt": {"cw": 104, "cwp": 0.04, "grp": "dv"}, "rs189": 99},
        "NEAR21": {"opt": {"cw": 102, "cwp": 0.02, "grp": "rs21"}, "rs189": 50},
        "BELOW": {"opt": {"cw": 95, "cwp": -0.05, "grp": "rs63"}, "rs189": 90},
    }
    assert wall_near(details) == ["NEAR21", "NEARDV"]
    html = f'<script>window.DET={json.dumps(details)};</script>' + _swing_card([("本命", "FAR")])
    path = tmp_path / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    candidates, _ = load_dashboard(path, 3)
    # Option-wall names outside the two tabs are no longer Jev targets.
    assert [(c["ticker"], c["sources"][0]) for c in candidates] == [("FAR", "本命")]


def test_unrecoverable_duplicate_is_an_error_and_keeps_same_session_ranking(tmp_path: Path, monkeypatch):
    import run_jev_live_shadow as rj
    (tmp_path / "latest-manifest.json").write_text(
        json.dumps({"session_date": "2026-10-02", "generated_at": "2026-10-02T22:00:00Z"}), encoding="utf-8")
    (tmp_path / "source-mc57.html").write_text(
        '<script>window.DET={"AAA":{"sec":"Tech"}};</script>' + _swing_card([("本命", "AAA")]), encoding="utf-8")
    ranking = tmp_path / "data" / "jev-ranking.json"
    ranking.parent.mkdir(parents=True)
    prior = {"session_date": "2026-10-02", "rows": [{"ticker": "OLD", "state_sha256": "zz", "expected_value_score": 1}]}
    ranking.write_text(json.dumps(prior), encoding="utf-8")
    doc = {"title": "t", "description": "d", "published_utc": "2026-10-02T12:00:00Z", "publisher": "p", "url": "u"}
    monkeypatch.setenv("MASSIVE_API_KEY", "m")
    monkeypatch.setenv("JEV_API_SECRET", "j")
    monkeypatch.setattr(rj, "fetch_news_bulk", lambda *a, **k: ({"AAA": [doc]}, {"pages": 1}))
    monkeypatch.setattr(rj, "evaluate_jev", lambda *a, **k: {"evaluation_id": "9", "duplicate": True,
                                                            "gateway_cost_usd": 0, "aggregate": None})
    monkeypatch.setattr(sys, "argv", ["run_jev_live_shadow.py", "--root", str(tmp_path)])
    assert rj.main() == 1                                         # not a silent success
    summary = json.loads((tmp_path / ".preservation/jev/live-shadow-summary.json").read_text())
    assert summary["evaluated_count"] == 0 and summary["error_count"] == 1
    assert json.loads(ranking.read_text()) == prior               # same-session ranking kept
    assert rj.prior_ranking_session(tmp_path / "missing.json") is None
