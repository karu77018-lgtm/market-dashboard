from scripts.event_risk.build_earnings_expectation_core import _pct_rank_map, _reaction_stats


def test_percentile_map_orders_values():
    rows = [{"x": -1.0}, {"x": 2.0}, {"x": 1.0}]
    m = _pct_rank_map(rows, "x")
    assert m[0] == 0.0
    assert m[2] == 50.0
    assert m[1] == 100.0


def test_reaction_stats_keeps_negative_probability():
    rows = [
        {"gap_pct": -2.0, "ret1_pct": -1.0, "ret5_pct": -5.0, "ret20_pct": -7.0},
        {"gap_pct": 2.0, "ret1_pct": 1.0, "ret5_pct": 5.0, "ret20_pct": 7.0},
    ]
    s = _reaction_stats(rows)
    assert s["ret5_pct"]["median"] == 0.0
    assert s["ret5_pct"]["p_negative"] == 0.5
