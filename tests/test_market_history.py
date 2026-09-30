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


def test_legacy_spark_dates_match_plotted_observations(tmp_path):
    import ast
    from types import SimpleNamespace
    # Execute the recovered original function, preserve its SVG byte for byte.
    import base64,lzma,tarfile
    with tarfile.open(ROOT/'bootstrap/recovery-assets.tar.xz') as tar:
        parts=sorted(m.name for m in tar.getmembers() if '.py.lzma.b85.part' in m.name)
        source=lzma.decompress(base64.b85decode(''.join(tar.extractfile(p).read().decode().strip() for p in parts).encode())).decode()
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_spark')
    namespace={'pd':pd,'_SPARK_SEQ':0};exec(compile(ast.Module(body=[fn],type_ignores=[]),'original-spark','exec'),namespace)
    module=SimpleNamespace(_spark=namespace['_spark'])
    data=tmp_path/'data';data.mkdir();(data/'mc57.json').write_text(json.dumps({'session_date':'2026-09-29'}))
    values=[(d.date(),float(i)) for i,d in enumerate(pd.bdate_range('2026-01-01','2026-10-01'))]
    original=module._spark(values,'2026-09-29',60)
    namespace['_SPARK_SEQ']=0
    ui.install(module,tmp_path,data)
    result=module._spark(values,'2026-09-29',60)
    assert result.startswith(original)
    soup=BeautifulSoup(result,'html.parser'); labels=[x.get_text() for x in soup.select('.mh-spark-axis span')]
    plotted=[d for d,v in values if d<=pd.Timestamp('2026-09-29').date()][-60:]
    assert labels==[pd.Timestamp(plotted[round((len(plotted)-1)*p)]).strftime('%y/%m/%d') for p in (0,.5,1)]
    assert module._spark(values[:5])==''


def fixture_prices(n=3000):
    dates=pd.bdate_range('2014-01-01',periods=n)
    syms=list(dict.fromkeys([*mh.SYMBOLS,*refresh_mc57.MC57_ETFS]))
    return pd.DataFrame({k:100*np.exp(np.arange(n)*(.00015+i*.000009)+.08*np.sin(np.arange(n)/41+i)) for i,k in enumerate(syms)},index=dates)


def test_long_yahoo_empty_response_retries_real_current_data(tmp_path,monkeypatch):
    monkeypatch.setattr(mh,'SYMBOLS',['SPY']);monkeypatch.setattr(mh.time,'sleep',lambda n:None)
    dates=pd.bdate_range('2025-01-01','2026-09-30')
    frame=pd.DataFrame({'Adj Close':np.arange(len(dates))+100.},index=dates)
    calls=[]
    def download(*args,**kwargs):
        calls.append(kwargs);return pd.DataFrame() if len(calls)==1 else frame
    monkeypatch.setattr(mh.yf,'download',download)
    actual,errors=mh.acquire('2026-09-30',tmp_path/'prices.json')
    assert len(calls)==2 and not errors
    assert actual.loc[pd.Timestamp('2026-09-30'),'SPY']==frame['Adj Close'].iloc[-1]


def test_failed_adjustment_refetch_keeps_dated_cache_without_splicing(tmp_path,monkeypatch):
    monkeypatch.setattr(mh,'SYMBOLS',['SPY']);monkeypatch.setattr(mh.time,'sleep',lambda n:None)
    dates=pd.bdate_range('2025-01-01','2026-09-29');old=pd.Series(100.,index=dates)
    cache=tmp_path/'prices.json';mh.write(cache,{'series':{'SPY':mh.rows(old)}})
    revised=pd.DataFrame({'Adj Close':[50.,51.]},index=pd.to_datetime(['2026-09-29','2026-09-30']))
    calls=[]
    def download(*args,**kwargs):
        calls.append(kwargs);return revised if len(calls)==1 else pd.DataFrame()
    monkeypatch.setattr(mh.yf,'download',download)
    actual,errors=mh.acquire('2026-09-30',cache)
    assert len(calls)==4 and errors['SPY']=='Yahoo history unavailable'
    pd.testing.assert_series_equal(actual['SPY'],old.rename('SPY'),check_freq=False)
    assert pd.Timestamp('2026-09-30') not in actual.index


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


def test_rank_flow_missing_twenty_session_day_does_not_move_date(tmp_path):
    f=fixture_prices(700);target=str(f.index[-1].date())
    f.loc[f.index[-21],'RSPR']=np.nan
    mh.write(tmp_path/'work/market-history-prices.json',{'series':{k:mh.rows(f[k]) for k in f}})
    result=mh.build(tmp_path,target,offline=True)
    for h in ('21','63','126'):
        j=json.loads((tmp_path/'market-history'/result['files']['gics11'][h]['2y']).read_text())
        assert j['previous'] is None
        assert j['source_bars']<504
        assert j['status']=='INSUFFICIENT_HISTORY'


def test_unavailable_windows_not_offered_but_complete_windows_work(tmp_path):
    f=fixture_prices(2700);target=str(f.index[-1].date())
    f.loc[f.index[:700],'RSPC']=np.nan
    mh.write(tmp_path/'work/market-history-prices.json',{'series':{k:mh.rows(f[k]) for k in f}})
    mh.build(tmp_path,target,offline=True)
    mc={'session_date':target,'mc57':22,'history':[],'metric_scores':{}}
    src='<html><head></head><body><section id="t-market"><div class="card"><h2>ブレッドス推移</h2><div class="chart"><svg></svg></div></div></section><section id="t-rotation"></section></body></html>'
    soup=BeautifulSoup(ui.apply_html(src,tmp_path,mc=mc),'html.parser')
    assert not soup.select('.mh-tools button:disabled')
    assert soup.select_one('[data-history-key="leadership"] [data-window="10y"]')
    assert soup.select_one('[data-history-key="gics11"] [data-window="2y"]')
    assert soup.select_one('[data-history-key="gics11"] [data-window="5y"]')
    assert not soup.select_one('[data-history-key="gics11"] [data-window="10y"]')
    assert not soup.select_one('[data-history-key="unavailable"]')
    assert not soup.select_one('[data-history-key="mc57-group-0"]')


def test_vix_native_state_unchanged_and_full_daily_history_exported(tmp_path):
    import base64,lzma,tarfile,hashlib
    from build_exact_source_mc57_clone import SOURCE_SHA256
    # Real immutable native model, not a mirrored implementation or network fixture.
    with tarfile.open(ROOT/'bootstrap/recovery-assets.tar.xz') as archive:
        parts=sorted(m.name for m in archive.getmembers() if '.py.lzma.b85.part' in m.name)
        encoded=''.join(archive.extractfile(p).read().decode().strip() for p in parts)
    raw=lzma.decompress(base64.b85decode(encoded.encode()))
    assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA256
    path=tmp_path/'native.py';path.write_bytes(raw)
    spec=importlib.util.spec_from_file_location('native_vix_test',path)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    dates=pd.bdate_range('1990-01-01','2026-09-29')
    highs=15+np.abs(np.random.default_rng(21).normal(0,4,len(dates)))
    macro={'^VIX':pd.DataFrame({'Close':highs*.97,'High':highs},index=dates)}
    before=native.build_vix_cycle(macro,lookback=77)
    full=native.build_vix_cycle(macro,lookback=2520)
    mh.write(tmp_path/'data/mc57.json',{'session_date':'2026-09-29','mc57':22})
    mh.write(tmp_path/'market-history/index.json',{'files':{},'session_date':'2026-09-29'})
    ui.install(native,tmp_path,tmp_path/'data')
    after=native.build_vix_cycle(macro,lookback=77)
    assert {k:v for k,v in after.items() if k!='windows'}=={k:v for k,v in before.items() if k!='windows'}
    native._vix_cycle_card(after)
    index=json.loads((tmp_path/'market-history/index.json').read_text())
    for win,n in mh.WINDOWS.items():
        data=json.loads((tmp_path/'market-history'/index['files']['vixcycle'][win]).read_text())
        assert len(data['dates'])==n
        assert data['series']['VIX']==[r['close'] for r in full['series'][-n:]]
    assert after['windows'][0]['label']=='2Y'
    lagged={'^VIX':macro['^VIX'].iloc[:-1]}
    lag_ctx=native.build_vix_cycle(lagged,lookback=77)
    native._vix_cycle_card(lag_ctx)
    lag_data=json.loads((tmp_path/'market-history'/index['files']['vixcycle']['2y']).read_text())
    assert lag_data['dates'][-1]=='2026-09-28'
    assert lag_data['availability']['VIX']['status']=='INSUFFICIENT_HISTORY'
    assert lag_data['observed_asof']=='2026-09-28'


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
    assert not soup.select('[data-window]')  # No exported data => no period choices.
    assert soup.select_one('.mh-history-note')
    assert soup.select_one('#market-history-config').string.count('history')==0
    assert 'window.CALC={"color":"Blue"};' in out
    assert ui.apply_html(out,tmp_path,mc=mc)==out


def test_same_session_mc57_is_exact_but_previous_session_never_reused(tmp_path):
    p=fixture_prices(1100)[refresh_mc57.MC57_ETFS];target=str(p.index[-1].date())
    path=tmp_path/'market-history/mc57-full.json'
    prior=refresh_mc57.compute_mc57(p,target,'original',history_output=path)
    refresh_mc57.dump(tmp_path/'work/mc57-authoritative.json',prior)
    revised=p.copy();revised.iloc[-1]*=1.00001
    fresh=refresh_mc57.compute_mc57(revised,target,'new',history_output=path)
    actual=refresh_mc57.preserve_same_session_mc57(tmp_path,fresh)
    assert actual['mc57']==prior['mc57'];assert actual['metric_scores']==prior['metric_scores']
    assert json.loads(path.read_text())['history'][-1]['mc57']==prior['mc57']
    tomorrow=dict(fresh,session_date='2099-01-01')
    assert refresh_mc57.preserve_same_session_mc57(tmp_path,tomorrow)==tomorrow


def test_preserved_jev_anchor_and_existing_categories(tmp_path):
    import render_jev_ranking
    mc={'mc57':22,'session_date':'2026-09-29','history':[],'metric_scores':{}}
    src='''<html><head><style>original</style></head><body><nav></nav>
    <section id="t-market"><div class="card cmt mkt20"><div class="mkt20-verdict">old</div><div class="mkt20-read">地合いは青</div>
    <div class="ccblock"><div class="cctxt">地合いは青</div></div><div class="ccblock"><div class="cctxt">マクロ情報を維持</div></div></div></section>
    <section id="t-rotation"></section><footer class='disc'>note</footer></body></html>'''
    out=ui.apply_html(src,tmp_path,mc=mc,summary={},breadth={'p50':29})
    assert "<footer class='disc'>" in out
    assert 'マクロ情報を維持' in out;assert '地合いは青' not in out
    path=tmp_path/'out.html';path.write_text(out);ranking=tmp_path/'jev.json';ranking.write_text(json.dumps({'status':'ready','rows':[]}))
    render_jev_ranking.render(path,ranking)
    assert 'jev-ranking-section' in path.read_text()
