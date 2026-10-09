from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import track_portfolio as tp  # noqa: E402
import track_record as tr  # noqa: E402

D = [d.date().isoformat() for d in pd.bdate_range(end="2026-10-09", periods=30).append(pd.bdate_range("2026-10-12", periods=30))]
S = D[29]                       # signal session; history before it is flat at 100


def frame(paths: dict[str, list[tuple]]) -> pd.DataFrame:
    """paths: ticker -> bars (open, low, close) for D[30], D[31], ...; flat 100 before."""
    rows = []
    for t, bars in paths.items():
        for k in range(30):
            rows.append((t, D[k], 100.0, 100.5, 99.5, 100.0))
        for k, (o, lo, c) in enumerate(bars):
            rows.append((t, D[30 + k], o, max(o, c), lo, c))
    f = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close"])
    f["date"] = pd.to_datetime(f["date"])
    return f


def qqq(n: int, price: float = 100.0) -> dict:
    return {D[k]: {"open": price, "close": price} for k in range(n)}


def sessions(names: list[str], regime: str = "on", pct: int | None = 50, r189: dict | None = None) -> dict:
    return {S: {"best": [{"t": t, "r189": (r189 or {}).get(t)} for t in names], "regime": regime, "qqq_pct": pct}}


def write_fund(root: Path, n: int) -> None:
    """A TQQQ-rule ledger whose sleeve NAV stays flat (TQQQ 100% at a flat price)."""
    import tqqq_rule
    days = {D[k]: {"target": 1.0, "gold": 0.0, "tqqq": 100.0, "tqqq_open": 100.0, "rf": 0.0} for k in range(n)}
    tqqq_rule.save({**tqqq_rule.new_ledger(), "days": days, "last_day": D[n - 1]}, root / tqqq_rule.LEDGER)


def run(names, paths, n_days, **kw):
    pf = tp.new_portfolio(S)
    q = qqq(30 + n_days)
    return tp.advance(pf, sessions(names, **{k: v for k, v in kw.items() if k in ("regime", "pct", "r189")}),
                      frame(paths), q, D[29 + n_days], fund=q)   # sleeve NAV priced like QQQ


def test_entry_next_open_twenty_percent_and_idle_money_in_qqq():
    pf = run(["AAA"], {"AAA": [(100, 99.9, 110)]}, 1)
    p = pf["positions"]["AAA"]
    assert p["entry_day"] == D[30] and p["entry"] == 100 and abs(p["invested"] - 0.20) < 1e-12
    idle = 1 - 0.20
    assert abs(pf["qqq_sh"] * 100 - idle / 2) < 1e-12 and abs(pf["cash"] - idle / 2) < 1e-12
    assert abs(pf["equity"][-1][1] - (1 + (0.20) * 0.10)) < 1e-12       # AAA +10%, QQQ flat
    assert p["triggered"] == [0] and p["pending_add"] == 1


def test_five_slots_ranked_by_189_day_return():
    names = [f"T{k}" for k in range(6)]
    r189 = {t: k / 10 for k, t in enumerate(names)}                        # T5 strongest, T0 weakest
    pf = run(names, {t: [(100, 99.9, 100)] for t in names}, 1, r189=r189)
    assert set(pf["positions"]) == {f"T{k}" for k in range(1, 6)}
    assert pf["skipped"] == [{"t": "T0", "signal": S, "day": D[30], "why": "5銘柄で満杯"}]
    assert abs(pf["cash"] + pf["qqq_sh"] * 100) < 1e-12                   # 5 x 20% = fully invested


def test_regime_off_buys_nothing_and_unknown_pct_keeps_last():
    pf = run(["AAA"], {"AAA": [(100, 99.9, 100)]}, 1, regime="off", pct=None)
    assert pf["positions"] == {} and abs(pf["qqq_sh"] * 100 - 0.5) < 1e-12


def test_same_amount_adds_never_exceed_forty_percent():
    up = [(100, 99.9, 110), (111, 110.5, 125), (126, 125, 160), (160, 159, 170)]
    pf = run(["AAA"], {"AAA": up}, 4, pct=0)
    p = pf["positions"]["AAA"]
    assert p["adds"] == 1
    first_add = min(0.20, 0.40 * (0.80 + 0.20 / 100 * 111) - 0.20 / 100 * 111)
    first = 0.20 / 100 + first_add / 111                                 # full same-amount add at 111
    eq_open = (0.80 - first_add) + first * 126
    second = max(0, min(0.20, 0.40 * eq_open - first * 126))                      # the 40% cap binds at 126
    assert second < 0.20 and abs(p["shares"] - (first + second / 126)) < 1e-12
    big = run(["AAA"], {"AAA": [(100, 99.9, 110), (300, 299, 300)]}, 2, pct=0)
    q = big["positions"]["AAA"]
    eq_open = (1 - 0.20) + (0.20) / 100 * 300                            # cash + position at the open
    room = 0.40 * eq_open - (0.20) / 100 * 300                            # < 1/6: only up to 40%
    assert room < 0 and q["adds"] == 0 and q["invested"] == 0.20


def test_exits_gap_and_ema_break_next_open():
    gap = run(["AAA"], {"AAA": [(100, 99.9, 100), (90, 89, 90)]}, 2)
    assert gap["positions"] == {} and gap["closed"][0]["reason"] == "損切り（窓）" and gap["closed"][0]["exit"] == 90
    ema = run(["AAA"], {"AAA": [(100, 99.9, 100), (99.9, 99.4, 99.5), (80, 79, 79)]}, 3)
    c = ema["closed"][0]
    assert c["reason"] == "安値21EMA割れ（翌始値）" and c["exit"] == 80 and c["exit_day"] == D[32]
    stop = run(["AAA"], {"AAA": [(100, 99.9, 100), (99, 91, 95)]}, 2)
    assert abs(stop["closed"][0]["exit"] - 92) < 1e-9 and stop["closed"][0]["reason"] == "損切り −8%"


def test_incremental_equals_one_shot_and_reruns_are_idempotent():
    paths = {"AAA": [(100, 99.9, 104), (105, 103, 111), (112, 108, 109), (109, 100, 101)],
             "BBB": [(50, 49.9, 51), (51, 50, 52), (52, 40, 41), (41, 40, 40)]}
    f, q, ses = frame(paths), qqq(34, 100), sessions(["AAA", "BBB"])
    once = tp.advance(tp.new_portfolio(S), ses, f, q, D[33], fund=q)
    step = tp.new_portfolio(S)
    for k in range(30, 34):
        step = tp.advance(step, ses, f, q, D[k], fund=q)
    assert json.dumps(step, sort_keys=True) == json.dumps(once, sort_keys=True)
    again = tp.advance(copy.deepcopy(once), ses, f, q, D[33], fund=q)
    assert again == once
    assert tp.advance(copy.deepcopy(once), ses, f[f["date"] > pd.Timestamp(D[31])], q, D[33], fund=q) == once


def test_waits_for_missing_qqq_instead_of_skipping_a_session():
    q = qqq(32)
    q[D[30]] = {"open": None, "close": 100}
    pf = tp.advance(tp.new_portfolio(S), sessions(["AAA"]), frame({"AAA": [(100, 99, 100), (100, 99, 100)]}), q, D[31],
                    fund=qqq(32))
    assert pf["last_day"] == S and pf["waiting"] == D[30] and pf["positions"] == {}


def test_waits_for_missing_sleeve_nav_and_sleeve_moves_with_the_fund():
    f, q = frame({"AAA": [(100, 99.9, 100), (100, 99.9, 100)]}), qqq(32)
    fund = qqq(31)                                     # TQQQ-rule NAV not recorded for D[31] yet
    pf = tp.advance(tp.new_portfolio(S), sessions(["AAA"]), f, q, D[31], fund=fund)
    assert pf["last_day"] == D[30] and pf["waiting"] == D[31]
    fund[D[31]] = {"open": 100, "close": 120}         # sleeve +20% while QQQ is flat
    pf = tp.advance(pf, sessions(["AAA"]), f, q, D[31], fund=fund)
    idle = 1 - 0.20
    assert pf["last_day"] == D[31] and "waiting" not in pf
    assert abs(pf["equity"][-1][1] - (0.20 + idle / 2 * 1.2 + idle / 2)) < 1e-12
    assert pf["equity"][-1][2] == 100                  # benchmark column stays QQQ


def test_published_qqq_pct_comes_from_the_rules_card():
    page = '<div class="card" id="rules-card" data-rule="x"><div class="rreg off">… → 余剰資金のQQQ 100%</div></div>'
    assert tp.published_qqq_pct(page) == 100
    page = '<div class="card" id="rules-card" data-rule="x"><div class="rreg off">… → 余剰資金のTQQQルール枠 50%</div></div>'
    assert tp.published_qqq_pct(page) == 50
    assert tp.published_qqq_pct("<div>余剰資金のQQQ 100%</div>") is None


def test_run_records_portfolio_and_renders_tab(tmp_path: Path):
    page = ('<html><head></head><body><nav><a class="tabx" href="#t-alloc">Positions</a></nav>'
            '<section id="t-alloc"><div class="card" id="mc57-swing-screener" data-regime="on">'
            '<div class="sw-sec"><span>本命<small>n</small></span><button class="cp" data-tk="AAA">c</button></div>'
            '</div></section><section id="t-rules"><div class="card" id="rules-card" data-rule="r">余剰資金のQQQ 50%</div>'
            '</section></body></html>')
    f = frame({"AAA": [(100, 99.9, 110)]})
    market = tmp_path / "data" / "market_inputs.json"
    market.parent.mkdir(parents=True)
    market.write_text(json.dumps({"series": {"QQQ": [{"date": d, **v} for d, v in qqq(31).items()]}}))
    write_fund(tmp_path, 31)
    out = tr.run(page, f[f["date"] <= pd.Timestamp(S)], S, tmp_path)
    led = json.loads((tmp_path / tr.LEDGER).read_text())
    assert led["sessions"][S]["qqq_pct"] == 50 and led["portfolio"]["last_day"] == S
    assert "翌営業日の始値で買うところから始まります" in out
    out = tr.run(out, f, D[30], tmp_path)
    led = json.loads((tmp_path / tr.LEDGER).read_text())
    assert list(led["portfolio"]["positions"]) == ["AAA"] and led["portfolio"]["equity"][-1][0] == D[30]
    assert "保有中" in out and "ルール運用" in out and 'class="tr-spark"' in out
    assert tr.render_only(out, tmp_path) == tr.render_only(tr.render_only(out, tmp_path), tmp_path)
    assert "余剰資金のTQQQルール枠" in out


def test_transition_preserves_old_portfolio_and_starts_at_new_signal():
    old = tp.new_portfolio("2026-10-08")
    old.pop("rule")
    old.pop("sleeve")
    old["equity"] = [["2026-10-08", 0.5, 100]]
    led = {"rule": "swing-v2-max6", "portfolio": old, "sessions": {
        "2026-10-08": {"rule": "swing-v2-max6"}, S: {"rule": tr.RULE_ID}}}
    frozen = copy.deepcopy(old)
    pf = tr.prepare_portfolio(led)
    assert pf["start"] == S and pf["equity"] == [[S, 1.0, None]]
    assert led["portfolio_history"][0]["portfolio"] == frozen
    assert tr.prepare_portfolio(led) is pf and len(led["portfolio_history"]) == 1
    assert led["sessions"]["2026-10-08"]["rule"] == "swing-v2-max6"


def test_frozen_old_session_is_not_relabelled_or_replayed():
    led = tr.new_ledger()
    led["rule"] = "swing-v2-max6"
    led["sessions"] = {S: {"rule": "swing-v2-max6", "best": [], "revisions": 0}}
    page = '<section id="mc57-swing-screener"><div class="sw-sec"><span>本命<small>0</small></span></div></section>'
    tr.record(led, page, S, {})
    assert led["sessions"][S]["rule"] == "swing-v2-max6"
    assert tr.prepare_portfolio(led) is None


def test_legacy_portfolio_cannot_be_advanced_under_new_sizing():
    import pytest
    pf = tp.new_portfolio(S)
    pf.pop("rule")
    with pytest.raises(ValueError, match="Legacy portfolio"):
        tp.advance(pf, {}, frame({"AAA": [(100, 99.9, 100)]}), qqq(31), D[30], fund=qqq(31))


def test_rules_tab_shows_forward_record_above_backtest(tmp_path: Path):
    import rules_tab
    page = ('<html><head></head><body><nav><a class="tabx" href="#t-alloc">Positions</a></nav>'
            '<section id="t-alloc"></section><section id="t-rules"></section></body></html>')
    page = rules_tab.apply(page)
    out = tr.apply(page, None, [], error="broken")
    assert "記録ファイルを読めなかった" in out
    led = tr.new_ledger()
    led["start"] = S
    out = tr.apply(out, led, [])
    assert out.count(f'id="{tr.RULES_BLOCK_ID}"') == 1 and "読めなかった" not in out
    assert out.index(tr.RULES_BLOCK_ID) < out.index("成績（単年・旧6銘柄ルールの過去検証）")
    paths = {"AAA": [(100, 99.9, 104), (105, 103, 111)]}
    led["sessions"] = sessions(["AAA"])
    led["portfolio"] = tp.advance(tp.new_portfolio(S), led["sessions"], frame(paths), qqq(32, 100), D[31], fund=qqq(32))
    out = tr.apply(out, led, [])
    block = out[out.index(tr.RULES_BLOCK_ID):out.index("成績（単年・旧6銘柄ルールの過去検証）")]
    assert "ルール運用" in block and "2026/10" in block and out.count(f'id="{tr.RULES_BLOCK_ID}"') == 1
    assert tr.apply(out, led, []) == out
    assert rules_tab.rule_problems(out, required=("rules-card",)) == []


def test_monthly_returns_chain_month_ends():
    eq = [["2026-01-30", 1.0, 100.0], ["2026-02-10", 1.05, 101.0], ["2026-02-27", 1.10, 102.0],
          ["2026-03-31", 0.99, 99.96]]
    m = tr.monthly(eq)
    assert [x[0] for x in m] == ["2026-02", "2026-03"]
    assert abs(m[0][1] - 0.10) < 1e-12 and abs(m[1][1] - (0.99 / 1.10 - 1)) < 1e-12
    assert abs(m[1][2] - (99.96 / 102 - 1)) < 1e-12


def test_display_preserves_old_results_without_rebuilding(tmp_path: Path):
    page = '<html><head></head><body><nav><a class="tabx" href="#t-alloc">Positions</a></nav><section id="t-alloc"></section><section id="t-rules"></section></body></html>'
    led = tr.new_ledger()
    led["rule"] = "swing-v2-max6"
    old = tp.new_portfolio(S)
    old.pop("rule")
    old.pop("sleeve")
    old["equity"] = [[S, 1, 100], [D[30], 0.5, 100]]
    old["last_day"] = D[30]
    old.pop("max_names")
    led["portfolio"] = old
    tr.save(led, tmp_path / tr.LEDGER)
    before = (tmp_path / tr.LEDGER).read_bytes()
    out = tr.render_only(page, tmp_path)
    assert "旧ルールの保存記録" in out and "計算し直しません" in out
    assert "保有（最大6）" in out and "−50.0%" in out
    assert (tmp_path / tr.LEDGER).read_bytes() == before
    assert tr.display_ledger(led, tmp_path)["portfolio"] == old


def test_six_existing_positions_are_preserved_without_liquidation():
    old = tp.new_portfolio('2026-10-08', legacy_tqqq=True)
    old['positions'] = {f'T{i}': {'shares': i + 1, 'unit': 1 / 6, 'pending_exit': i == 0,
                                'pending_add': 1, 'last': 100} for i in range(6)}
    old['closed'] = [{'t': 'CLOSED', 'pnl': 0.12}]
    before = copy.deepcopy(old)
    led = {'rule': old['rule'], 'portfolio': old, 'sessions': {S: {'rule': tr.RULE_ID}}}
    current = tr.prepare_portfolio(led)
    assert led['portfolio_history'][0]['portfolio'] == before
    assert len(led['portfolio_history'][0]['portfolio']['positions']) == 6
    assert current['positions'] == {} and current['closed'] == []
    assert current['cash'] == 1 and current['equity'] == [[S, 1, None]]
    assert led['allocation_transition']['method'] == 'separate-forward-series'


def test_legacy_tqqq_comparison_retains_six_name_sizing_and_never_saves(tmp_path):
    f = frame({'AAA': [(100, 99.9, 110)]})
    led = tr.new_ledger()
    led['start'], led['sessions'] = S, sessions(['AAA'])
    old = tp.new_portfolio(S, legacy_tqqq=True)
    old.pop('sleeve')
    old['last_day'] = D[30]
    led['portfolio'] = old
    tr.save(led, tmp_path / tr.LEDGER)
    before = (tmp_path / tr.LEDGER).read_bytes()
    (tmp_path / 'work').mkdir()
    f.assign(volume=1e6).to_csv(tmp_path / 'work/ohlcv.csv', index=False)
    (tmp_path / 'latest-manifest.json').write_text(json.dumps({'session_date': D[30]}))
    (tmp_path / 'work/market-inputs-cache.json').write_text(json.dumps(
        {'series': {'QQQ': [{'date': d, **v} for d, v in qqq(31).items()]}}))
    write_fund(tmp_path, 31)
    shown = tr.display_ledger(led, tmp_path)
    assert shown['_pending'] and shown['portfolio'] == old
    comparison = shown['_legacy_tqqq']
    assert comparison['max_names'] == 6
    assert abs(comparison['positions']['AAA']['invested'] - 1 / 6) < 1e-12
    assert '従来表示・参考' in tr.history_html(shown)
    assert (tmp_path / tr.LEDGER).read_bytes() == before


def test_idle_hundred_percent_sleeve_unchanged_at_twenty_percent_stock():
    pf = run(['AAA'], {'AAA': [(100, 99.9, 100)]}, 1, pct=100)
    assert abs(pf['positions']['AAA']['invested'] - 0.20) < 1e-12
    assert abs(pf['qqq_sh'] * 100 - 0.80) < 1e-12 and abs(pf['cash']) < 1e-12


def test_new_series_labels_use_current_start_not_legacy_start():
    led = tr.new_ledger()
    led['start'] = '2026-10-05'
    led['sessions'] = {'2026-10-05': {'rule': 'swing-v2-max6'}, S: {'rule': tr.RULE_ID}}
    led['portfolio'] = tp.new_portfolio(S)
    block = tr.rules_block(led)
    assert S in block and '2026-10-05' not in block
    assert '（1営業日分）' in tr.tab_html(led, [])


def test_published_legacy_snapshot_available_without_cached_prices():
    root = Path(__file__).resolve().parents[1]
    led = tr.display_ledger(tr.load(root / tr.LEDGER), root)
    snapshot = led['_legacy_snapshot']
    assert snapshot['source_commit'] == '9f7aabcd5499e523949e8da7aadb21fa53804ba8'
    assert snapshot['through'] == '2026-10-08'
    assert '−3.6%' in snapshot['html'] and '保有（最大6）' in snapshot['html']
    assert '公開時点表示（保存）' in tr.history_html(led)
