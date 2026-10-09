"""Pinned chart-source replay and one-series continuation, without rewriting history."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconstruct_swing_model as rm
import track_portfolio as tp
import track_record as tr

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / 'tests/fixtures/five-stock-reconstruction.json').read_text())[str(tr.LEDGER)]


def test_pinned_replay_uses_uniform_chart_prices_and_preserves_old_record(tmp_path):
    files=json.loads((ROOT / 'tests/fixtures/five-stock-reconstruction.json').read_text())
    for path, content in files.items():
        target=tmp_path/path; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(content))
    led = fixture(); before = copy.deepcopy(led)
    saved = led['modeled_portfolio']; meta = saved['reconstruction']
    got = rm.replay(tmp_path, led, input_commit=meta['input_commit'], generated_at=meta['generated_at'])
    for p in (got, saved):
        assert p['max_names'] == 5 and p['initial_weight'] == .20
        assert p['last_day'] == '2026-10-08'
        assert list(p['positions']) == ['MRVL', 'AMD', 'CRWD', 'PANW']
        assert p['positions']['CRWD']['entry'] == 278.0
        assert p['positions']['PANW']['entry'] == 412.8
        assert all(x['unit'] == .2 and x['adds'] == 0 for x in p['positions'].values())
        assert p['closed'][0]['t'] == 'INTC' and p['closed'][0]['exit'] == pytest.approx(117.06 * .92)
        assert p['closed'][0]['exit_day'] == '2026-10-08'
        total = p['equity'][-1][1]
        stock = sum(x['shares'] * x['last'] for x in p['positions'].values()) / total
        assert stock == pytest.approx(.808403272041602)
        assert p['cash'] / total == pytest.approx(.191596727958398)
        assert stock + p['cash'] / total == pytest.approx(1)
    assert {k:v for k,v in got.items() if k != 'reconstruction'} == {k:v for k,v in saved.items() if k != 'reconstruction'}
    assert led == before  # replay reads, never rewrites original quantities or frozen signals
    assert led['portfolio']['positions']['CRWD']['entry'] == 278.1099853515625
    assert all(s['rule'] == 'swing-v2-max6' for s in led['sessions'].values())
    for path, expected in got['reconstruction']['inputs'].items():
        assert hashlib.sha256((tmp_path/path).read_bytes()).hexdigest()==expected
    original = {k:v for k,v in led.items() if k != 'modeled_portfolio'}
    assert hashlib.sha256((json.dumps(original, ensure_ascii=False, indent=1)+'\n').encode()).hexdigest() == meta['inputs'][str(tr.LEDGER)]


def test_model_is_only_current_series_and_same_session_rerun_is_idempotent():
    led = fixture(); pf = tp.current_portfolio(led); old = copy.deepcopy(led['portfolio'])
    assert pf == led['modeled_portfolio'] and pf != old
    assert 'inventory_origin' not in pf
    before = copy.deepcopy(pf)
    assert tp.advance(pf, led['sessions'], pd.DataFrame(), {}, '2026-10-08', fund={}) == before
    html = tr.tab_html(tr.display_ledger(led, ROOT), [])
    assert '新5銘柄ルールで再計算した現在の保有モデル' in html
    assert '当時の運用実績ではありません' in html
    assert 'tr-forward' not in html
    assert '旧ルールの保存記録' in html
    rules = tr.rules_block(tr.display_ledger(led, ROOT))
    assert '改訂済み公開チャートによる再計算' in rules
    assert '開始待ち' not in rules
    assert led['portfolio'] == old


def test_reconstruction_refuses_incomplete_input(tmp_path):
    led=fixture()
    (tmp_path/'chart-data').mkdir()
    (tmp_path/'chart-data/index.json').write_text(json.dumps({'session_date':'2026-10-07'}))
    with pytest.raises(ValueError, match='cutoff'):
        rm.replay(tmp_path, led, input_commit='a'*40, generated_at='2026-10-09T00:00:00Z')


def test_daily_refresh_advances_only_the_model_without_resetting_original(tmp_path, monkeypatch):
    led=fixture(); original=copy.deepcopy(led['portfolio']); model=copy.deepcopy(led['modeled_portfolio'])
    tr.save(led,tmp_path/tr.LEDGER)
    dates=pd.bdate_range(end='2026-10-09',periods=35)
    rows=[]
    for t in ['MRVL','AMD','CRWD','PANW','DELL','LITE']:
        price=model['positions'][t]['last'] if t in model['positions'] else 100.
        rows += [(t,d,price,price,price,price,1000) for d in dates]
    frame=pd.DataFrame(rows,columns=['ticker','date','open','high','low','close','volume'])
    q={'2026-10-08':{'open':750.,'close':747.58},'2026-10-09':{'open':750.,'close':750.}}
    monkeypatch.setattr(tr,'record',lambda *a,**k:None)
    monkeypatch.setattr(tr,'advance_all',lambda *a,**k:None)
    monkeypatch.setattr(tr,'qqq_bars',lambda *a,**k:q)
    monkeypatch.setattr(tr.tqqq_rule,'fund_bars',lambda *a,**k:{'2026-10-09':{'open':1.,'close':1.}})
    monkeypatch.setattr(tr,'apply',lambda *a,**k:'rendered')
    assert tr.run('',frame,'2026-10-09',tmp_path)=='rendered'
    result=tr.load(tmp_path/tr.LEDGER)
    assert result['portfolio']==original
    assert 'current_portfolio' not in result and 'portfolio_history' not in result
    got=result['modeled_portfolio']
    assert got['last_day']=='2026-10-09' and got['equity'][:-1]==model['equity']
    assert got['reconstruction']==model['reconstruction']
    assert len(got['positions'])==5 and 'DELL' in got['positions'] and 'LITE' not in got['positions']
    assert got['positions']['DELL']['unit']==pytest.approx(got['equity'][-1][1]*.20)
    assert got['positions']['MRVL']['shares']==model['positions']['MRVL']['shares']
    before=copy.deepcopy(result)
    tr.run('',frame,'2026-10-09',tmp_path)
    assert tr.load(tmp_path/tr.LEDGER)==before


@pytest.mark.parametrize('defect', ['null', 'duplicate', 'short-history'])
def test_reconstruction_rejects_unusable_chart_data(tmp_path, defect):
    files=json.loads((ROOT / 'tests/fixtures/five-stock-reconstruction.json').read_text())
    i=files['chart-data/index.json']['ticker_to_shard']['MRVL']
    bars=files[f'chart-data/shard-{i:02d}.json']['MRVL']
    if defect=='null': bars[-1][3]=None
    elif defect=='duplicate': bars.append(bars[-1])
    else: files[f'chart-data/shard-{i:02d}.json']['MRVL']=bars[-4:]
    for path,content in files.items():
        out=tmp_path/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(content))
    with pytest.raises(ValueError,match='OHLC|Duplicate|EMA'):
        rm.replay(tmp_path, fixture(), input_commit='a'*40, generated_at='2026-10-09T00:00:00Z')
