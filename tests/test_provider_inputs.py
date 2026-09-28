from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from provider_inputs import (  # noqa: E402
    _normalize_grouped_results,
    compute_massive_market_structure,
    grouped_history_from_yahoo_ohlcv,
    select_preserved_count_fallback_universe,
    select_expanded_universe,
)


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
