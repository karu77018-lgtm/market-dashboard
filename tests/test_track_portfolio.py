from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import track_portfolio as tp  # noqa: E402
import track_record as tr  # noqa: E402

D = [d.date().isoformat() for d in pd.bdate_range(end=tp.EFFECTIVE_DATE, periods=30).append(
    pd.bdate_range(pd.Timestamp(tp.EFFECTIVE_DATE) + pd.offsets.BDay(1), periods=30))]
W, N = tp.INITIAL_WEIGHT, tp.MAX_NAMES
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


def test_entry_next_open_first_weight_and_idle_money_in_qqq():
    pf = run(["AAA"], {"AAA": [(100, 99.9, 110)]}, 1)
    p = pf["positions"]["AAA"]
    assert p["entry_day"] == D[30] and p["entry"] == 100 and abs(p["invested"] - W) < 1e-12
    idle = 1 - W
    assert abs(pf["qqq_sh"] * 100 - idle / 2) < 1e-12 and abs(pf["cash"] - idle / 2) < 1e-12
    assert abs(pf["equity"][-1][1] - (1 + W * 0.10)) < 1e-12       # AAA +10%, QQQ flat
    assert p["triggered"] == [0] and p["pending_add"] == 1


def test_slots_ranked_by_189_day_return():
    names = [f"T{k}" for k in range(N + 1)]
    r189 = {t: k / 10 for k, t in enumerate(names)}                        # strongest last, T0 weakest
    pf = run(names, {t: [(100, 99.9, 100)] for t in names}, 1, r189=r189)
    # v6: stocks stop at STOCK_CAP of equity -> four full names, the fifth gets what is left
    full = int(tp.STOCK_CAP / W + 1e-9)
    held = {f"T{k}" for k in range(N + 1 - full - 1, N + 1)}
    assert set(pf["positions"]) == held
    stock = sum(p["shares"] * 100 for p in pf["positions"].values())
    assert abs(stock - tp.STOCK_CAP) < 1e-9
    partial = pf["positions"][f"T{N - full}"]
    assert abs(partial["shares"] * 100 - (tp.STOCK_CAP - full * W)) < 1e-9
    cap = f"株が上限の{tp.STOCK_CAP:.0%}"
    assert [x["t"] for x in pf["skipped"]] == [f"T{k}" for k in range(N - full - 1, -1, -1)]
    assert all(x["why"] == cap for x in pf["skipped"])


def test_regime_off_buys_nothing_and_unknown_pct_keeps_last():
    pf = run(["AAA"], {"AAA": [(100, 99.9, 100)]}, 1, regime="off", pct=None)
    # after the v6 cutover an unpublished share moves the v5 normal 50% to the v6 normal 60%
    assert pf["positions"] == {} and abs(pf["qqq_sh"] * 100 - tp.SLEEVE_NORMAL / 100) < 1e-12
    pf = run(["AAA"], {"AAA": [(100, 99.9, 100)]}, 1, regime="off", pct=100)
    assert abs(pf["qqq_sh"] * 100 - 1.0) < 1e-12


def test_same_amount_adds_never_exceed_forty_percent():
    up = [(100, 99.9, 110), (111, 110.5, 125), (126, 125, 160), (160, 159, 170)]
    pf = run(["AAA"], {"AAA": up}, 4, pct=0)
    p = pf["positions"]["AAA"]
    first = W / 100 + W / 111                                            # same-amount add at 111 (below 40%)
    eq_open = (1 - 2 * W) + first * 126
    second = max(0, min(W, 0.40 * eq_open - first * 126))                # the 40% cap binds at 126
    assert p["adds"] == 2 and second < W and abs(p["shares"] - (first + second / 126)) < 1e-12
    big = run(["AAA"], {"AAA": [(100, 99.9, 110), (300, 299, 300)]}, 2, pct=0)
    q = big["positions"]["AAA"]
    eq_open = (1 - W) + W / 100 * 300                                    # cash + position at the open
    room = 0.40 * eq_open - W / 100 * 300
    assert room < W                                                      # only up to 40%, never a full add
    assert abs(q["invested"] - (W + max(0.0, room))) < 1e-12 and q["adds"] == (1 if room > 0 else 0)


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
    idle = 1 - W
    assert pf["last_day"] == D[31] and "waiting" not in pf
    assert abs(pf["equity"][-1][1] - (W + idle / 2 * 1.2 + idle / 2)) < 1e-12
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
    assert out.index(tr.RULES_BLOCK_ID) < out.index('<div class="rh">成績（単年）</div>')
    paths = {"AAA": [(100, 99.9, 104), (105, 103, 111)]}
    led["sessions"] = sessions(["AAA"])
    led["portfolio"] = tp.advance(tp.new_portfolio(S), led["sessions"], frame(paths), qqq(32, 100), D[31], fund=qqq(32))
    out = tr.apply(out, led, [])
    block = out[out.index(tr.RULES_BLOCK_ID):out.index('<div class="rh">成績（単年）</div>')]
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
    assert "−50.0%" in out
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


def test_display_never_rebuilds_or_adds_comparison_series(tmp_path):
    led = tr.new_ledger()
    led['start'], led['sessions'] = S, sessions(['AAA'])
    old = tp.new_portfolio(S, legacy_tqqq=True)
    old.pop('sleeve')
    old['last_day'] = D[30]
    led['portfolio'] = old
    tr.save(led, tmp_path / tr.LEDGER)
    before = (tmp_path / tr.LEDGER).read_bytes()
    shown = tr.display_ledger(led, tmp_path)
    assert shown['_pending'] and shown['portfolio'] == old
    assert '_legacy_tqqq' not in shown and '_legacy_snapshot' not in shown
    assert (tmp_path / tr.LEDGER).read_bytes() == before


def test_idle_hundred_percent_sleeve_holds_all_idle_money():
    pf = run(['AAA'], {'AAA': [(100, 99.9, 100)]}, 1, pct=100)
    assert abs(pf['positions']['AAA']['invested'] - W) < 1e-12
    assert abs(pf['qqq_sh'] * 100 - (1 - W)) < 1e-12 and abs(pf['cash']) < 1e-12


def test_new_series_labels_use_current_start_not_legacy_start():
    led = tr.new_ledger()
    led['start'] = '2026-10-05'
    led['sessions'] = {'2026-10-05': {'rule': 'swing-v2-max6'}, S: {'rule': tr.RULE_ID}}
    led['portfolio'] = tp.new_portfolio(S)
    block = tr.rules_block(led)
    assert S in block and '2026-10-05' not in block


def test_published_record_shows_one_current_series_and_old_rules_folded():
    root = Path(__file__).resolve().parents[1]
    led = tr.display_ledger(tr.load(root / tr.LEDGER), root)
    html = tr.tab_html(led, [])
    assert html.count('<div class="tr-grid">') == 2 + len(led.get('portfolio_history', [])) + (1 if led.get('portfolio') else 0)
    assert '過去検証（' in html and '設定の比較' in html and '翌営業日の寄りで売買' in html
    assert '旧ルールの記録（参考）' in html and 'SHA-256' not in html and '入力コミット' not in html


def test_v5_model_continues_under_v6_without_selling():
    """A running v5 model keeps its holdings; only orders from v6 publications are capped."""
    pf = tp.new_portfolio(D[25])
    pf["rule"] = tp.PREVIOUS_RULE_IDS[0]
    pf["positions"] = {f"H{i}": {"signal": D[25], "entry_day": D[26], "entry": 100.0, "stop": 92.0,
                                 "shares": W / 100, "unit": W, "invested": W, "adds": 0, "triggered": [],
                                 "pending_add": 0, "pending_exit": False, "ema": 90.0, "last": 100.0, "days": 1}
                       for i in range(4)}
    pf["cash"], pf["qqq_sh"], pf["last_day"] = 1 - 4 * W, 0.0, D[29]
    pf5 = copy.deepcopy(pf)
    pf5["positions"]["H4"] = dict(pf5["positions"]["H0"])
    pf5["cash"] -= W
    bars = frame({**{f"H{i}": [(100, 99, 100)] for i in range(4)}, "NEW": [(100, 99, 100)]})
    ses = {S: {"best": [{"t": "NEW", "r189": 1.0}], "regime": "on", "qqq_pct": 60}}
    q = {d: {"open": 100.0, "close": 100.0} for d in D}
    fund = {d: {"open": 1.0, "close": 1.0} for d in D}
    out = tp.advance(pf, ses, bars, q, D[30], fund=fund)
    assert out["rule"] == tp.RULE_ID and out["rule_changes"][0]["from"] == tp.PREVIOUS_RULE_IDS[0]
    assert len([t for t in out["positions"] if t.startswith("H")]) == 4          # nothing sold
    new = out["positions"]["NEW"]["shares"] * 100
    assert abs(new - (tp.STOCK_CAP - 4 * W)) < 1e-9 and out["qqq_pct"] == 60     # filled up to the cap only
    assert abs(out["positions"]["NEW"]["unit"] - (tp.STOCK_CAP - 4 * W)) < 1e-9     # adds repeat the smaller buy
    full = tp.advance(pf5, ses, bars, q, D[30], fund=fund)                      # already above 80%: hold, no buy
    assert len(full["positions"]) == 5 and full["skipped"][-1]["why"] == f"株が上限の{tp.STOCK_CAP:.0%}"


def test_missing_share_after_v6_falls_back_to_normal_and_v5_portfolio_is_carried():
    pf = tp.new_portfolio(S)
    pf["qqq_pct"] = 100                                    # a weak-health day before the outage
    q = qqq(31)
    out = tp.advance(pf, sessions(["AAA"], pct=None), frame({"AAA": [(100, 99.9, 100)]}), q, D[30], fund=q)
    assert out["qqq_pct"] == tp.SLEEVE_NORMAL
    v5 = tp.new_portfolio(S)
    v5["rule"] = tp.PREVIOUS_RULE_IDS[0]
    led = {"rule": v5["rule"], "portfolio": v5, "sessions": {S: {"rule": tr.RULE_ID}}}
    assert tr.prepare_portfolio(led) is v5 and "portfolio_history" not in led


def test_v5_retag_only_when_a_session_advances():
    v5 = tp.new_portfolio(S)
    v5["rule"] = tp.PREVIOUS_RULE_IDS[0]
    before = copy.deepcopy(v5)
    q = qqq(30)                                            # nothing after S
    assert tp.advance(v5, sessions(["AAA"]), frame({"AAA": []}), q, S, fund=q) == before


def test_carried_v5_portfolio_is_labeled_in_both_views():
    v5 = tp.new_portfolio("2026-10-05")
    v5["rule"] = tp.PREVIOUS_RULE_IDS[0]
    v5["equity"] = [["2026-10-05", 1.0, 100], ["2026-10-06", 1.01, 100]]
    led = {**tr.new_ledger(), "portfolio": v5, "sessions": {}}
    html = tr.current_inventory_html(led)
    assert "旧ルール（株の上限なし・余剰資金の枠50%）" in html
    assert "旧ルール（株の上限なし・余剰資金の枠50%）" in tr.rules_block(led)


def test_v5_retag_waits_for_a_valid_session():
    v5 = tp.new_portfolio(S)
    v5["rule"] = tp.PREVIOUS_RULE_IDS[0]
    q = qqq(31)
    q[D[30]] = {"open": None, "close": 100}               # newer date, unusable bar
    out = tp.advance(v5, sessions(["AAA"]), frame({"AAA": [(100, 99, 100)]}), q, D[30], fund=qqq(31))
    assert out["rule"] == tp.PREVIOUS_RULE_IDS[0] and "rule_changes" not in out and out["waiting"] == D[30]


def test_segment_note_only_for_carried_series():
    old = tp.new_portfolio("2026-10-05", legacy_tqqq=True)
    assert tr._segment_note(old) == ""
    v5 = tp.new_portfolio("2026-10-05")
    v5["rule"] = tp.PREVIOUS_RULE_IDS[0]
    assert "旧ルール" in tr._segment_note(v5)
