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


def test_frame_requires_current_gold():
    m = market()
    del m["series"]["GC=F"]
    assert tq.frame_from_market(m) is None                 # no silent switch from gold to T-bills
    m = market()
    m["series"]["GC=F"] = m["series"]["GC=F"][:-6]          # gold more than 4 days stale
    assert tq.frame_from_market(m) is None
    m = market()
    m["series"]["GC=F"] = m["series"]["GC=F"][-100:]        # too short for the 126-day test
    assert tq.frame_from_market(m) is None
    assert tq.frame_from_market(market())["gopen"].notna().all()


def test_incremental_ledger_equals_one_shot():
    f = tq.frame_from_market(market())
    one = tq.update(tq.new_ledger(), f, DAYS[-1])
    step = tq.update(tq.new_ledger(), f, DAYS[250])
    for d in DAYS[251:]:
        step = tq.update(step, f, d)
    assert json.dumps(step, sort_keys=True) == json.dumps(one, sort_keys=True)
    assert min(one["days"]) == DAYS[tq.FIRST_RECORD] and one["last_day"] == DAYS[-1]   # full 52-week window
    assert tq.update(copy.deepcopy(one), f, DAYS[-1]) == one          # frozen once written
    assert all(r["target"] in (0.0, 0.25, 0.5, 0.75, 1.0) for r in one["days"].values())


def test_update_never_restarts_a_ledger_it_cannot_join():
    f = tq.frame_from_market(market())
    led = tq.update(tq.new_ledger(), f, DAYS[300])
    frozen = copy.deepcopy(led)
    gap = f.drop(index=pd.Timestamp(DAYS[300]))              # the download lost the ledger's last day
    assert tq.update(copy.deepcopy(led), gap, DAYS[-1]) == frozen


def test_capitulation_hold_does_not_reenter_on_its_exit_bar():
    n = 40
    ind = {"rfast": np.zeros(n, bool), "vol": np.full(n, 0.5), "dd52": np.zeros(n), "ret10": np.zeros(n),
           "cap": np.zeros(n, bool), "golden": np.ones(n, bool), "hy_calm": np.zeros(n, bool),
           "hy_wide": np.zeros(n, bool), "d200": np.zeros(n), "gold_up": np.zeros(n, bool), "tqc": np.full(n, 100.0)}
    ind["cap"][[0, 16, 17]] = True                            # still signalling on the 16th day (expiry)
    out, _ = tq.run(ind)
    assert out["cap_hold"][:16].all() and not out["cap_hold"][16] and out["cap_hold"][17]
    ind["cap"][:] = False
    ind["cap"][[0, 3]] = True
    ind["tqc"][3:] = 80.0                                     # -20%: stopped on day 3 while signalling
    out, _ = tq.run(ind)
    assert out["cap_hold"][:3].all() and not out["cap_hold"][3:].any()


def test_fund_bars_trade_next_open_and_mark_gold_and_bills():
    led = tq.new_ledger()
    led["days"] = {
        "2026-01-02": {"target": 1.0, "gold": 0.0, "tqqq": 100.0, "tqqq_open": 100.0, "gold_px": 10.0, "rf": 0.0},
        "2026-01-05": {"target": 0.5, "gold": 0.5, "tqqq": 110.0, "tqqq_open": 105.0,
                       "gold_open": 10.0, "gold_px": 10.0, "rf": 0.0},
        "2026-01-06": {"target": 0.5, "gold": 0.5, "tqqq": 110.0, "tqqq_open": 110.0,
                       "gold_open": 11.0, "gold_px": 12.0, "rf": 0.0},
    }
    b = tq.fund_bars(led)
    assert b["2026-01-02"] == {"open": 1.0, "close": 1.0}
    # 01-02's 100% TQQQ is bought at the 01-05 open (105) and marked at its close
    assert abs(b["2026-01-05"]["open"] - 1.0) < 1e-12 and abs(b["2026-01-05"]["close"] - 110 / 105) < 1e-12
    # 01-05's 50/50 is bought at the 01-06 opens: gold's overnight move (10 -> 11) is not credited,
    # and the day return is the weighted sum (0.5 x 0% + 0.5 x 12/11-1), not a compounded product
    nav = 110 / 105
    assert abs(b["2026-01-06"]["open"] - nav) < 1e-12
    assert abs(b["2026-01-06"]["close"] - nav * (1 + 0.5 * (12 / 11 - 1))) < 1e-12


def test_top_card_states_total_asset_shares(tmp_path: Path):
    led = tq.new_ledger()
    led["days"] = {"2026-10-07": {"target": 0.75, "gold": 0.25, "trend": True, "hy": 3.0}}
    page = '<html><head></head><body><div class="wrap"><nav>n</nav></div></body></html>'
    out = tq.apply_top(page, led, 50, stock=0.6, session="2026-10-07")
    assert out.index(tq.CARD_ID) < out.index("<nav") and out.count(f'id="{tq.CARD_ID}"') == 1
    # idle 40% x sleeve 50% = 20%: TQQQ 75% of it = 15%, gold 5%, cash 20%
    assert "資産全体の配分" in out
    for name, v in (("個別株", "60%"), ("TQQQ", "15%"), ("金", "5%"), ("現金・短期国債", "20%")):
        assert f"{name} <b>{v}</b>" in out, name
    assert "平時" in out and "判定のまま" not in out
    assert tq.apply_top(out, led, 50, stock=0.6, session="2026-10-07") == out
    assert out.count('id="tqqq-rule-style"') == 1
    stale = tq.apply_top(page, led, 50, stock=0.6, session="2026-10-08")
    assert "2026-10-08の入力が欠けたため、2026-10-07の判定のままです" in stale
    plain = tq.apply_top(page, led, 100, stock=None)
    assert "個別株以外のお金の配分" in plain and "TQQQ <b>75%</b>" in plain and "金 <b>25%</b>" in plain
    assert "<td>37.5%</td>" in plain                          # 50% in stocks -> 50% x 100% x 75%
    led["days"]["2026-10-08"] = {"target": 0.0, "gold": 1.0, "alarm": True}
    out2 = tq.apply_top(out, led, 100, stock=0.5)
    assert out2.count(f'id="{tq.CARD_ID}"') == 1 and "過熱警報" in out2
    assert "判定不可" in tq.apply_top(page, None, 50)


def test_hy_uses_only_values_published_before_the_session():
    s = pd.Series({pd.Timestamp("2026-10-02"): 3.10, pd.Timestamp("2026-10-05"): 3.12,
                   pd.Timestamp("2026-10-06"): 3.03, pd.Timestamp("2026-10-07"): 3.09})
    got = tq.known_before(s, pd.DatetimeIndex(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]))
    assert list(got) == [3.10, 3.12, 3.03, 3.09]          # Monday uses Friday's; never the same day's value
