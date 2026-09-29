import importlib.util, math, json, sqlite3
from datetime import date,timedelta
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('p',Path(__file__).with_name('pilot.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def bars():
    out=[]
    start=date(2025,9,1)
    for i in range(250):
        c=100+8*math.sin(i*.3)+i*.07
        out.append([(start+timedelta(days=i)).isoformat(),c,c+1,c-1,c,1000000])
    return out

def state():
    rows=bars()
    return {'forecast_grid':p.grids(rows),'reference_close':rows[-1][4]}

def response(s):
    ans={}
    for id,q in p.questions(s).items():
        if q['type']=='boolean':ans[id]={'probability':.6}
        else:
            labels=list(q['criteria']);chosen=labels[len(labels)//2]
            ans[id]={'choice':chosen,'probabilities':{k:float(k==chosen) for k in labels}}
    return {'ok':True,'rawRuns':[{'answers':ans} for _ in range(3)]}

def test_no_future_prices():
    rows=bars();assert all(r[0]<='2026-01-01' for r in p.valid_bars(rows,'2026-01-01'))

def test_duplicate_prices_rejected():
    with pytest.raises(p.SafeError):p.valid_bars(bars()+[bars()[0]])

def test_invalid_ohlc_rejected():
    r=bars()[0];r[2]=1
    assert p.valid_bars([r])==[]

def test_unknown_200_not_zero():
    assert p.technical(bars()[:126])['sma_distance_pct']['200'] is None

def test_all_bins_have_consistent_membership():
    for h,g in p.grids(bars()).items():
        for kind in ['terminal','upside','downside']:
            assert sum(b['sample_count'] for b in g[kind].values())==g['sample_size']
            assert list(g[kind].values())[-1]['upper_pct_exclusive'] is None

def test_historical_values_do_not_use_future_rows():
    before=p.grids(bars()[:200]);b=bars();b[230][4]=999999
    assert p.grids(b[:200])==before

def test_question_count():assert len(p.questions(state()))==10

def test_missing_probability_rejected():
    with pytest.raises(p.SafeError):p.normalized_distribution({'choice':'a','probabilities':{'a':1}},['a','b'])

def test_bad_sum_rejected():
    with pytest.raises(p.SafeError):p.normalized_distribution({'choice':'a','probabilities':{'a':.2,'b':.1}},['a','b'])

def test_rounding_sum_explicit():
    d,t=p.normalized_distribution({'choice':'a','probabilities':{'a':.5,'b':.49}},['a','b'])
    assert t==.99 and abs(sum(d.values())-1)<1e-12

def test_three_runs_required():
    s=state();r=response(s);r['rawRuns'].pop()
    with pytest.raises(p.SafeError):p.summarize(r,s)

def test_prediction_summary():
    s=state();r=p.summarize(response(s),s)
    assert r['forecasts']['5']['up_probability']==.6
    assert r['forecasts']['10']['terminal_agreement']==1
    assert r['forecasts']['5']['terminal_interval80_pct'][0]<0

def test_unbounded_tail_not_finite_invention():
    s=state();r=response(s)
    for run in r['rawRuns']:
        a=run['answers']['terminal_5d'];k=list(a['probabilities'])[-1]
        a['probabilities']={key:float(key==k) for key in a['probabilities']};a['choice']=k
    result=p.summarize(r,s)
    assert result['forecasts']['5']['terminal_interval80_pct'][1] is None

def test_input_news_excludes_vendor_insights():
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE articles(id TEXT,hash TEXT,published TEXT,retrieved TEXT,payload TEXT)')
    raw={'tickers':['ABC'],'title':'Example','description':'No assurance','insights':[{'future':'leak'}]}
    db.execute('INSERT INTO articles VALUES(?,?,?,?,?)',('a','h','2026-06-01T00:00:00Z','2026-09-29T13:00:00Z',json.dumps(raw)))
    result=p.news_for(db,['ABC'])
    assert 'insights' not in result['ABC'][0] and 'leak' not in json.dumps(result)

def test_future_news_not_sent():
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE articles(id TEXT,hash TEXT,published TEXT,retrieved TEXT,payload TEXT)')
    db.execute('INSERT INTO articles VALUES(?,?,?,?,?)',('a','h','2026-09-30T00:00:00Z','2026-10-01T00:00:00Z',json.dumps({'tickers':['ABC']})))
    assert not p.news_for(db,['ABC'])

def test_document_limits_recorded():
    docs=[{'id':str(i),'content_hash':'h','published_utc':f'2026-09-{1+i%28:02}T00:00:00Z','retrieved_utc':'2026-09-29T13:00:00Z','title':'guidance','description':'x'*2000,'publisher':'example'} for i in range(100)]
    selected,counts=p.choose_news(docs)
    assert len(selected)==40 and counts['eligible_articles_six_months']==100
    assert counts['description_truncations']==40
