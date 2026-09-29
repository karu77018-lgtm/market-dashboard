import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
spec=importlib.util.spec_from_file_location('study',Path(__file__).with_name('study.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def frame(n=100):
    days=pd.bdate_range('2025-01-02',periods=n)
    c=100*np.exp(np.arange(n)*.0008+np.sin(np.arange(n))*.01)
    return pd.DataFrame({'open':c*.998,'high':c*1.015,'low':c*.985,'close':c,'volume':1000000},index=days)

def test_cutoff_dst():
    assert s.cutoff('2026-03-30').hour==20
    assert s.cutoff('2026-01-05').hour==21

def test_horizon_next_open_end():
    f=frame();r=s.target(f,f.index[50],5,f.index)
    assert r['entry_session']==str(f.index[51].date())
    assert r['end_session']==str(f.index[55].date())
    assert r['terminal_log']==pytest.approx(np.log(f.close.iloc[55]/f.open.iloc[51]))

def test_future_unavailable():
    f=frame();assert s.target(f,f.index[-3],5,f.index) is None

def test_missing_bar_not_silent():
    f=frame();f.iloc[52,0]=np.nan
    assert s.target(f,f.index[50],5,f.index) is None

def test_baseline_maturity():
    f=frame();past,latest=s.past_outcomes(f.iloc[:60],10)
    assert latest<=str(f.index[59].date()) and len(past['terminal'])>10

def test_future_mutation_cannot_change_features():
    f=frame();g=f.copy();g.iloc[70:,:4]*=100
    assert s.features(f.iloc[:65])==s.features(g.iloc[:65])
    assert s.past_outcomes(f.iloc[:65],10)==s.past_outcomes(g.iloc[:65],10)

@pytest.mark.parametrize('kind',['terminal','up','down'])
def test_distribution_valid(kind):
    f=s.family([.1,.5,-.2] if kind=='terminal' else [.1,.5,.2],kind)
    assert f['p'].sum()==pytest.approx(1)
    r=s.distribution_summary(f,f['p'],.05,kind)
    assert r['q10_pct']<=r['q50_pct']<=r['q90_pct']
    assert 0<=r['p_positive']<=1

def payload(p):
    return {'rawRuns':[{'answers':{'q':{'choice':'a','probabilities':p}}} for _ in range(3)]}

def test_probability_sum_rounding_tracked():
    out=s.parse_probabilities(payload({'a':.51,'b':.48}),{'q':{'criteria':{'a':'A','b':'B'}}})
    assert out['q']['p'].sum()==pytest.approx(1) and out['q']['agreement']==1

def test_missing_distribution_rejected():
    with pytest.raises(s.SafeError):s.parse_probabilities(payload({'a':1}),{'q':{'criteria':{'a':'A','b':'B'}}})

def test_invalid_distribution_rejected():
    with pytest.raises(s.SafeError):s.parse_probabilities(payload({'a':.9,'b':.9}),{'q':{'criteria':{'a':'A','b':'B'}}})

def test_partial_runs_rejected():
    p=payload({'a':.5,'b':.5});p['rawRuns'].pop()
    with pytest.raises(s.SafeError):s.parse_probabilities(p,{'q':{'criteria':{'a':'A','b':'B'}}})

def test_selection_not_future_dependent():
    f=frame();frames={f'T{i}':f*(1+i*.01) for i in range(16)}
    day=f.index[70];a=s.choose_candidates(frames,day)[0]
    changed={tk:g.copy() for tk,g in frames.items()}
    for g in changed.values():g.iloc[71:,:4]*=100
    assert a==s.choose_candidates(changed,day)[0]

def test_known_bad_ohlc_not_accepted():
    f=frame().reset_index().rename(columns={'index':'date'});f.loc[0,'high']=1
    out=s.clean_frame(f);assert out.iloc[0].isna().all()

def test_duplicate_dates_rejected():
    f=frame().reset_index().rename(columns={'index':'date'})
    with pytest.raises(s.SafeError):s.clean_frame(pd.concat([f,f.iloc[:1]]))

def test_calibration_holdout_disjoint():
    c=s.CFG
    assert c['development'][1]<c['calibration'][0]<c['calibration'][1]<c['holdout'][0]
    assert c['pilot_origins']==3 and c['per_origin']==8 and c['budget_usd']==.20
