from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from swing_screener import CARD_ID, apply, card_html, evaluate  # noqa: E402


def _frame(n_days: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rng = np.random.default_rng(1)
    rows = []
    # One liquid leader: steady uptrend, quiet last 10 sessions, heavy dollar volume.
    path = np.r_[np.linspace(20, 60, n_days - 10), np.full(10, 60.0)]
    for i, (d, p) in enumerate(zip(dates, path)):
        width = 0.04 if i < n_days - 10 else 0.01
        vol = 3e6 if i < n_days - 5 else 1.5e6
        rows.append(("LEAD", d, p, p * (1 + width / 2), p * (1 - width / 2), p, vol))
    # Background: 40 drifting liquid stocks with lower dollar volume.
    for k in range(40):
        bg = np.cumprod(1 + rng.normal(0, 0.01, n_days)) * 30
        for d, p in zip(dates, bg):
            rows.append((f"BG{k}", d, p, p * 1.01, p * 0.99, p, 1.0e6))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def test_quiet_liquid_leader_is_a_core_candidate():
    result = evaluate(_frame())
    tickers = [r["ticker"] for r in result["core"]]
    assert tickers == ["LEAD"]
    lead = result["core"][0]
    assert abs(lead["stop"] - lead["close"] * 0.92) < 1e-9
    assert abs(lead["add"] - lead["close"] * 1.10) < 1e-9


def test_card_is_inserted_into_positions_tab_once():
    frame = _frame()
    page = '<html><head></head><body><section id="t-alloc"><div id="taExpo"></div></section></body></html>'
    out = apply(page, frame)
    assert out.count(f'id="{CARD_ID}"') == 1
    assert out.index(CARD_ID) < out.index("taExpo")
    assert apply(out, frame) == out  # idempotent
    assert apply("<html><head></head><body></body></html>", frame).count(CARD_ID) == 0


def test_short_history_and_empty_result_render_gracefully():
    short = _frame(120)
    result = evaluate(short)
    assert result["core"] == [] and result["reason"] == "history_short"
    html = card_html({"session": "2026-01-02", "core": [], "watch": [], "ep": [], "universe": 0})
    assert "本日の買い候補なし" in html


def test_late_entry_listed_when_today_no_longer_signals():
    frame = _frame()
    last_day = frame["date"].max()
    lead = (frame["ticker"] == "LEAD") & (frame["date"] == last_day)
    # Today: +1% close and a volume spike, so the volume-dry-up check fails today
    # while yesterday's signal is still valid and close stays within +3%.
    frame.loc[lead, ["open", "high", "low", "close"]] *= 1.01
    frame.loc[lead, "volume"] = 2.0e7
    result = evaluate(frame)
    assert [r["ticker"] for r in result["core"]] == []
    late = result["late"]
    assert [r["ticker"] for r in late] == ["LEAD"] and late[0]["lag"] == 1
    assert 0 < late[0]["from_signal"] <= 0.03
    assert "LEAD" not in [r["ticker"] for r in result["watch"]]
