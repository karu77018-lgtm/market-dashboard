from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import trend_leaders as tl  # noqa: E402
from rotation_split import apply as split  # noqa: E402


def frame(n: int = 400) -> pd.DataFrame:
    """UP* trend up (strength 1..6), DOWN falls, CHEAP rises but trades under $10."""
    dates = pd.bdate_range("2024-01-01", periods=n)
    rows = []
    paths = {f"UP{k}": 50 * np.exp(np.linspace(0, 0.15 * k, n)) for k in range(1, 7)}
    paths["DOWN"] = 100 * np.exp(np.linspace(0, -0.6, n))
    paths["FLAT"] = 60 + np.sin(np.arange(n) / 9)
    paths["CHEAP"] = 2 * np.exp(np.linspace(0, 1.0, n))
    for t, p in paths.items():
        for d, c in zip(dates, p):
            rows.append((t, d, c, c * 1.01, c * 0.99, c, 2_000_000))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


DET = {f"UP{k}": {"sec": "1. エネルギー（化石燃料）"} for k in range(1, 7)}
DET.update({"DOWN": {"sec": "2. 金融・銀行・保険"}, "FLAT": {"sec": "2. 金融・銀行・保険"}})


def result(tv=None):
    f = frame()
    return tl.compute(f, DET, str(f["date"].max().date()), tv)


def test_template_rs_gate_and_liquidity():
    res = result()
    m = res["today"]["mkt"]
    assert m["n"] == 8                      # CHEAP (< $10) is not in the liquid market
    passed = set(m["ok"][m["ok"]].index)
    # UP1/UP2 rise less than +30% from the 52-week low (condition 6); of the rest only
    # the RS percentile >= 70 (UP4-UP6 of 8 names) pass the 8th condition
    assert passed == {"UP4", "UP5", "UP6"}
    assert [r["t"] for r in res["leaders"]["mkt"]] == ["UP6", "UP5", "UP4"]
    assert res["leaders"]["mkt"][0]["kind"] == "新高値型"


def test_sector_rate_needs_enough_members(monkeypatch):
    monkeypatch.setattr(tl, "MIN_SECTOR", 2)
    rows = {r["sector"]: r for r in result()["sectors"]}
    assert rows["エネルギー（化石燃料）"]["pass"] == 3 and rows["エネルギー（化石燃料）"]["n"] == 6
    assert rows["金融・銀行・保険"]["rate"] == 0
    assert list(rows)[0] == "エネルギー（化石燃料）"          # sorted by rate, not by count


def test_sp500_group_ranks_inside_members_and_flags_earnings():
    f = frame()
    day = f["date"].max()
    soon = int(pd.Timestamp(day + pd.Timedelta(days=5), tz="UTC").timestamp())
    tv = {"sp500": {"UP3", "UP4", "DOWN"}, "info": {"UP4": {"earn": soon, "ath": 10_000.0}}}
    res = tl.compute(f, DET, str(day.date()), tv)
    sp = res["today"]["sp"]
    assert sp["n"] == 3 and set(sp["ok"][sp["ok"]].index) == {"UP4"}   # ranked inside the 3 members
    lead = res["leaders"]["sp"][0]
    assert lead["t"] == "UP4" and lead["earn_days"] == 5 and lead["kind"] == "戻り型"  # far below ATH
    assert all(r["t"] not in tv["sp500"] for r in res["leaders"]["mkt"])
    html = tl.card_html(res)
    assert "決算5日" in html and 'data-tkone="UP4"' in html


PAGE = (
    "<html><head></head><body><nav><a class='tabx' href='#t-rotation'>Rotation</a></nav>"
    '<section id="t-rotation"><div class="card"><h2>何が指数を支えている？</h2></div>'
    '<div class="card"><h2>主導セクター・業種</h2></div>'
    '<div class="card" id="mc57-theme-gate"><h2>テーマ判定（3条件）</h2></div>'
    '<div class="card"><h2>テーマETFの温度計</h2></div></section><footer class="disc">f</footer></body></html>'
)


def test_refresh_path_card_moves_to_themes_under_its_header():
    page = split(tl.apply(PAGE, result()))
    themes = page[page.find('<section id="t-themes"'):]
    assert tl._find_div(themes, tl.CARD_ID) > 0
    heads = re.findall(r'<div class="msec-l">([^<]*)', themes)
    assert heads[:2] == ["① 今のテーマ", "② 客観スクリーン"] and heads[2].startswith("③")


def test_display_path_inserts_header_renumbers_and_replaces_in_place():
    page = split(PAGE)                                  # already split, no card yet
    once = tl.apply(page, result())
    themes = once[once.find('<section id="t-themes"'):]
    heads = re.findall(r'<div class="msec-l">([^<]*)', themes)
    assert heads[:3] == ["① 今のテーマ", "② 客観スクリーン", "③ 自ユニバースで主導しているのは誰か"]
    assert tl.apply(once, result()) == once            # replaced, not duplicated
    assert once.count(f'id="{tl.CARD_ID}"') == 1 and once.count("mc57-trend-leaders-style") == 1
    assert tl.apply(page, None) == page


def test_short_history_returns_none_and_ledger_records(tmp_path):
    assert tl.compute(frame(200), DET, "2024-10-01") is None
    res = result()
    led = tl.record(tl.load_ledger(tmp_path), res)
    tl.save_ledger(led, tmp_path)
    day = tl.load_ledger(tmp_path)["days"][res["session"]]
    assert day["mkt"] == [3, 8] and day["top"]["mkt"] == ["UP6", "UP5", "UP4"]
