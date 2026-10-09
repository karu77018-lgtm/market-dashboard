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
    assert "保有モデルの個別株比率を使った資産全体の目標配分（翌営業日）" in out
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


def test_legacy_inventory_is_read_only_and_explicitly_historical(tmp_path):
    import track_record as tr
    import track_portfolio as tp
    led = tr.new_ledger()
    led['rule'] = 'swing-v2-max6'
    old = tp.new_portfolio('2026-10-05', legacy_tqqq=True)
    old['equity'] = [['2026-10-05', 1, 100], ['2026-10-08', 1, 100]]
    old['last_day'] = '2026-10-08'
    old['cash'] = .245
    old['positions'] = {'AAA': {'shares': .0067, 'last': 100}}
    old.pop('rule'); old.pop('sleeve')
    led['portfolio'] = old
    tr.save(led, tmp_path / tr.LEDGER)
    before = (tmp_path / tr.LEDGER).read_bytes()
    state = tq.holding_state(tmp_path)
    assert abs(state['stock'] - .67) < 1e-12 and state['as_of'] == '2026-10-08'
    assert state['inherited'] and state['sleeve'] == 'QQQ'
    assert abs(state['stock'] + state['cash'] + state['sleeve_share'] - 1) < 1e-12
    text = tq.card_html('2026-10-08', {'target': .25}, 50, top=True, stock=state['stock'], holdings=state)
    assert 'QQQ 8.5%' in text and '現金 24.5%' in text
    assert 'TQQQ <b>4.1%</b>' in text and '現金・短期国債 <b>28.9%</b>' in text
    assert 'data-stock-asof="2026-10-08"' in text and '旧ルールの保存保有記録（比較用）' in text
    assert '旧配分から引き継ぎ' not in text and '20%ずつに買い直していません' not in text
    assert '記録開始待ち' not in text and '保有モデルの個別株比率を使った資産全体の目標配分（翌営業日）' in text
    assert (tmp_path / tr.LEDGER).read_bytes() == before


def test_pending_stock_share_shows_idle_money_target_and_explicit_wait():
    rec = {'target': .25, 'gold': 0, 'trend': True}
    out = tq.card_html('2026-10-08', rec, 50, top=True, stock=None)
    assert '新ルールで再計算した保有モデルを確認できない' in out
    assert '最大5銘柄・初回20%' in out and '旧ルールの保有比率は使いません' in out
    assert 'TQQQ <b>12.5%</b>' in out
    assert '現金・短期国債 <b>87.5%</b>' in out
    assert '資産全体の配分（今日の目標）' not in out
    assert '個別株 <b>' not in out and '80%' not in out
    assert '個別株以外のお金の配分（今日の目標）' in out


def test_primary_model_preferred_over_old_holdings_with_reconstruction_provenance(tmp_path):
    import track_record as tr
    import track_portfolio as tp

    led = tr.new_ledger()
    old = tp.new_portfolio('2026-10-05', legacy_tqqq=True)
    old.update(equity=[['2026-10-05', 1, 100], ['2026-10-08', 1, 100]],
               last_day='2026-10-08', cash=.245,
               positions={'OLD': {'shares': .0067, 'last': 100}})
    led['portfolio'] = copy.deepcopy(old)
    led['current_portfolio'] = copy.deepcopy(old)
    modeled = tp.new_portfolio('2026-10-05')
    modeled.update(equity=[['2026-10-05', 1, 100], ['2026-10-08', 1, 100]],
                   last_day='2026-10-08', cash=.191597,
                   positions={t: {'shares': weight / 100, 'last': 100}
                              for t, weight in [('AAA', .22), ('BBB', .215), ('CCC', .20), ('DDD', .173403)]})
    modeled['reconstruction'] = {'kind': 'chart-ohlcv-backcast', 'as_of': '2026-10-08',
                                 'generated_at': '2026-10-09T06:50:00Z', 'input_commit': 'abc123',
                                 'inputs': {'chart-data/AAA.json': 'abc456'},
                                 'price_note': '修正後のチャート価格を使用'}
    led['modeled_portfolio'] = modeled
    tr.save(led, tmp_path / tr.LEDGER)
    before = (tmp_path / tr.LEDGER).read_bytes()

    state = tq.holding_state(tmp_path)
    assert abs(state['stock'] - .808403) < 1e-12
    assert abs(state['cash'] - .191597) < 1e-12 and abs(state['sleeve_share']) < 1e-12
    assert {p['ticker'] for p in state['positions']} == {'AAA', 'BBB', 'CCC', 'DDD'}
    assert not state['inherited'] and state['source'] == 'modeled_portfolio'
    assert state['reconstruction'] == modeled['reconstruction']
    assert state['label'] == '新ルールで再計算した保有モデル'
    assert abs(tq.stock_share(tmp_path) - .808403) < 1e-12

    text = tq.card_html('2026-10-08', {'target': .25}, 50, top=True, stock=state['stock'], holdings=state)
    assert '新ルールで再計算した保有モデル：2026-10-08終値時点' in text
    assert '最大5銘柄・初回は総資産の20%' in text
    assert '個別株 <b>80.8%</b>' in text and '現金 19.2%' in text
    assert 'TQQQルール枠（NAV） 0.0%' in text
    assert 'TQQQ <b>2.4%</b>' in text and '現金・短期国債 <b>16.8%</b>' in text
    assert 'width:80.84%' in text  # stock weight is not rounded before residual target math
    assert '目標配分（翌営業日）' in text and '同日の保有内訳とは別' in text
    assert '修正後のチャートOHLCV価格' in text and '修正後のチャート価格を使用' in text
    assert '旧台帳は比較用の履歴としてそのまま保存' in text
    assert '実取引の過去実績ではありません' in text
    assert 'data-stock-source="modeled_portfolio"' in text
    assert 'data-reconstruction-kind="chart-ohlcv-backcast"' in text
    assert 'data-reconstruction-asof="2026-10-08"' in text
    assert 'data-reconstruction-generated-at="2026-10-09T06:50:00Z"' in text
    assert 'data-reconstruction-input-commit="abc123"' in text
    assert '旧配分から引き継ぎ' not in text and '20%ずつに買い直していません' not in text
    assert (tmp_path / tr.LEDGER).read_bytes() == before


def test_reconstruction_labels_escape_price_note_and_source_metadata():
    state = {'as_of': '2026-10-08', 'stock': .8, 'cash': .2, 'sleeve_share': 0,
             'sleeve': 'TQQQルール枠（NAV）', 'positions': [], 'inherited': False,
             'source': 'modeled_portfolio',
             'reconstruction': {'kind': 'chart-ohlcv-backcast', 'as_of': '2026-10-08',
                                'price_note': '<script>unsafe</script>', 'input_commit': '"quoted"'}}
    text = tq.holdings_html(state)
    assert '<script>unsafe</script>' not in text
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in text
    assert 'data-reconstruction-input-commit="&quot;quoted&quot;"' in text
