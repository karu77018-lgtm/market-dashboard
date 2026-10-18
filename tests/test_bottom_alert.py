from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bottom_alert as ba  # noqa: E402


def _market(vix_highs, qqq_closes):
    days = pd.bdate_range("2025-01-02", periods=len(qqq_closes))
    q = [{"date": d.strftime("%Y-%m-%d"), "open": c, "high": c, "low": c, "close": c} for d, c in zip(days, qqq_closes)]
    v = [{"date": d.strftime("%Y-%m-%d"), "open": h, "high": h, "low": h, "close": h} for d, h in zip(days, vix_highs)]
    return {"series": {"QQQ": q, "^VIX": v}}, days


def _crash(peak_vix):
    n = 300
    qc = np.full(n, 100.0)
    qc[260:280] = np.linspace(100, 75, 20)          # -25% fall
    qc[280:] = 76.0
    vh = np.full(n, 15.0)
    vh[265:280] = np.linspace(20, peak_vix, 15)      # VIX spike, then fall
    vh[280:] = np.linspace(peak_vix * 0.8, 18, n - 280)
    return _market(list(vh), list(qc))


def test_big_and_mid_fire_once_after_a_crash_and_vix_rollover():
    m, days = _crash(60.0)
    f = ba.compute(m)
    assert f.big.sum() == 1 and f.mid.sum() == 1
    d = f.index[f.big][0]
    assert d > days[279] and f.loc[d, "cross"] and f.loc[d, "d52"] <= -0.10
    assert abs(f.l2.iloc[-1] - 47.65) < 0.05            # seed +2σ


def test_no_big_without_plus_two_sigma_and_ledger_freezes_days(tmp_path: Path):
    m, days = _crash(36.0)                              # above +1σ, below +2σ
    f = ba.compute(m)
    assert f.big.sum() == 0 and f.mid.sum() == 1
    led = ba.update(ba.new_ledger(), f, days[-1].strftime("%Y-%m-%d"), keep_from=days[250].strftime("%Y-%m-%d"))
    assert led["last_day"] == days[-1].strftime("%Y-%m-%d") and len(led["days"]) == 50
    again = ba.update(led, f, days[-1].strftime("%Y-%m-%d"))
    assert again is led and len(again["days"]) == 50


def test_card_states_and_placement():
    led = ba.new_ledger()
    base = {"d52": -0.03, "vix_high": 16.0, "vix_rel10": 1.0, "vmax10": 16.0, "l1": 33.2, "l2": 47.6, "mid": False, "big": False}
    led["days"] = {"2026-10-15": dict(base), "2026-10-16": dict(base)}
    assert "なし" in ba.card_html(led)
    led["days"]["2026-10-16"]["d52"] = -0.09
    assert "監視中" in ba.card_html(led)
    led["days"]["2026-10-15"]["mid"] = True
    h = ba.card_html(led)
    assert "急落の底候補（10/15）" in h and "−9.0%" in h
    led["days"]["2026-10-16"]["big"] = True
    assert "大型急落の底確認（10/16）" in ba.card_html(led)
    page = '<html><head></head><body><div id="tqqq-rule-card"><div>x</div></div><nav></nav></body></html>'
    out = ba.apply(page, led)
    assert out.index('id="tqqq-rule-card"') < out.index(f'id="{ba.CARD_ID}"') < out.index("<nav")
    assert ba.apply(out, led) == out and out.count('id="bottom-alert-style"') == 1
    assert ba.card_html(None) == "" and ba.apply(page, None) == page
