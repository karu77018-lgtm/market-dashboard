from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import market_history as mh
import market_internals_ui as ui
import refresh_mc57


def fixture_prices(n=3000):
    dates=pd.bdate_range('2014-01-01',periods=n)
    syms=list(dict.fromkeys([*mh.SYMBOLS,*refresh_mc57.MC57_ETFS]))
    return pd.DataFrame({k:100*np.exp(np.arange(n)*(.00015+i*.000009)+.08*np.sin(np.arange(n)/41+i)) for i,k in enumerate(syms)},index=dates)


def test_mc57_formula_and_current_unchanged_and_all_windows(tmp_path):
    p=fixture_prices(4100)[refresh_mc57.MC57_ETFS];target=p.index[-1].strftime('%Y-%m-%d')
    # Execute pre-change function from immutable git baseline, not a mirror of new code.
    spec=importlib.util.spec_from_file_location('mc57_reference',ROOT/'tests/fixtures/mc57_reference.py')
    reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    before=reference.compute_mc57(p,target,'fixture');after=refresh_mc57.compute_mc57(p,target,'fixture',history_output=tmp_path/'full.json')
    assert after==before
    full=json.loads((tmp_path/'full.json').read_text());assert len(full['history'])==2520
    s=pd.Series({pd.Timestamp(r['date']):r['mc57'] for r in full['history']})
    files=mh.export_windows(tmp_path,'mc57',{'MC57':s},target)
    for win,n in mh.WINDOWS.items():
        j=json.loads((tmp_path/files[win]).read_text());assert len(j['dates'])==n
        assert j['dates'][-1]==target;assert j['series']['MC57'][-1]==after['mc57']


def test_group_partition_and_raw_reconstruction():
    keys=sum(mh.GROUPS.values(),[])
    assert len(keys)==len(set(keys))==12;assert set(keys)==set(refresh_mc57.METRIC_NAMES)
    p=fixture_prices(1100)[refresh_mc57.MC57_ETFS];j=refresh_mc57.compute_mc57(p,str(p.index[-1].date()),'fixture')
    assert np.mean(list(j['metric_scores'].values()))==j['raw']
    assert '4本柱' not in ui.breakdown_panel(j)
    assert '3<sup>−z</sup>' in ui.breakdown_panel(j)


def test_nqsar_blue_does_not_affect_internal_narrative():
    mc={'mc57':22,'history':[]};b={'p50':35,'net':-12}
    summary={'indices':{'QQQ':{'63':10}},'spread':{'QQQ-QQQE':{'63':5}},'leading':['MAG7','Mega']}
    text=ui.comment_card(mc,b,summary)
    assert '市場内部は弱い' in text;assert '細い相場' in text
    assert not any(x in text for x in ['Blue','Green','Yellow','Red','地合いは青','積極的に拾う'])
    module=type('Module',(),{})()
    # SAR tuple is accepted for the frozen signature but never read.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);(root/'data').mkdir();(root/'data/mc57.json').write_text(json.dumps(mc));ui.install(module,root,root/'data')
        assert module._market_comment({}, {}, ('Blue','estimate'), {'pa50':35})==module._market_comment({}, {}, ('Red','estimate'), {'pa50':35})


def test_leadership_daily_equal_weight_adjusted_returns_and_gaps():
    f=fixture_prices();s=mh.mag7_index(f)
    assert s.iloc[0]==100
    expected=(1+f[mh.MAG7].pct_change(fill_method=None).iloc[1:].mean(axis=1)).prod()*100
    assert np.isclose(s.iloc[-1],expected)
    sizes,pairs,ratios,summary=mh.package_series(f,str(f.index[-1].date()))
    assert set(sizes)=={'Small','Mid','Large','Mega','MAG7'}
    assert set(pairs)=={'SPY','RSP','QQQ','QQQE'};assert set(ratios)=={'SPY/RSP','QQQ/QQQE'}
    broken=f.copy();broken.loc[f.index[100],'NVDA']=np.nan
    assert mh.mag7_index(broken).iloc[100:].isna().all()


def test_gics_unique_ranks_and_top_bottom_from_same_current():
    f=fixture_prices()
    for h in (21,63,126):
        rows=mh.rank_history(f,h)
        assert set(rows[-1]['ranks'])==set(mh.GICS)
        assert sorted(rows[-1]['ranks'].values())==list(range(1,12))
        order=sorted(mh.GICS,key=lambda k:(-rows[-1]['rs'][k],k))
        assert [rows[-1]['ranks'][k] for k in order]==list(range(1,12))
        assert set(k for k,v in rows[-1]['ranks'].items() if v<=3)==set(order[:3])
        assert set(k for k,v in rows[-1]['ranks'].items() if v>=9)==set(order[-3:])
    f.loc[f.index[-1],'RSPR']=np.nan
    assert mh.rank_history(f,63)[-1]['date']!=str(f.index[-1].date())


def test_exports_lazy_windows_missing_not_zero(tmp_path):
    f=fixture_prices(2700);target=str(f.index[-1].date())
    j={'series':{k:mh.rows(f[k]) for k in f},'session_date':target}
    mh.write(tmp_path/'work/market-history-prices.json',j)
    result=mh.build(tmp_path,target,offline=True)
    for key in ('leadership','concentration','relative','indices'):
        for win in mh.WINDOWS:
            data=json.loads((tmp_path/'market-history'/result['files'][key][win]).read_text())
            assert data['dates'][-1]==target
    for h in ('21','63','126'):
        for win in mh.WINDOWS:
            data=json.loads((tmp_path/'market-history'/result['files']['gics11'][h][win]).read_text())
            assert data['current']['date']==target
            assert data['previous']['date']==str(f.index[-21].date())
    f.loc[f.index[-1],'XLG']=np.nan
    files=mh.export_windows(tmp_path,'missing',{'Mega':f.XLG},target)
    data=json.loads((tmp_path/files['2y']).read_text());assert data['series']['Mega'][-1] is None
    assert data['availability']['Mega']['status']!='READY'


def test_persistent_ui_preserves_styles_tabs_and_breadth_policy(tmp_path):
    mc={'mc57':22.356,'session_date':'2026-09-29','metric_scores':{k:30. for k in refresh_mc57.METRIC_NAMES},'history':[]}
    src='''<!DOCTYPE html><html><head><style>.card{background:#f2f1ee;border-radius:10px}</style></head><body>
    <div class="sar sar-blue"><span id="sarCol">Blue</span><div class="lab">トレンド判定</div></div>
    <section id="t-market"><div class="banner"><div class="lab">マーケットステータス（地合いスコア）</div><div id="mri-bd">旧4本柱</div></div>
    <div class="card cmt mkt20">地合いは青</div><div class="card"><h2>ブレッドス推移</h2><div class="chart"><svg></svg></div></div></section>
    <section id="t-rotation"><div id="old-rotation">既存</div></section><section id="t-rules">rules</section><script>window.CALC={"color":"Blue"};</script></body></html>'''
    out=ui.apply_html(src,tmp_path,mc=mc,summary={},breadth={'p50':35})
    soup=BeautifulSoup(out,'html.parser');before=BeautifulSoup(src,'html.parser')
    assert soup.style.string==before.style.string
    assert soup.select_one('#old-rotation').get_text()=='既存'
    assert soup.select_one('#sarCol').get_text()=='Blue'
    assert 'NQ運用判定' in out;assert '地合いは青' not in out;assert '旧4本柱' not in out
    assert soup.select_one('[data-window="2y"]').get('aria-pressed')=='true'
    assert soup.select_one('[data-history-key="unavailable"] [data-window="5y"]').has_attr('disabled')
    assert soup.select_one('#market-history-config').string.count('history')==0
    assert 'window.CALC={"color":"Blue"};' in out
    assert ui.apply_html(out,tmp_path,mc=mc)==out
