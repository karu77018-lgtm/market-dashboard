from __future__ import annotations
import copy
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import track_portfolio as tp
import track_record as tr

D = [d.date().isoformat() for d in pd.bdate_range(end='2026-10-09', periods=34)]


def inputs(names, gaps=()):
    rows = [(t, pd.Timestamp(d), 90.0 if d == D[-1] and t in gaps else 100.0,
             101.0, 89.0 if d == D[-1] and t in gaps else 99.9,
             90.0 if d == D[-1] and t in gaps else 100.0)
            for t in names for d in D]
    return pd.DataFrame(rows, columns=['ticker', 'date', 'open', 'high', 'low', 'close'])


def signal(names):
    return {'regime': 'on', 'qqq_pct': 50, 'best': [{'t': t, 'r189': 1} for t in names]}


def old_six():
    names = [f'T{i}' for i in range(6)]
    q = {d: {'open': 100.0, 'close': 100.0} for d in D}
    old = tp.advance(tp.new_portfolio(D[-4], legacy_tqqq=True),
                     {D[-4]: signal(names)}, inputs(names), q, D[-2], fund=q)
    return old, names, q


def test_six_carried_names_are_not_sold_or_resized_and_new_entry_waits():
    old, names, q = old_six()
    saved = copy.deepcopy(old)
    cur = tp.current_portfolio({'rule': old['rule'], 'portfolio': old})
    assert cur['positions'] == old['positions'] and cur['equity'] == old['equity']
    tp.advance(cur, {D[-2]: signal(['NEW'])}, inputs(names + ['NEW']), q, D[-1], fund=q)
    assert len(cur['positions']) == 6 and cur['closed'] == []
    assert cur['skipped'][-1]['why'] == '5銘柄で満杯'
    assert all(p['unit'] == 1 / 6 for p in cur['positions'].values())
    assert old == saved


def test_existing_exits_free_one_twenty_percent_slot_without_reweighting_others():
    old, names, q = old_six()
    cur = tp.current_portfolio({'portfolio': old})
    tp.advance(cur, {D[-2]: signal(['NEW', 'OTHER'])}, inputs(names + ['NEW', 'OTHER'], ['T0', 'T1']),
               q, D[-1], fund=q)
    assert len(cur['positions']) == 5 and len(cur['closed']) == 2
    equity_open = 1 - 2 * (1 / 6) * .10
    assert abs(cur['positions']['NEW']['unit'] - equity_open * .20) < 1e-12
    assert cur['positions']['T2']['shares'] == old['positions']['T2']['shares']
    assert cur['positions']['T2']['unit'] == old['positions']['T2']['unit']
    assert cur['skipped'][-1]['t'] == 'OTHER'


def test_qqq_conversion_waits_for_quotes_and_preserves_value_at_same_future_open():
    old = tp.new_portfolio(D[-2], legacy_tqqq=True)
    old.pop('sleeve'); old.pop('rule')
    old.update(cash=.7, qqq_sh=.003, equity=[[D[-3], 1, 100], [D[-2], 1, 100]])
    ledger = {'rule': 'swing-v2-max6', 'portfolio': old}
    cur = tp.current_portfolio(ledger)
    q = {D[-2]: {'open': 100, 'close': 100}, D[-1]: {'open': 110, 'close': 110}}
    frame = inputs(['AAA'])
    tp.advance(cur, {}, frame, q, D[-1], fund={})
    assert cur['waiting'] == D[-1] and cur['sleeve'] == 'legacy-qqq'
    assert cur['qqq_sh'] == .003 and cur['equity'] == old['equity']
    tp.advance(cur, {}, frame, q, D[-1], fund={D[-1]: {'open': 2, 'close': 2}})
    assert cur['sleeve_conversion']['day'] == '2026-10-09'
    assert abs(cur['sleeve_conversion']['value_at_open'] - .33) < 1e-12
    assert abs(cur['equity'][-1][1] - 1.03) < 1e-12
    assert cur['equity'][:-1] == old['equity']
    once = copy.deepcopy(cur)
    tp.advance(cur, {}, frame, q, D[-1], fund={})
    assert cur == once


def test_lagged_pre_cutover_sessions_keep_old_sizing_and_qqq():
    old = tp.new_portfolio(D[-4], legacy_tqqq=True)
    old.pop('rule'); old.pop('sleeve')
    cur = tp.current_portfolio({'rule': 'swing-v2-max6', 'portfolio': old})
    names = [f'T{i}' for i in range(6)]
    q = {d: {'open': 100, 'close': 100} for d in D}
    tp.advance(cur, {D[-4]: signal(names)}, inputs(names), q, D[-2], fund={})
    assert len(cur['positions']) == 6
    assert all(p['unit'] == 1 / 6 for p in cur['positions'].values())
    assert cur['sleeve'] == 'legacy-qqq' and 'sleeve_conversion' not in cur
    assert cur['last_day'] == '2026-10-08'


def test_archived_origin_survives_independent_forward_series():
    old, _, _ = old_six(); old.pop('rule')
    ledger = {'rule': tr.RULE_ID, 'portfolio': tp.new_portfolio('2026-10-09'),
              'portfolio_history': [{'rule': 'swing-v2-max6', 'portfolio': old}]}
    current = tp.current_portfolio(ledger)
    assert current['inventory_origin']['rule'] == 'swing-v2-max6'
    assert len(current['positions']) == 6
    assert current['start'] == old['start'] and current['equity'] == old['equity']
    assert ledger['portfolio']['positions'] == {}
    assert '新5銘柄だけの成績ではありません' in tr.current_inventory_html(ledger)
