from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import breakout_health as bh  # noqa: E402
import swing_screener as ss  # noqa: E402


def _walk(n=400, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n))), index=idx)
    return c * 1.01, c * 0.99, c


def test_weekly_sar_lookup_matches_truncated_state():
    h, l, c = _walk()
    cache: dict = {}
    for k in range(80, len(c), 7):
        day = c.index[k]
        up, _ = ss.weekly_sar_state(h.iloc[:k + 1], l.iloc[:k + 1], c.iloc[:k + 1])
        assert bh._sar_up_at(cache, "X", {"X": h}, {"X": l}, {"X": c}, day) == bool(up), day


def test_allocation_rule():
    on, off = {"on": True, "value": 0.05}, {"on": False, "value": -0.02}
    assert bh.allocation(off, {"on": True})[0] == 100
    assert bh.allocation(off, {"on": False})[0] == 60
    assert bh.allocation(on, {"on": True})[0] == 60
    assert bh.allocation(None, {"on": True})[0] == 60
    assert bh.allocation(off, None)[0] == 60


def test_daily_card_and_positions_line():
    health = {"session": "2026-10-01", "value": -0.028, "n": 40, "on": False, "since": "2026-08-20",
              "history": [("2026-09-%02d" % d, v, 40) for d, v in ((1, 0.01), (2, -0.01), (3, -0.028))]}
    page = '<section id="t-market"><div class="card"><div class="chd"><h2>リーダーの強さ<span>x</span></h2></div></div></section>'
    out = bh.apply_daily(page, health, {"on": True})
    assert out.index(bh.CARD_ID) < out.index("リーダーの強さ")
    assert "−2.8%" in out and "不調" in out and '今日の余剰資金：<b class="big">100%</b> をTQQQルール枠へ' in out
    assert "勢い株が報われていない" in out and "0%以上に戻ると（今はあと2.8pt）" in out and "読み方と根拠" in out
    assert bh.apply_daily(out, health, {"on": True}) == out
    assert bh.apply_daily("<html></html>", health, None) == "<html></html>"
    line = bh.positions_line(health, {"on": False})
    assert "不調" in line and "50%" in line          # session 2026-10-01 is before the v6 cutover
    assert bh.positions_line(None, None) == ""


def test_allocation_keeps_v5_share_for_publications_before_the_cutover():
    on = {"on": True, "value": 0.05}
    assert bh.allocation(on, {"on": True, "date": "2026-10-12"})[0] == 50
    assert bh.allocation(on, {"on": True, "date": "2026-10-13"})[0] == 60
    assert bh.allocation(on, {"on": True}, "2026-10-12")[0] == 50
    assert bh.allocation({"on": False, "value": -0.01}, {"on": True, "date": "2026-10-12"})[0] == 100


def test_card_wording_for_unavailable_health_and_regime_off():
    na = {"session": "2026-10-14", "value": None, "n": 2, "on": None, "since": None, "history": []}
    card = bh.daily_card(na, {"on": True, "date": "2026-10-14"})
    assert "0営業日" not in card and "判定できない" in card
    bad = {"session": "2026-10-14", "value": -0.01, "n": 20, "on": False, "since": "2026-10-01", "history": []}
    line = bh.positions_line(bad, {"on": False, "date": "2026-10-14"})
    assert "0%をまたぐと切り替え" not in line and "比率は同じ" in line


def test_unknown_regime_is_not_shown_as_below_the_line():
    good = {"session": "2026-10-14", "value": 0.02, "n": 20, "on": True, "since": "2026-10-01", "history": []}
    line = bh.positions_line(good, None)
    assert "地合いが取れない" in line and "200日線より下" not in line
    card = bh.daily_card(good, None)
    assert "地合い（QQQの200日線）が取れない間は" in card and "回復したら" not in card


def test_streak_is_a_lower_bound_at_the_window_edge_and_no_legend_without_chart():
    hist = [("2025-10-%02d" % d, 0.01, 20) for d in range(1, 29)]
    long = {"session": hist[-1][0], "value": 0.01, "n": 20, "on": True, "since": hist[0][0], "history": hist}
    card = bh.daily_card(long, {"on": True, "date": hist[-1][0]})
    assert "28営業日以上" in card and "1年以上前から" in card and "1年分" in card
    empty = {**long, "history": [], "since": "2025-10-10"}
    card = bh.daily_card(empty, {"on": True, "date": hist[-1][0]})
    assert "1年分" not in card and "推移はまだ描けない" in card
