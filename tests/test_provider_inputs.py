from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from provider_inputs import (  # noqa: E402
    _normalize_grouped_results,
    compute_massive_market_structure,
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


def test_universe_keeps_legacy_and_adds_only_liquid_expansion():
    history = grouped_history()
    target = "2026-09-20"
    broad = [
        {"ticker": "CORE", "price": 12, "market_cap": 300_000_000},
        {"ticker": "ADD", "price": 10, "market_cap": 100_000_000},
        {"ticker": "ILLQ", "price": 10, "market_cap": 100_000_000},
    ]
    reference = {
        ticker: {"ticker": ticker, "type": "CS", "primary_exchange": "XNAS"}
        for ticker in ("CORE", "ADD", "ILLQ")
    }
    selected, stats = select_expanded_universe(
        broad, reference, history, target_session=target,
    )
    assert [row["ticker"] for row in selected] == ["ADD", "CORE"]
    assert stats["legacy_universe"] == 1
    assert stats["massive_liquid_expansion"] == 1
    assert stats["massive_current_coverage"] == 1.0


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
