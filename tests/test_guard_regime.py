from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import swing_screener as ss  # noqa: E402


def _write(tmp_path, last_qqq, vix, vix3m):
    days = pd.bdate_range("2025-09-01", periods=260)
    q = [{"date": d.strftime("%Y-%m-%d"), "close": 100.0 + i * 0.1} for i, d in enumerate(days)]
    q[-1]["close"] = last_qqq
    d = days[-1].strftime("%Y-%m-%d")
    m = {"series": {"QQQ": q, "^VIX": [{"date": d, "close": vix}], "^VIX3M": [{"date": d, "close": vix3m}]}}
    p = tmp_path / "market_inputs.json"
    p.write_text(json.dumps(m))
    return p, d


def test_guard_needs_backwardation_and_qqq_under_50dma(tmp_path, monkeypatch):
    import tqqq_rule
    monkeypatch.setattr(tqqq_rule, "full_bottom_active", lambda root=None, session=None: None)
    p, d = _write(tmp_path, 120.0, 20.0, 20.5)          # ts 0.976, QQQ under its 50-day line
    r = ss.regime_from_market(p, d)
    assert r["guard"] and abs(r["ts"] - 20.0 / 20.5) < 1e-12
    p, d = _write(tmp_path, 140.0, 20.0, 20.5)          # above the 50-day line
    assert not ss.regime_from_market(p, d)["guard"]
    p, d = _write(tmp_path, 120.0, 18.0, 20.5)          # ts 0.88
    assert not ss.regime_from_market(p, d)["guard"]
    monkeypatch.setattr(tqqq_rule, "full_bottom_active", lambda root=None, session=None: {"day": d, "left": 5})
    p, d = _write(tmp_path, 120.0, 20.0, 20.5)
    r = ss.regime_from_market(p, d)
    assert not r["guard"] and r["guard_raw"] and r["guard_full"]


def test_guard_is_retired_from_2026_10_29(tmp_path, monkeypatch):
    import tqqq_rule
    from swing_allocation import GUARD_OFF_FROM
    monkeypatch.setattr(tqqq_rule, "full_bottom_active", lambda root=None, session=None: None)
    days = pd.bdate_range(end=GUARD_OFF_FROM, periods=260)
    q = [{"date": d.strftime("%Y-%m-%d"), "close": 100.0 + i * 0.1} for i, d in enumerate(days)]
    q[-1]["close"] = 120.0                              # under the 50-day line, VIX/VIX3M 0.976: the old guard
    d = days[-1].strftime("%Y-%m-%d")
    p = tmp_path / "market_inputs.json"
    p.write_text(json.dumps({"series": {"QQQ": q, "^VIX": [{"date": d, "close": 20.0}], "^VIX3M": [{"date": d, "close": 20.5}]}}))
    r = ss.regime_from_market(p, d)
    assert not r["guard"] and not r["guard_raw"] and "守りモード" not in ss._guard_bar(r)
