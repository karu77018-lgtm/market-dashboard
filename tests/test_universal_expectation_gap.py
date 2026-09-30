import math

from scripts.expectation_gap.run_universal_expectation_gap import (
    compute_market_row,
    percentile_ranks,
    research_priority,
    select_candidates,
)


def synthetic_series(n=220, start=10.0, daily=0.002):
    rows = []
    price = start
    for i in range(n):
        prev = price
        price *= 1 + daily
        rows.append([
            f"2026-01-{(i % 28) + 1:02d}",
            prev,
            max(prev, price) * 1.002,
            min(prev, price) * 0.998,
            price,
            2_000_000 + i * 1000,
        ])
    return rows


def test_percentile_ranks_ties():
    out = percentile_ranks({"A": 1.0, "B": 2.0, "C": 2.0, "D": 4.0})
    assert out["A"] == 0.0
    assert out["D"] == 100.0
    assert math.isclose(out["B"], out["C"])


def test_market_row_has_required_fields():
    row = compute_market_row("TEST", synthetic_series())
    assert row is not None
    assert row["ddv20"] >= 10_000_000
    assert row["run20_z"] > 0
    assert row["high63_proximity_pct"] <= 100


def test_candidate_selection_includes_controls():
    rows = []
    for i in range(30):
        rows.append({
            "ticker": f"T{i:02d}",
            "trend_strength": 90 - i,
            "expectation_load": 40 + i * 2,
            "p_ret63": 90,
            "p_ret20": 90 - i * 2,
        })
    got = select_candidates(rows, 12)
    assert len(got) <= 12
    labels = {label for r in got for label in r["seed_labels"]}
    assert "underappreciated_strength_seed" in labels
    assert "expectations_heavy_control" in labels


def test_research_priority_is_transparent_and_bounded():
    row = {
        "expectation_load": 30,
        "trend_strength": 80,
        "financials": {"fundamental_delta_score": 80},
        "jev": {"semantic_gap_score": 75},
        "insider": {"informative_positive": True},
        "short_interest": {"state": "building"},
    }
    score = research_priority(row)
    assert score is not None
    assert 0 <= score <= 100
    assert score > 70
