from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from provider_inputs import (  # noqa: E402
    ProviderError,
    _get_json,
    _normalize_grouped_results,
    compute_massive_market_structure,
    grouped_history_from_yahoo_ohlcv,
    select_preserved_count_fallback_universe,
    select_expanded_universe,
)


def test_massive_entitlement_403_is_not_retried(monkeypatch):
    class Response:
        status_code = 403
        headers = {}

        def raise_for_status(self):
            raise AssertionError("4xx should be handled before raise_for_status")

        def json(self):
            return {"status": "NOT_AUTHORIZED"}

    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=45):
            self.calls += 1
            return Response()

    session = Session()
    monkeypatch.setattr("provider_inputs.time.sleep", lambda _: None)

    with pytest.raises(ProviderError, match="status=403"):
        _get_json(
            session,
            "https://api.massive.com/v2/example",
            params={"apiKey": "test"},
            attempts=5,
        )

    assert session.calls == 1


def grouped_history() -> dict:
    history = {}
    for i in range(20):
        day = f"2026-09-{i + 1:02d}"
        history[day] = {
            "CORE": {"c": 10 + i * .1, "h": 10.5 + i * .1, "l": 9.5 + i * .1, "v": 3_000_000},
            "ADD": {"c": 8 + i * .1, "h": 8.5 + i * .1, "l": 7.5 + i * .1, "v": 4_000_000},
            "ILLQ": {"c": 8 + i * .1, "h": 8.5 + i * .1, "l": 7.5 + i * .1, "v": 1_000},
        }
    return history


def test_normalize_grouped_filters_and_maps_fields():
    rows = _normalize_grouped_results(
        [
            {"T": "A", "c": 10, "h": 11, "l": 9, "v": 1000, "o": 9.5, "n": 42},
            {"T": "B", "c": 5, "h": 6, "l": 4, "v": 100},
            {"T": "A", "c": ".", "h": 11, "l": 9, "v": 1000},
        ],
        {"A"},
    )
    assert set(rows) == {"A"}
    assert rows["A"]["c"] == 10
    assert rows["A"]["n"] == 42


def test_universe_is_broad_and_buy_filters_are_annotations_only():
    history = grouped_history()
    target = "2026-09-20"
    broad = [
        {"ticker": "CORE", "price": 12, "market_cap": 300_000_000},
        {"ticker": "ADD", "price": 10, "market_cap": 100_000_000},
        {"ticker": "ILLQ", "price": 10, "market_cap": 100_000_000},
        {"ticker": "NOREF", "price": 10, "market_cap": 100_000_000},
    ]
    reference = {
        ticker: {"ticker": ticker, "type": "CS", "primary_exchange": "XNAS"}
        for ticker in ("CORE", "ADD", "ILLQ")
    }
    selected, stats = select_expanded_universe(
        broad, reference, history, target_session=target,
    )
    assert [row["ticker"] for row in selected] == ["ADD", "CORE", "ILLQ"]
    assert stats["legacy_universe"] == 1
    assert stats["massive_broad_expansion"] == 2
    assert stats["buy_filter_eligible"] == 2
    assert stats["massive_current_coverage"] == 1.0
    rows = {row["ticker"]: row for row in selected}
    assert rows["ADD"]["buy_filter_eligible"] is True
    assert rows["ILLQ"]["buy_filter_eligible"] is False
    assert rows["ILLQ"]["buy_filter_failures"] == ["median_dollar_volume_20"]


def test_market_structure_counts_and_volume():
    grouped = {
        "2026-09-24": {
            "A": {"c": 100, "h": 101, "l": 99, "v": 10},
            "B": {"c": 100, "h": 101, "l": 99, "v": 20},
        },
        "2026-09-25": {
            "A": {"c": 105, "h": 106, "l": 99, "v": 30},
            "B": {"c": 95, "h": 101, "l": 94, "v": 40},
        },
    }
    result = compute_massive_market_structure(
        ["A", "B"], grouped, target_session="2026-09-25",
    )
    assert result["advances"] == 1
    assert result["declines"] == 1
    assert result["four_pct_net"] == 0
    assert result["up_down_volume_ratio"] == pytest.approx(.75)
    assert result["coverage"] == 1.0


def test_yahoo_fallback_preserves_prior_universe_count():
    history = grouped_history()
    broad = [
        {"ticker": "CORE", "price": 12, "market_cap": 300_000_000},
        {"ticker": "ADD", "price": 10, "market_cap": 100_000_000},
        {"ticker": "ILLQ", "price": 10, "market_cap": 100_000_000},
    ]
    reference = {
        ticker: {"ticker": ticker, "type": "CS", "primary_exchange": "XNAS"}
        for ticker in ("CORE", "ADD", "ILLQ")
    }
    selected, stats = select_preserved_count_fallback_universe(
        broad, reference, history,
        preserved_tickers=["CORE", "ADD"], target_count=2,
    )
    assert [row["ticker"] for row in selected] == ["ADD", "CORE"]
    assert stats["active_universe"] == 2
    assert stats["fallback_target_count"] == 2
    assert stats["fallback_replacements"] == 0
    assert all(row["current_session_provider"] == "Yahoo Finance" for row in selected)


def test_yahoo_fallback_fills_new_reference_ticker_missing_from_grouped_cache():
    history = grouped_history()
    broad = [
        {"ticker": "CORE", "price": 12, "market_cap": 300_000_000},
        {"ticker": "NEW", "price": 8, "market_cap": 80_000_000},
    ]
    reference = {
        ticker: {"ticker": ticker, "type": "CS", "primary_exchange": "XNAS"}
        for ticker in ("CORE", "NEW")
    }
    selected, stats = select_preserved_count_fallback_universe(
        broad, reference, history,
        preserved_tickers=["CORE", "MISSING"], target_count=2,
    )
    assert [row["ticker"] for row in selected] == ["CORE", "NEW"]
    assert stats["fallback_replacements"] == 1
    new = next(row for row in selected if row["ticker"] == "NEW")
    assert new["universe_route"] == "yahoo_fallback_fill"


def test_yahoo_ohlcv_becomes_grouped_fallback(tmp_path):
    path = tmp_path / "ohlcv.csv"
    path.write_text(
        "ticker,date,open,high,low,close,volume\n"
        "A,2026-09-24,9,11,8,10,100\n"
        "A,2026-09-25,10,12,9,11,200\n",
        encoding="utf-8",
    )
    grouped = grouped_history_from_yahoo_ohlcv(
        path, ["A"], target_session="2026-09-25",
    )
    assert grouped["2026-09-25"]["A"] == {
        "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.0, "v": 200.0,
    }


def test_massive_key_only_sent_to_trusted_https_host():
    import pytest
    from provider_inputs import ProviderError, _url_with_key
    ok = _url_with_key("https://api.massive.com/v3/reference/tickers?cursor=abc", "KEY", path_prefix="/v3/reference/tickers")
    assert "apiKey=KEY" in ok and "cursor=abc" in ok
    for bad in ("https://evil.example/v3/reference/tickers?cursor=a", "http://api.massive.com/v3/reference/tickers",
                "https://api.massive.com.evil.example/v3/reference/tickers", "https://u:p@api.massive.com/v3/reference/tickers",
                "https://api.massive.com:8443/v3/reference/tickers"):
        with pytest.raises(ProviderError):
            _url_with_key(bad, "KEY", path_prefix="/v3/reference/tickers")
    with pytest.raises(ProviderError):
        _url_with_key("https://api.massive.com/v2/other", "KEY", path_prefix="/v3/reference/tickers")


def _shortfall_case():
    history = grouped_history()
    broad = [{"ticker": "CORE", "price": 12, "market_cap": 300_000_000}]
    reference = {"CORE": {"ticker": "CORE", "type": "CS", "primary_exchange": "XNAS"}}
    return broad, reference, history


def test_yahoo_fallback_rejects_shortfall_by_default():
    broad, reference, history = _shortfall_case()
    with pytest.raises(ProviderError, match="cannot preserve universe count: 1/2"):
        select_preserved_count_fallback_universe(
            broad, reference, history, preserved_tickers=["CORE", "GONE"], target_count=2)


def test_yahoo_fallback_allows_small_provisional_shortfall_and_names_it():
    broad, reference, history = _shortfall_case()
    selected, stats = select_preserved_count_fallback_universe(
        broad, reference, history, preserved_tickers=["CORE", "GONE"], target_count=2,
        max_shortfall=1, required_tickers=["CORE"])
    assert [row["ticker"] for row in selected] == ["CORE"]
    assert stats["active_universe"] == 1 and stats["fallback_shortfall"] == 1
    assert stats["fallback_dropped_prior"] == ["GONE"] and stats["fallback_replacements"] == 0


def test_yahoo_fallback_never_drops_a_held_ticker():
    broad, reference, history = _shortfall_case()
    with pytest.raises(ProviderError, match="lost a held ticker: GONE"):
        select_preserved_count_fallback_universe(
            broad, reference, history, preserved_tickers=["CORE", "GONE"], target_count=2,
            max_shortfall=5, required_tickers=["GONE"])


def test_yahoo_fallback_keeps_held_ticker_outside_prior_universe():
    broad, reference, history = _shortfall_case()
    with pytest.raises(ProviderError, match="lost a held ticker: NOTPRIOR"):
        select_preserved_count_fallback_universe(
            broad, reference, history, preserved_tickers=["CORE"], target_count=1,
            max_shortfall=5, required_tickers=["NOTPRIOR"])
    selected, _ = select_preserved_count_fallback_universe(
        broad, reference, history, preserved_tickers=["GONE"], target_count=1,
        max_shortfall=1, required_tickers=["CORE"])
    assert [row["ticker"] for row in selected] == ["CORE"]


def test_fallback_shortfall_limit_and_held_names(tmp_path):
    import json as _json
    import refresh_mc57 as rm
    assert rm.fallback_max_shortfall(3968) == 119 and rm.fallback_max_shortfall(20) == 1
    # 2026-10-14: 3939/3968 stopped the publication under the old 0.5% limit.
    assert 3968 - 3939 <= rm.fallback_max_shortfall(3968)
    (tmp_path / "track-record").mkdir()
    ledger = tmp_path / "track-record" / "signals.json"
    ledger.write_text(_json.dumps(
        {"modeled_portfolio": {"positions": {"mrvl": {}, "AMD": {}}}, "portfolio": {"positions": {"CRWD": {}}}}))
    assert rm.held_tickers(tmp_path) == ["AMD", "MRVL"]  # the frozen earlier model is not held
    ledger.write_text(_json.dumps({"portfolio": {"positions": {"CRWD": {}}}}))
    assert rm.held_tickers(tmp_path) == ["CRWD"]
    assert rm.held_tickers(tmp_path / "missing") == []
    ledger.write_text("{truncated")
    with pytest.raises(ProviderError, match="unreadable"):
        rm.held_tickers(tmp_path)


def test_prior_count_keeps_provisional_target(tmp_path):
    import json as _json
    import refresh_mc57 as rm
    manifest = tmp_path / "latest-manifest.json"
    manifest.write_text(_json.dumps({"universe": {"active_universe": 3965},
                                     "provider_status": {"universe_target": 3968}}))
    assert rm.prior_universe_count(tmp_path, ["A"]) == 3968
    manifest.write_text(_json.dumps({"universe": {"active_universe": 3970},
                                     "provider_status": {"universe_target": None}}))
    assert rm.prior_universe_count(tmp_path, ["A"]) == 3970
    # A target the pool fell far below is stale: fall back to the published count.
    manifest.write_text(_json.dumps({"universe": {"active_universe": 3700},
                                     "provider_status": {"universe_target": 3968}}))
    assert rm.prior_universe_count(tmp_path, ["A"]) == 3700
