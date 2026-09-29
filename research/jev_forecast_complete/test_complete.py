import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
spec=importlib.util.spec_from_file_location('completion',Path(__file__).with_name('complete.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def frame(n=400):
 ix=pd.bdate_range('2024-01-02',periods=n);c=100*np.exp(np.arange(n)*.0003+.03*np.sin(np.arange(n)))
 return pd.DataFrame({'open':c*.997,'high':c*1.03,'low':c*.97,'close':c,'volume':np.full(n,1e6)},index=ix)

@pytest.mark.parametrize('kind',['terminal','up','down'])
@pytest.mark.parametrize('scale',[1.,10.,63.3786255275,89.6309117856,150.])
def test_finite_actual_arithmetic_mean(kind,scale):
 vals=[-20.,-10.,0.,15.,40.,180.] if kind=='terminal' else [0,1,10,40,90]
 f=s.make_family(vals,np.ones(len(vals)),scale,kind)
 for p in [f['p'],np.eye(7)[0],np.eye(7)[-1]]:
  r=s.summarize(f,p)
  assert np.isfinite(r['mean_pct']) and min(f['x'])<=r['mean_pct']<=max(f['x'])
  assert r['mean_pct']==pytest.approx(np.dot(p,f['means']))
  assert r['q10_pct']<=r['q50_pct']<=r['q90_pct']
  if kind=='down':assert 0<=r['mean_pct']<100
  if kind=='terminal':assert r['mean_pct']>-100

def test_no_clipping_observed_extreme():
 f=s.make_family([900.],[1.],5.,'terminal');assert 900. in f['x']
 assert s.summarize(f,f['p'])['mean_pct']==pytest.approx(np.average(f['x'],weights=f['w']))

def test_batl_old_scale_no_exponential_explosion():
 f=s.make_family([-10.,-30.,20.,100.],np.ones(4),89.6309117856,'terminal')
 r=s.summarize(f,f['p']);assert abs(r['mean_pct'])<100

def test_horizon_and_future_isolation():
 f=frame();day=f.index[300];past,w,latest=s.arithmetic_history(f.loc[:day],10)
 assert latest<=str(day.date())
 modified=f.copy();modified.iloc[301:,:4]*=20
 assert s.arithmetic_history(modified.loc[:day],10)==(past,w,latest)
 actual=s.actual_target(f,day,10,f.index)
 assert actual['entry_session']==str(f.index[301].date())
 assert actual['end_session']==str(f.index[310].date())
 assert actual['terminal_pct']==pytest.approx((f.close.iloc[310]/f.open.iloc[301]-1)*100)
 assert s.actual_target(f,f.index[-4],10,f.index) is None

def fake_row(y=8.,end='2026-08-20',phase='calibration'):
 return {'model':'jev_news','horizon':5,'phase':phase,'origin':'2026-08-10',
 'actual':{'end_session':end,'terminal_pct':y,'up_pct':20.,'down_pct':10.},
 **{k:{'scale_pp':10.,'q10_pct':-5. if k=='terminal' else 0.,'q50_pct':0.,'q90_pct':5.,'p_positive':.5,'mean_pct':0.} for k in s.KINDS}}

def test_calibration_does_not_use_boundary_crossing_labels():
 rows=[fake_row() for _ in range(20)];base=s.residual_calibration(rows,'jev_news',5)
 rows.extend([fake_row(9999,'2026-09-01'),fake_row(-9999,'2026-09-10','holdout')])
 assert s.residual_calibration(rows,'jev_news',5)==base
 assert base['n']==20 and base['latest_label_session']=='2026-08-20'

def test_calibration_bounds_not_mean_or_probability():
 r=fake_row();q=s.apply_cal(r,{'terminal_add_scale':2.,'up_add_scale':3.,'down_add_scale':30.})
 assert q['terminal']['mean_pct']==r['terminal']['mean_pct']
 assert q['terminal']['cal_lower_pct']==-25 and q['terminal']['cal_upper_pct']==25
 assert q['down']['cal_upper_pct']==100

def test_feedback_no_holdout_and_no_unmatured_labels():
 rows=[fake_row(8,'2026-04-10','development') for _ in range(20)]
 base=s.frozen_feedback(rows,'jev_news','2026-04-11')
 rows += [fake_row(9999,'2026-04-12','development'),fake_row(-9999,'2026-04-10','holdout')]
 assert s.frozen_feedback(rows,'jev_news','2026-04-11')==base

def test_interval_score_penalizes_wide_or_missed_ranges():
 rows=[fake_row()];r=s.score_rows(rows,'jev_news',5)
 assert r['interval_score_pp']==40 and r['terminal80_coverage']==0

def test_named_candidates_do_not_require_core12():
 h='window.DET='+s.canonical({'A':{'loc':['RS21']},'B':{'loc':['Core 12 #1']},'C':{'loc':[]}})+';'
 assert set(dict(s.named_tickers(h)))=={'A','B'}

def test_invalid_probability_or_physical_support_rejected():
 f=s.make_family([1.],[1.],5.,'terminal')
 with pytest.raises(ValueError):s.summarize(f,[1.]*7)
 with pytest.raises(ValueError):s.make_family([-101],[1.],5.,'terminal')
 with pytest.raises(ValueError):s.make_family([120],[1.],5.,'down')

def test_fixed_protocol_phases():
 p=s.PLAN
 assert p['development'][1]<p['calibration'][0]<p['calibration'][1]<p['holdout'][0]
 assert p['no_outcome_dependent_exclusion'] and not p['private_holdings']
