import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import decline_anatomy as da  # noqa: E402

DAYS = pd.bdate_range("2024-01-02", periods=520)
PAGE = ('<html><head><title>x</title></head><body><section id="t-market">'
        '<div class="card" id="daily-index-internals-divergence"><div class="sub">a</div></div>'
        '<div class="card ch-card" id="rule-changelog"><h2>前回からの変化</h2></div>'
        '<div class="msec"><div class="msec-l">② 相場の強さ</div></div></section></body></html>')


def _path(drop: float, tail: int = 20, recover: bool = False) -> np.ndarray:
    """Steady rise, then ``drop`` over 15 sessions, then flat (or back to the high)."""
    up = 100 * 1.0006 ** np.arange(len(DAYS) - tail - 15)
    down = up[-1] * np.linspace(1, 1 + drop, 16)[1:]
    end = np.full(tail, down[-1]) if not recover else np.linspace(down[-1], up[-1] * 0.99, tail)
    return np.concatenate([up, down, end])


def _market(drop: float = -0.12, recover: bool = False, spy_drop: float = -0.03) -> dict:
    q = _path(drop, recover=recover)
    series = {"QQQ": q, "SPY": _path(spy_drop), "^VIX": np.where(np.arange(len(DAYS)) > len(DAYS) - 36, 24.0, 15.0),
              "^TNX": np.full(len(DAYS), 4.0)}
    for s in ("IWM", "RSP", "IWF", "IWD", "SOXX", "TLT", "GC=F", "CL=F", "DX-Y.NYB", "JPY=X", *da.SECTORS):
        series[s] = _path(-0.20 if s == "SOXX" else 0.02 if s in da.SECTORS else -0.03)
    return {"series": {k: [{"date": str(d.date()), "close": float(v)} for d, v in zip(DAYS, vals)]
                       for k, vals in series.items()}}


def _slow() -> dict:
    days = pd.date_range("2022-01-01", "2026-01-01", freq="MS")
    month = {str(d.date()): 30.0 + i * 0.1 for i, d in enumerate(days)}
    return {"cape": month, "margin": {k: 1000.0 * 1.02 ** i for i, k in enumerate(month)},
            "mmf": {k: 2000.0 * 1.005 ** i for i, k in enumerate(month)},
            "baa": {k: 1.5 for k in month}, "dgs10": {k: 4.0 for k in month}, "dtb3": {k: 4.5 for k in month}}


def test_reference_table_is_complete():
    assert len(da.EPISODES) >= 40
    for e in da.EPISODES:
        assert {"peak", "trigger", "more", "r20", "r120", "r250", "r500", "rec12", "inv18"} <= set(e)
        assert all(k in e for k in da.FACTORS), e["peak"]
    assert {da.classify(e) for e in da.EPISODES} == set(da.TYPES)
    # the published study figures the card quotes
    assert da.heat_stats()["both_n"] == 10 and da.heat_stats()["both_deep"] == 6
    rs = da.recession_stats(True, False)
    assert rs["rec_n"] == 6 and rs["non_n"] == 34 and rs["same_n"] == 4 and rs["same_rec"] == 1


def test_episode_opens_at_minus_ten_and_closes_within_four_percent():
    q = pd.Series(_path(-0.12), index=DAYS)
    ep = da.find_episode(q)
    assert ep["active"] and ep["peak"] == q.idxmax() and q[ep["trigger"]] / q.max() - 1 <= -0.10
    assert q[:ep["trigger"]].iloc[-2] / q.max() - 1 > -0.10          # the first day at or below -10%
    assert not da.find_episode(pd.Series(_path(-0.12, recover=True), index=DAYS))["active"]
    shallow = da.find_episode(pd.Series(_path(-0.08), index=DAYS))
    assert not shallow["active"] and "peak" not in shallow


def test_factors_and_type_from_market_inputs():
    state = da.build_state(_market(), _slow())
    f = {k: v["v"] for k, v in state["factors"].items()}
    assert state["active"] and state["type"] == "ハイテク単独安（資金移動）型"   # SPY holds up, rates and credit flat
    assert f["spx"] > 5 and f["sox"] < -5 and f["secup"] == 9 and f["d10"] == 0 and f["cred"] == 0
    assert state["inv18"] is True and round(f["md_yoy"]) == round((1.02 ** 12 - 1) * 100)
    assert json.loads(json.dumps(state)) == state                    # plain JSON
    assert da.build_state({"series": {}}, _slow()) is None
    flat = da.build_state(_market(drop=-0.05), _slow())
    assert flat["active"] is False and "factors" not in flat


def test_classify_and_rank_edges():
    assert da.classify({"cred": 20, "d10": -30, "spx": 9}) == "信用不安・質への逃避型"
    assert da.classify({"cred": 20, "d10": 30, "spx": 9}) == "金利上昇型"
    assert da.classify({"cred": None, "d10": -30, "spx": 9}) == "ハイテク単独安（資金移動）型"
    assert da.classify({"cred": 0, "d10": 0, "spx": 1}) == "全面安型"
    past = sorted(e["dfn"] for e in da.EPISODES if e["dfn"] is not None)
    assert da.rank("dfn", past[-1] + 1) == {"n": len(past), "lo": len(past) + 1, "hi": 1, "side": "high"}
    assert da.rank("dfn", past[0] - 1)["side"] == "low" and da.rank("dfn", float(np.median(past)))["side"] is None
    assert da.rank("dfn", None) is None


def test_public_series_parsers_and_fallback():
    assert da.parse_fred_csv("observation_date,X\n2026-01-02,1.5\n2026-01-05,.\n") == {"2026-01-02": 1.5}
    assert da.parse_multpl("<tr><td>Nov 1, 2026</td><td>&#x2002;39.82\n</td></tr>") == {"2026-11-01": 39.82}
    assert da.parse_finra("<tr><td>Oct-26</td><td>1,448,360</td><td>1</td></tr>") == {"2026-10-31": 1448360.0}
    calls = []

    def getter(url):
        calls.append(url)
        if "fred" in url:
            raise TimeoutError
        return "<tr><td>Nov 1, 2026</td><td>40.1</td></tr>" * 6

    out = da.refresh_slow(_slow(), getter)
    assert out["baa"] == _slow()["baa"] and sum("fred" in u for u in calls) == 1   # one wait per site
    assert da.refresh_slow(_slow(), lambda u: (_ for _ in ()).throw(OSError())) == _slow()


def test_card_is_placed_before_the_change_log_and_is_stable():
    state = json.loads((ROOT / da.STATE_SEED).read_text(encoding="utf-8"))
    out = da.apply(PAGE, state)
    assert out.index('id="daily-index-internals-divergence"') < out.index(f'id="{da.CARD_ID}"') < out.index('id="rule-changelog"')
    assert out.index('id="rule-changelog"') < out.index('<div class="msec">')    # the change-log rebuild keys on this
    assert da.apply(out, state) == out and out.count(da.STYLE_ID) == 1
    assert da.embedded_state(out) == state
    soup = str(BeautifulSoup(out, "html.parser"))                               # other adapters re-serialise the page
    assert da.CARD_RE.search(soup).group(0) == da.CARD_RE.search(out).group(0)
    for words in ("いつもと違う点", "景気後退チェック", "過熱チェック", "期間で変わる傾向", "下げの中身が近い過去の下げ", "売買ルールは変えません"):
        assert words in out
    assert da.apply(PAGE.replace('<div class="card ch-card"', '<div class="card"'), state).count(da.CARD_ID) == 0
    assert da.apply(PAGE, None) == PAGE


def test_inactive_card_and_display_only_rerender(tmp_path):
    calm = da.apply(PAGE, {"session": "2026-01-05", "index": "QQQ", "active": False, "dd_now": -2.3})
    assert "調整局面ではありません" in calm and "過熱チェック" not in calm
    assert da.rerender(calm, tmp_path) == calm                                   # re-rendered from the embedded state
    assert da.rerender(PAGE, tmp_path) == PAGE                                   # no state, no seed: untouched
    seed = json.loads((ROOT / da.STATE_SEED).read_text(encoding="utf-8"))
    (tmp_path / "seed").mkdir()
    (tmp_path / da.STATE_SEED).write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "1999-01-04"}), encoding="utf-8")
    assert da.rerender(PAGE, tmp_path) == PAGE                                   # seed of another session is not shown
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": seed["session"]}), encoding="utf-8")
    assert da.CARD_ID in da.rerender(PAGE, tmp_path)
    assert da.run(PAGE, tmp_path, seed["session"]) == da.rerender(PAGE, tmp_path)  # no market inputs: same as display path


def test_run_computes_from_the_refresh_inputs(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "market_inputs.json").write_text(json.dumps(_market()), encoding="utf-8")
    (tmp_path / "seed").mkdir()
    (tmp_path / da.SLOW_SEED).write_text(json.dumps({"series": _slow()}), encoding="utf-8")
    out = da.run(PAGE, tmp_path, str(DAYS[-1].date()), getter=lambda u: (_ for _ in ()).throw(OSError()))
    state = da.embedded_state(out)
    assert state["active"] and state["session"] == str(DAYS[-1].date()) and "ハイテク単独安" in out


def test_now_like_matches_older_weeks_only():
    state = da.build_state(_market(), _slow())
    like, today = state["now_like"], pd.Timestamp(state["session"])
    assert len(like) == 3 and like == sorted(like, key=lambda r: r["dist"])
    weeks = [pd.Timestamp(r["week"]) for r in like]
    assert all(w <= today - pd.Timedelta(days=da.NOW_EXCLUDE) for w in weeks)
    assert all(abs((a - b).days) > da.NOW_GAP for i, a in enumerate(weeks) for b in weeks[i + 1:])
    ref, feats = da._load_state_ref()
    assert len(ref) > 1000 and set(feats) <= set(da.state_frame(da._closes(_market()), _slow()).columns)
    assert all(pd.Timestamp(r["week"]) in ref.index for r in like)


def test_stale_inputs_and_saved_series(tmp_path):
    slow = _slow()  # monthly, last 2026-01-01
    assert da.stale_inputs(slow, "2026-01-10") == []
    late = {r["key"] for r in da.stale_inputs(slow, "2026-04-15")}
    assert {"margin", "cape", "mmf", "baa"} == late
    assert da.stale_inputs({}, "2026-01-20")[0]["last"] is None
    assert da.save_slow(tmp_path, slow, "2026-01-02") and not da.save_slow(tmp_path, slow, "2026-01-03")
    saved = json.loads((tmp_path / da.SLOW_SEED).read_text())
    assert saved["saved"] == "2026-01-02" and len(saved["series"]["cape"]) == da.SLOW_KEEP["cape"]
    grown = {**slow, "margin": {**slow["margin"], "2026-02-28": 9.0}}
    assert da.save_slow(tmp_path, grown, "2026-03-20") and da.load_slow(tmp_path)["margin"]["2026-02-28"] == 9.0


def test_card_shows_the_period_match_and_stale_warning():
    state = da.build_state(_market(), _slow())
    out = da.card_html(state)
    assert "今の相場にいちばん近い時期" in out and "近い時期のその後" in out and "下げの中身がいちばん近い過去の下げ" in out
    assert out.index("今の相場にいちばん近い時期") < out.index("いつもと違う点")
    assert "更新が止まっているデータ" not in out
    warned = da.card_html({**state, "stale": da.stale_inputs(_slow(), "2026-04-15")})
    assert "更新が止まっているデータ" in warned and "信用買い残（FINRA）" in warned and "日前" in warned
    calm = da.card_html({**da.build_state(_market(drop=-0.05), _slow()), "stale": []})
    assert "今の相場に近い時期" in calm and "今の相場にいちばん近い時期" in calm and "更新が止まっている" not in calm
    old = {k: v for k, v in state.items() if k not in ("now_like", "stale")}   # cards saved before this change
    assert "いつもと違う点" in da.card_html(old) and "いちばん近い時期" not in da.card_html(old)
