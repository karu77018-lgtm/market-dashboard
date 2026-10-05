from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ipo_base as ib  # noqa: E402
import setups_curate as sc  # noqa: E402

DAYS = pd.bdate_range("2026-01-02", periods=120)


def ipo_frame(t="NEWX", breakout=True):
    """Listed on day 0, high 50 on day 10, base down to 40, breakout on the last day."""
    rows = []
    for i, d in enumerate(DAYS):
        if i <= 10:
            c = 30 + i * 2
        elif i < len(DAYS) - 1:
            c = 42 + 3 * np.sin(i / 4)
        else:
            c = 52 if breakout else 47
        v = 3e6 if i == len(DAYS) - 1 and breakout else 1e6
        rows.append((t, d, c * 0.99, max(c, 50 if i == 10 else c) * 1.005, c * 0.98, c, v))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def test_breakout_and_waiting_and_age_limits():
    f = ipo_frame()
    session = DAYS[-1].strftime("%Y-%m-%d")
    res = ib.scan(f, {"NEWX": DAYS[0].strftime("%Y-%m-%d")}, session)
    assert [r["t"] for r in res["breakouts"]] == ["NEWX"] and res["breakouts"][0]["back"] == 0
    r = res["breakouts"][0]
    assert r["base"] >= ib.MIN_BASE and 0.10 <= r["depth"] <= 0.50 and r["volx"] >= 1.4
    w = ib.scan(ipo_frame(breakout=False), {"NEWX": DAYS[0].strftime("%Y-%m-%d")}, session)
    assert w["breakouts"] == [] and [x["t"] for x in w["waiting"]] == ["NEWX"]
    old = ib.scan(f, {"NEWX": "2020-01-02"}, session)                  # listed years ago: not an IPO base
    assert old == {"breakouts": [], "waiting": []}
    thin = f.assign(volume=f.volume / 100)
    assert ib.scan(thin, {"NEWX": DAYS[0].strftime("%Y-%m-%d")}, session)["breakouts"] == []


def test_listings_are_extended_with_new_first_bars(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / ib.LISTINGS).write_text(json.dumps({"schema": "listing-dates.1", "dates": {"OLD": "2010-01-04"}}))
    seasoned = ipo_frame("OLD").assign(date=lambda d: d.date - pd.Timedelta(days=200))
    frame = pd.concat([seasoned, ipo_frame("NEWX")])
    assert ib.update_listings(frame, tmp_path) == 1
    dates = ib.load_listings(tmp_path)
    assert dates["NEWX"] == DAYS[0].strftime("%Y-%m-%d") and dates["OLD"] == "2010-01-04"
    assert ib.update_listings(frame, tmp_path) == 0


def test_signals_are_recorded_once_and_followed():
    f = ipo_frame()
    session = DAYS[-1].strftime("%Y-%m-%d")
    res = ib.scan(f, {"NEWX": DAYS[0].strftime("%Y-%m-%d")}, session)
    led = ib.record_and_advance({"schema": ib.SCHEMA, "signals": {}}, res, f, session, {})
    led = ib.record_and_advance(led, res, f, session, {})
    assert list(led["signals"]) == [f"{session}:NEWX"] and led["signals"][f"{session}:NEWX"]["status"] == "約定待ち"
    assert ib.ledger_summary(led)["signals"] == 1


def test_card_goes_after_pre_breakout_and_numbers_follow():
    page = ('<html><head></head><body><section id="t-today">'
            '<div class="msec"><div class="msec-l">① 発火前</div></div><div class="card">a</div>'
            '<div class="msec"><div class="msec-l">② 支えへの接触</div></div><div class="card">b</div>'
            '</section></body></html>')
    res = {"breakouts": [], "waiting": []}
    out = sc.renumber(ib.apply(page, res, {"on": True}, None))
    assert out.index("IPOベース") < out.index("支えへの接触")
    assert "② IPOベース" in out and "③ 支えへの接触" in out and "該当なし" in out
    again = sc.renumber(ib.apply(out, res, {"on": True}, None))
    assert again == out and again.count(f'id="{ib.CARD_ID}"') == 1
