import json, os, pandas as pd, numpy as np, study
names=json.load(open('ipo_list.json'))
frames={}
for t in names:
    f=study.load(t)
    if len(f)==0 or f.date.iloc[0]<pd.Timestamp('2014-07-01') or study.spac_like(f): continue
    frames[t]=f
def run(**kw):
    for k,v in kw.items(): setattr(study,k,v)
    rows=[]
    for t,f in frames.items():
        study.t_name=t; rows+=study.signals(t,f)
    d=pd.DataFrame(rows); d=d[(d.date>='2015')&d.regime]
    pnl=d.ret_add*(1+d.adds)
    return len(d), round(d.ret.mean()*100,2), round(d.ret[d.ret>0].sum()/-d.ret[d.ret<0].sum(),2), round(pnl[pnl>0].sum()/-pnl[pnl<0].sum(),2)
base=dict(VOL_X=1.4,MIN_BASE=15,DEPTH=(0.10,0.50),MIN_DV=20e6,MAX_AGE=504)
print('base',run(**base))
for k,vals in [('VOL_X',[1.0,1.2,1.8]),('MIN_BASE',[10,25,40]),('DEPTH',[(0.10,0.35),(0.15,0.50),(0.05,0.60)]),('MIN_DV',[10e6,50e6]),('MAX_AGE',[252,756])]:
    for v in vals:
        p=dict(base); p[k]=v; print(k,v,run(**p))
