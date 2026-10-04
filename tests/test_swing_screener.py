from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from swing_screener import CARD_ID, apply, card_html, evaluate  # noqa: E402



# Known, open market regime (unknown regime now stops new entries).
ON = {"on": True, "close": 110.0, "ma": 100.0, "date": "2026-01-02"}

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
    html = card_html({"regime": ON, "session": "2026-01-02", "core": [], "watch": [], "ep": [], "universe": 0})
    assert "週足SARの鮮度と形がそろうのを待つ" in html


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



def test_late_entry_requires_buyable_on_its_signal_day(monkeypatch):
    import swing_screener as ss
    frame = _frame()
    last_day = frame["date"].max()
    lead = (frame["ticker"] == "LEAD") & (frame["date"] == last_day)
    frame.loc[lead, ["open", "high", "low", "close"]] *= 1.01
    frame.loc[lead, "volume"] = 2.0e7
    real = ss.weekly_sar_state

    def sar(high, low, close):  # bearish as of the signal day, bullish today
        return (False, None) if high.index[-1] < last_day else real(high, low, close)

    monkeypatch.setattr(ss, "weekly_sar_state", sar)
    result = ss.evaluate(frame)
    assert result["late"] == []

def test_watch_badges_show_current_and_required_values():
    from swing_screener import _miss_label
    r = {"vc": 0.9004, "vdry": 1.07, "chg": 0.0298, "prev_chg": 0.039, "ext10": 0.141}
    assert _miss_label("収縮", r) == "値幅 0.9004 → 0.90以下"
    assert _miss_label("出来高減", r) == "出来高 1.070 → 0.90以下"
    assert _miss_label("前日+3%以下", r) == "前日 +3.90% → +3%以下"
    assert _miss_label("10日線+12%以内", r) == "10日線 +14.10% → +12%以内"


def test_structure_pivot_detects_ll_to_hl_and_invalidates_on_break():
    from swing_screener import structure_pivot
    # Down to a low (LL) at 10, rally to 20, pull back to a higher low (HL) at 14, then drift.
    low = np.r_[np.linspace(30, 10, 20), np.linspace(10.5, 19.5, 10), np.linspace(19, 14, 8), np.linspace(14.5, 17, 12)]
    high = low + 1.0
    line, hl = structure_pivot(high, low)
    assert abs(hl - 14.0) < 1e-9
    assert line >= 20.0  # highest high between LL and HL
    broken = np.r_[low, [13.0]]
    line2, hl2 = structure_pivot(np.r_[high, [14.0]], broken)
    assert not (abs(hl2 - 14.0) < 1e-9)  # the 14.0 HL setup is invalidated by the break


def test_inside_structure_is_listed_first():
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 2, "watch": [], "ep": [], "late": [],
                      "core": [{"ticker": "AAA", "close": 10.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80,
                                "dv": 99, "vc": 0.8, "vdry": 0.8, "ext10": 0.0, "el21": 9.5, "stop": 9.2,
                                "add": 11.0, "be": 12.5, "pivot_line": 10.5, "hl": 9.6, "inside": True, "pos": 0.6, "streak": 3,
                                "sar_up": True, "sar_age": 3}]})
    assert "HL構造・ライン下" in html and "RS21 50・63 80" in html and "選定3日目" in html
    assert 'data-tkone="AAA"' in html  # tap opens the shared ticker detail overlay
    assert "買い増し +10%" in html and "買い増し +20%" in html and "$12.00" in html  # second add level (falls back to close x1.20)
    assert "最大6銘柄" in html


def test_option_walls_render_and_failures_are_harmless():
    frame = _frame()
    page = '<html><head></head><body><section id="t-alloc"></section></body></html>'
    asked = []
    fake = lambda targets, session: asked.extend(targets) or {}
    apply(page, frame, walls_fn=fake)
    assert asked[0] == "LEAD"
    assert len(asked) == len(set(asked))  # candidates first, dollar-volume top 5% added once
    study = evaluate(frame)["study"]
    assert study and {t for t, _, _ in study} <= set(asked)
    assert {g for _, _, g in study} <= {"dv", "rs189", "rs63", "rs21"}
    store: dict = {}
    def record(targets, session):
        store.update({t: {"cw": 1.0, "cwp": 0.01} for t in targets})
        return store
    apply(page, frame, walls_fn=record)
    assert store["LEAD"]["grp"] == "cand"
    assert {store[t]["grp"] for t, _, _ in study} <= {"cand", "dv", "rs189", "rs63", "rs21"}
    opt = {"cw": 66.0, "cwp": 0.1, "pw": 55.0, "pwp": -0.08, "gf": 58.5, "gfp": -0.025, "conf": "OK"}
    row = {"ticker": "AAA", "close": 60.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99, "vc": 0.8,
           "vdry": 0.8, "ext10": 0.0, "el21": 57.0, "stop": 55.2, "add": 66.0, "be": 75.0, "pivot_line": 64.0,
           "hl": 52.0, "inside": True, "pos": 0.67, "streak": 3, "opt": opt, "sar_up": True, "sar_age": 2}
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 1, "watch": [], "ep": [], "late": [],
                      "core": [row]})
    assert "OP 上値の壁</i><b>$66 <em>+10.0%</em>" in html and "<b>$58.50 <em>" in html

    def broken(targets, session):
        raise RuntimeError("cboe down")

    assert CARD_ID in apply(page, frame, walls_fn=broken)


def test_sections_split_best_waiting_and_good_watch():
    base = {"close": 100.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99, "vc": 0.8, "vdry": 0.8,
            "ext10": 0.0, "el21": 95.0, "stop": 92.0, "add": 110.0, "be": 125.0, "streak": 3}
    best = {**base, "ticker": "BEST", "pivot_line": 110.0, "hl": 80.0, "inside": True, "pos": 2 / 3,
            "sar_up": True, "sar_age": 3}
    far = {**base, "ticker": "FAR", "pivot_line": 85.0, "hl": 70.0, "inside": False, "pos": None,
           "sar_up": False, "sar_age": None}
    gw = {**base, "ticker": "GW", "pivot_line": 110.0, "hl": 80.0, "inside": True, "pos": 2 / 3,
          "missing": ["収縮"], "vc": 0.93, "sar_up": True, "sar_age": 4}
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 3, "ep": [], "late": [],
                      "core": [far, best], "watch": [gw]})
    i_best, i_gw, i_far = (html.index(f'data-tkone="{t}"') for t in ("BEST", "GW", "FAR"))
    assert i_best < i_gw < i_far
    assert "好位置 $77.50〜$81.25" in html
    assert "あと1条件" in html and "値幅 0.930 → 0.90（あと3.2%縮小）" in html


def test_good_position_badge_and_structure_export(tmp_path):
    import json
    from swing_screener import write_structure
    base = {"ticker": "AAA", "close": 10.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99,
            "vc": 0.8, "vdry": 0.8, "ext10": 0.0, "el21": 9.5, "stop": 9.2, "add": 11.0, "be": 12.5,
            "pivot_line": 11.0, "hl": 8.0, "inside": True, "streak": 3, "sar_up": True, "sar_age": 3}
    page = lambda pos: card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 1, "watch": [], "ep": [],
                                  "late": [], "core": [{**base, "pos": pos}]})
    assert '<span class="sw-c good">好位置</span>' in page(0.6) and "位置 60%" in page(0.6)
    assert '<span class="sw-c good">好位置</span>' not in page(0.9)
    out = tmp_path / "structure.json"
    low = np.r_[np.linspace(30, 10, 20), np.linspace(10.5, 19.5, 10), np.linspace(19, 14, 8), np.linspace(14.5, 17, 12)]
    dates = pd.bdate_range("2026-01-01", periods=len(low))
    frame = pd.DataFrame({"ticker": "AAA", "date": dates, "open": low + .5, "high": low + 1, "low": low, "close": low + .5})
    assert write_structure(frame, out) == 1
    s = json.loads(out.read_text())["AAA"]
    assert s["hl"] == 14.0 and s["lld"] < s["lined"] < s["hld"]


def test_weekly_sar_and_priority_tiers():
    from swing_screener import psar_flags, tier, weekly_sar_state
    # Down 20 weeks, then up 6 weeks: one bull flip near the turn.
    c = np.r_[np.linspace(100, 60, 20), np.linspace(62, 90, 6)]
    up, flip = psar_flags(c + 1, c - 1, c)
    assert not up[15] and up[-1] and flip.sum() == 1 and 20 <= int(np.where(flip)[0][0]) <= 24
    days = pd.bdate_range("2025-01-06", periods=26 * 5)
    daily = np.repeat(c, 5)
    sar_up, age = weekly_sar_state(pd.Series(daily + 1, days), pd.Series(daily - 1, days), pd.Series(daily, days))
    assert sar_up and age == 25 - int(np.where(flip)[0][0])
    r = {"pivot_line": 110.0, "hl": 80.0, "pos": 0.6, "sar_up": True}
    assert tier({**r, "sar_age": 3}) == "S"
    assert tier({**r, "pos": 0.9, "sar_age": 3}) == "A"
    assert tier({**r, "pos": 0.9, "sar_age": 1}) == "B"
    assert tier({**r, "sar_age": 7}) == "B"  # 好位置 but no longer fresh
    assert tier({**r, "sar_age": 12}) == "C"  # 好位置 does not rescue a stale SAR
    assert tier({**r, "pos": 0.9, "sar_age": 12}) == "C"
    assert tier({**r, "sar_up": False, "sar_age": None}) == "D"


def test_watch_bucket_order():
    from swing_screener import watch_bucket
    r = {"pivot_line": 110.0, "hl": 80.0, "pos": 0.9, "sar_up": True}
    sa1 = {**r, "sar_age": 3, "missing": ["収縮"]}
    b1 = {**r, "sar_age": 7, "missing": ["収縮"]}
    sa2 = {**r, "sar_age": 3, "missing": ["収縮", "出来高減"]}
    c2 = {**r, "sar_age": 12, "missing": ["収縮", "出来高減"]}
    assert [watch_bucket(x) for x in (sa1, b1, sa2, c2)] == [0, 1, 2, 4]


def test_low_priority_late_entries_move_to_fold():
    base = {"close": 100.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99, "vc": 0.8, "vdry": 0.8,
            "ext10": 0.0, "el21": 95.0, "stop": 92.0, "add": 110.0, "be": 125.0, "streak": 3, "lag": 1,
            "signal_date": "2026-01-01", "signal_close": 99.0, "from_signal": 0.01,
            "pivot_line": 110.0, "hl": 80.0, "inside": True, "pos": 0.9}
    ok = {**base, "ticker": "LATEA", "sar_up": True, "sar_age": 3}
    bear = {**base, "ticker": "LATED", "sar_up": False, "sar_age": None}
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 2, "ep": [], "core": [], "watch": [],
                      "late": [ok, bear]})
    fold = html.index('class="sw-fold"')
    assert html.index('data-tkone="LATEA"') < fold < html.index('data-tkone="LATED"')
    assert "1日前に成立" in html


def test_buy_set_is_sar_bull_outside_hl_side():
    from swing_screener import buyable
    r = {"pivot_line": 110.0, "hl": 80.0, "sar_up": True, "sar_age": 12}
    assert buyable({**r, "inside": False, "pos": None})          # extended above the line: still bought
    assert buyable({**r, "inside": True, "pos": 0.9})            # right under the line
    assert not buyable({**r, "inside": True, "pos": 0.3})        # HL-side zone
    assert not buyable({**r, "sar_up": False, "inside": True, "pos": 0.6})


def test_regime_stops_new_entries_but_keeps_watchlist(tmp_path):
    import json
    from swing_screener import regime_from_market
    rows = [{"date": f"d{i:03d}", "close": 100.0 + i * 0.1} for i in range(220)]
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"series": {"QQQ": rows}}))
    assert regime_from_market(f)["on"] is True
    rows[-1]["close"] = 50.0
    f.write_text(json.dumps({"series": {"QQQ": rows}}))
    reg = regime_from_market(f)
    assert reg["on"] is False
    assert regime_from_market(tmp_path / "missing.json") is None
    assert regime_from_market(f, "d219")["on"] is False          # dated session matches
    assert regime_from_market(f, "d220") is None                 # stale QQQ is not today
    rows.append({"date": "d220", "close": None})                 # today's close missing
    f.write_text(json.dumps({"series": {"QQQ": rows}}))
    assert regime_from_market(f, "d220") is None
    unknown = card_html({"session": "2026-01-02", "universe": 1, "selected": 1, "ep": [], "late": [], "watch": [],
                         "core": [{**{"close": 100.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99,
                                      "vc": 0.8, "vdry": 0.8, "ext10": 0.0, "el21": 95.0, "stop": 92.0, "add": 110.0,
                                      "be": 125.0, "streak": 3, "pivot_line": 110.0, "hl": 80.0, "inside": True,
                                      "pos": 0.9, "sar_up": True, "sar_age": 3}, "ticker": "BUY"}], "regime": None})
    assert "地合い：判定不可" in unknown and 'data-regime="unknown"' in unknown
    assert unknown.index('data-tkone="BUY"') > unknown.index('class="sw-fold"')   # no 本命 when unknown
    base = {"close": 100.0, "chg": 0.0, "rs189": 99, "rs21": 50, "rs63": 80, "dv": 99, "vc": 0.8, "vdry": 0.8,
            "ext10": 0.0, "el21": 95.0, "stop": 92.0, "add": 110.0, "be": 125.0, "streak": 3,
            "pivot_line": 110.0, "hl": 80.0, "inside": True, "pos": 0.9, "sar_up": True, "sar_age": 3}
    watch = {**base, "ticker": "NEXT", "missing": ["収縮"], "vc": 0.93}
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 2, "ep": [], "late": [],
                      "core": [{**base, "ticker": "BUY"}], "watch": [watch], "regime": reg})
    assert "地合い：新規停止" in html
    assert html.index('data-tkone="BUY"') > html.index('class="sw-fold"')   # moved out of 本命
    assert 'data-tkone="NEXT"' in html                                       # watchlist still shown
    ok = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 2, "ep": [], "late": [],
                    "core": [{**base, "ticker": "BUY"}], "watch": [], "regime": {"on": True, "close": 110.0, "ma": 100.0}})
    assert "地合いOK" in ok and ok.index('data-tkone="BUY"') < ok.find('class="sw-fold"') if 'sw-fold' in ok else True


def test_good_leader_rule_and_card_section():
    from swing_screener import good_leader_ok
    base = {"sar_up": True, "sar_age": 3, "inside": True, "pos": 0.6}
    assert good_leader_ok(base)
    assert not good_leader_ok({**base, "sar_age": 9})
    assert not good_leader_ok({**base, "sar_age": None})
    assert not good_leader_ok({**base, "sar_up": False})
    assert not good_leader_ok({**base, "pos": 0.45}) and not good_leader_ok({**base, "pos": 0.8})
    assert not good_leader_ok({**base, "inside": False})
    row = {"ticker": "GLD1", "close": 50.0, "chg": 0.01, "rs189": 85, "rs21": 70, "rs63": 88, "dv": 60,
           "vc": 0.8, "vdry": 0.8, "ext10": 0.0, "el21": 48.0, "stop": 46.0, "add": 55.0, "add2": 60.0, "be": 62.5,
           "pivot_line": 52.0, "hl": 46.0, "inside": True, "pos": 0.66, "streak": None, "sar_up": True, "sar_age": 2,
           "missing": []}
    near = {**row, "ticker": "GLD2", "missing": ["出来高減"], "vdry": 0.95}
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 10, "selected": 0, "core": [], "watch": [], "ep": [], "late": [],
                      "glead": [row], "glead_near": [near]})
    assert "好位置リーダー（検討可）" in html and 'data-tkone="GLD1"' in html and 'data-tkone="GLD2"' in html
    assert "あと1つ" in html and "週足SAR 2週目" in html and "監視リスト" in html and "買い増し +20%" in html
    empty = card_html({"regime": ON, "session": "2026-01-02", "universe": 10, "selected": 0, "core": [], "watch": [], "ep": [], "late": []})
    assert "好位置リーダー（検討可）" in empty


def test_good_leader_counts_copy_and_overlap_match():
    base = {"close": 100.0, "chg": 0.0, "rs189": 90, "rs21": 50, "rs63": 85, "dv": 60, "vc": 0.8, "vdry": 0.8,
            "ext10": 0.0, "el21": 95.0, "stop": 92.0, "add": 110.0, "be": 125.0, "streak": 3, "pivot_line": 110.0,
            "hl": 80.0, "inside": True, "pos": 0.6, "sar_up": True, "sar_age": 2}
    glead = [{**base, "ticker": f"G{i}"} for i in range(12)]
    near = [{**base, "ticker": "N1", "missing": ["収縮"]}, {**base, "ticker": "BEST", "missing": ["収縮"]}]
    html = card_html({"regime": ON, "session": "2026-01-02", "universe": 1, "selected": 1, "ep": [], "late": [],
                      "watch": [], "core": [{**base, "ticker": "BEST"}], "glead": glead, "glead_near": near})
    assert "好位置<b>13</b>" in html                                    # 12 + N1 (BEST is already 本命)
    i = html.index("好位置リーダー（検討可）")
    copy = html[i:html.index("</div>", i)]
    assert "G11" in copy and "N1" in copy and "BEST" not in copy
    assert "全 12+1件" in html
