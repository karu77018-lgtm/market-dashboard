from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tqqq_rule as tq  # noqa: E402

DAYS = [d.date().isoformat() for d in pd.bdate_range("2025-01-01", periods=320)]


def market(hy_obs: int = 150, drop_last_hy: bool = False) -> dict:
    rng = np.random.default_rng(7)
    q = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(DAYS))))
    q[200:240] *= np.linspace(1, 0.78, 40)            # a drawdown to exercise the emergency modes
    q[240:] *= 0.78
    t = 30 * (q / q[0]) ** 3
    vix = 15 + 20 * (np.arange(len(DAYS)) % 90 == 0)
    rows = lambda px, vol=1e6: [{"date": d, "open": float(p) * 0.999, "high": float(p) * 1.01,
                                  "low": float(p) * 0.99, "close": float(p), "volume": vol} for d, p in zip(DAYS, px)]
    hy_days = DAYS[-hy_obs:-1] if drop_last_hy else DAYS[-hy_obs:]
    return {"series": {"QQQ": rows(q), "TQQQ": rows(t), "^VIX": rows(vix), "GC=F": rows(2000 + np.arange(len(DAYS)))},
            "fred": {"series": {"BAMLH0A0HYM2": {"history": [{"date": d, "value": 3.0 + 0.5 * (i > 100)}
                                                             for i, d in enumerate(hy_days)]},
                                "DGS3MO": {"history": [{"date": d, "value": 4.0} for d in DAYS]}}}}


def test_frame_keeps_price_history_and_requires_latest_hy():
    f = tq.frame_from_market(market())
    assert f is not None and len(f) == len(DAYS)          # FRED shorter than prices: price rows kept
    assert f["hy"].iloc[:100].isna().all() and f["hy"].iloc[-1] == 3.5
    lag = tq.frame_from_market(market(drop_last_hy=True))      # FRED one day behind: carried forward
    assert lag is not None and lag["hy"].iloc[-1] == 3.5
    m = market()
    m["fred"]["series"]["BAMLH0A0HYM2"]["history"] = []
    assert tq.frame_from_market(m) is None


def test_incremental_ledger_equals_one_shot():
    f = tq.frame_from_market(market())
    one = tq.update(tq.new_ledger(), f, DAYS[-1])
    step = tq.update(tq.new_ledger(), f, DAYS[250])
    for d in DAYS[251:]:
        step = tq.update(step, f, d)
    assert json.dumps(step, sort_keys=True) == json.dumps(one, sort_keys=True)
    assert min(one["days"]) == DAYS[199] and one["last_day"] == DAYS[-1]
    assert tq.update(copy.deepcopy(one), f, DAYS[-1]) == one          # frozen once written
    assert all(r["target"] in (0.0, 0.25, 0.5, 0.75, 1.0) for r in one["days"].values())


def test_fund_bars_trade_next_open_and_mark_gold_and_bills():
    led = tq.new_ledger()
    led["days"] = {
        "2026-01-02": {"target": 1.0, "gold": 0.0, "tqqq": 100.0, "tqqq_open": 100.0, "gold_px": 10.0, "rf": 0.0},
        "2026-01-05": {"target": 0.5, "gold": 0.5, "tqqq": 110.0, "tqqq_open": 105.0, "gold_px": 10.0, "rf": 0.0},
        "2026-01-06": {"target": 0.5, "gold": 0.5, "tqqq": 110.0, "tqqq_open": 110.0, "gold_px": 12.0, "rf": 0.0},
    }
    b = tq.fund_bars(led)
    assert b["2026-01-02"] == {"open": 1.0, "close": 1.0}
    assert abs(b["2026-01-05"]["open"] - 1.05) < 1e-12 and abs(b["2026-01-05"]["close"] - 1.10) < 1e-12
    # the 01-05 close decided 50% TQQQ / 50% gold: the gap is carried at 100%, the day at 50% + gold +20% x 50%
    assert abs(b["2026-01-06"]["open"] - 1.10) < 1e-12
    assert abs(b["2026-01-06"]["close"] - 1.10 * 1.10) < 1e-12


def test_top_card_replaces_itself_and_shows_the_idle_money_split(tmp_path: Path):
    led = tq.new_ledger()
    led["days"] = {"2026-10-07": {"target": 0.75, "gold": 0.25, "trend": True, "hy": 3.0}}
    page = '<html><head></head><body><div class="wrap"><nav>n</nav></div></body></html>'
    out = tq.apply_top(page, led, 50)
    assert out.index(tq.CARD_ID) < out.index("<nav") and out.count(f'id="{tq.CARD_ID}"') == 1
    assert "TQQQ <b>75%</b>" in out and "余剰資金の TQQQ <b>38%</b>" in out and "平時" in out
    assert tq.apply_top(out, led, 50) == out
    led["days"]["2026-10-08"] = {"target": 0.0, "gold": 1.0, "alarm": True}
    out2 = tq.apply_top(out, led, 100)
    assert out2.count(f'id="{tq.CARD_ID}"') == 1 and "過熱警報" in out2 and out2.count('id="tqqq-rule-style"') == 1
    assert "判定不可" in tq.apply_top(page, None, 50)
