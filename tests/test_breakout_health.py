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
    assert bh.allocation(off, {"on": False})[0] == 50
    assert bh.allocation(on, {"on": True})[0] == 50
    assert bh.allocation(None, {"on": True})[0] == 50
    assert bh.allocation(off, None)[0] == 50


def test_daily_card_and_positions_line():
    health = {"session": "2026-10-01", "value": -0.028, "n": 40, "on": False, "since": "2026-08-20",
              "history": [("2026-09-%02d" % d, v, 40) for d, v in ((1, 0.01), (2, -0.01), (3, -0.028))]}
    page = '<section id="t-market"><div class="card"><div class="chd"><h2>リーダーの強さ<span>x</span></h2></div></div></section>'
    out = bh.apply_daily(page, health, {"on": True})
    assert out.index(bh.CARD_ID) < out.index("リーダーの強さ")
    assert "−2.8%" in out and "不調" in out and "余剰資金のTQQQルール枠：100%" in out
    assert bh.apply_daily(out, health, {"on": True}) == out
    assert bh.apply_daily("<html></html>", health, None) == "<html></html>"
    line = bh.positions_line(health, {"on": False})
    assert "不調" in line and "50%" in line
    assert bh.positions_line(None, None) == ""
