import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config  # noqa: E402
from sim import hm, simulate_day  # noqa: E402
from watchlist import build_panel, daily_nets  # noqa: E402

CFG = Config().with_(signal__baseline_floor_per_min=1_000, exe__slippage=0.0)


def bars(rows):
    """rows: {"HH:MM": (o, h, l, c, v)}; vw = close."""
    out = [{"m": hm(k), "o": o, "h": h, "l": l, "c": c, "v": v, "vw": c} for k, (o, h, l, c, v) in rows.items()]
    return pd.DataFrame(out)


def quiet(start="09:30", end="09:44", px=10.0, vol=10_000):
    rows, m = {}, hm(start)
    while m <= hm(end):
        rows[f"{m // 60:02d}:{m % 60:02d}"] = (px, px, px, px, vol)
        m += 1
    return rows


def run(rows, **kw):
    return simulate_day("2025-01-02", [("AAA", "2日目")], {"AAA": bars(rows)}, kw.pop("cfg", CFG), **kw)


def test_signal_fill_and_three_take_profits():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)        # +4%, $1.04M vs $100K base
    rows["09:46"] = (10.45, 10.5, 10.45, 10.5, 50_000)       # limit 10.504 -> fill at max(open, limit)
    rows["09:50"] = (10.6, 12.2, 10.6, 12.1, 50_000)         # through +5/+10/+15%
    t, = run(rows)
    assert t["entry_time"] == "09:46"
    assert t["entry_px"] == pytest.approx(10.504)
    assert t["shares"] == 96                                 # 1000 // 10.4
    assert [f[3] for f in t["fills"]] == ["tp1", "tp2", "tp3"]
    assert [f[1] for f in t["fills"]] == [16, 64, 16]
    assert t["pnl"] > 0


def test_opening_ten_minutes_are_skipped_unless_from_open():
    rows = quiet("09:20", "09:34")
    rows["09:35"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:36"] = (10.4, 10.4, 10.3, 10.4, 50_000)
    assert run(rows) == []
    assert len(run(rows, from_open=True)) == 1


def test_stop_beats_take_profit_in_same_bar():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    rows["09:47"] = (10.4, 11.5, 9.0, 10.0, 50_000)          # hits +10% and -8%
    t, = run(rows)
    assert t["exit_reason"] == "stop"
    assert t["pnl_pct"] == pytest.approx(-0.08)


def test_missing_next_bar_means_no_fill():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:47"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    assert run(rows) == []


def test_gap_below_abandon_level_is_skipped():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.0, 10.0, 9.9, 10.0, 50_000)          # opens -3.8% from signal
    assert run(rows) == []


def test_time_exit_at_1550():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    rows["15:50"] = (10.3, 10.3, 10.3, 10.3, 1_000)
    t, = run(rows, cfg=CFG.with_(exe__max_hold_min=10_000))
    assert t["exit_reason"] == "time" and t["exit_time"] == "15:50"


def test_ladder_raises_stop_after_peak():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    rows["09:47"] = (10.4, 11.3, 10.4, 11.2, 50_000)         # peak +7.6% vs basis -> stop +2% (tp1 done too)
    rows["09:48"] = (11.0, 11.0, 10.5, 10.5, 50_000)
    t, = run(rows)
    assert t["fills"][-1][3] == "stop"
    assert t["fills"][-1][2] == pytest.approx(10.504 * 1.02)   # basis = limit 10.504


def test_slippage_hits_both_sides():
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    rows["09:47"] = (10.4, 10.4, 9.0, 9.0, 50_000)
    t, = run(rows, cfg=CFG.with_(exe__slippage=0.01))
    assert t["pnl_pct"] == pytest.approx(0.92 * 0.99 / 1.01 - 1)


def test_max_five_positions():
    tickers = [f"T{i}" for i in range(7)]
    rows = quiet()
    rows["09:45"] = (10.0, 10.4, 10.0, 10.4, 100_000)
    rows["09:46"] = (10.4, 10.4, 10.4, 10.4, 50_000)
    data = {t: bars(rows) for t in tickers}
    trades = simulate_day("2025-01-02", [(t, "2日目") for t in tickers], data, CFG)
    assert len(trades) == 5


def _panel(rows):
    df = pd.DataFrame(rows, columns=["ticker", "date", "o", "h", "l", "c", "v"])
    df["vw"] = df["c"]
    return build_panel(df, set(df["ticker"]), pd.DataFrame(columns=["ticker", "date", "split_from", "split_to"]))


def test_daily_nets_d3s_day2_and_reignite():
    days = [f"2025-01-{d:02d}" for d in range(1, 29)]
    rows = []
    for i, d in enumerate(days[:-1]):
        rows.append(("FLAT", d, 5, 5, 5, 5, 1_000_000))
        # D3S: day1 = days[-3] +60% on 12M shares, day2 = days[-2] closes lower
        c = {len(days) - 3: 8.0, len(days) - 2: 7.0}.get(i, 5.0)
        rows.append(("DDD", d, c, c, c, c, 12_000_000 if i == len(days) - 3 else 1_000_000))
        # 再点火: spike high +30% on 5x volume at days[-4], then calm, holds gains
        if i < len(days) - 4:
            rows.append(("RRR", d, 4, 4, 4, 4, 100_000))
        elif i == len(days) - 4:
            rows.append(("RRR", d, 4, 5.2, 4, 4.8, 600_000))
        else:
            rows.append(("RRR", d, 4.8, 4.9, 4.7, 4.8, 200_000))
    panel = _panel(rows)
    got = daily_nets(panel, len(days) - 1, Config().watch)
    assert ("DDD", "D3S") in got
    assert ("RRR", "再点火") in got
    assert all(t != "FLAT" for t, _ in got)


def test_reverse_split_is_not_a_gain():
    rows = [("SPL", "2025-01-02", 1, 1, 1, 1, 1e6), ("SPL", "2025-01-03", 10, 10, 10, 10, 1e5),
            ("SPL", "2025-01-06", 10, 10, 10, 10, 1e5)]
    df = pd.DataFrame(rows, columns=["ticker", "date", "o", "h", "l", "c", "v"]).assign(vw=lambda x: x.c)
    splits = pd.DataFrame([{"ticker": "SPL", "date": "2025-01-03", "split_from": 10, "split_to": 1}])
    panel = build_panel(df, {"SPL"}, splits)
    assert panel.loc[panel.date == "2025-01-03", "chg"].iat[0] == pytest.approx(0.0)
