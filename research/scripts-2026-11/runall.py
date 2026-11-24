import os, sys, pandas as pd, numpy as np
sys.path.insert(0,'.')
import prod3 as P
if os.environ.get('BAD'):
    import pickle; P.tp.BAD=set(pd.read_pickle(os.environ['BAD']))
    P.tp.PILOT=float(os.environ.get('PILOT','1')); P.tp.STOP_BAD=float(os.environ['STOPBAD']) if os.environ.get('STOPBAD') else None
    P.tp.FULL_ADDS=os.environ.get('FULLADDS','1')=='1'
i1=P.days.index('2026-11-13')
pf,Lg=P.run(P.days.index('2015-01-02'),i1,log=True)
e=Lg['eq'].copy(); e.index=pd.to_datetime(e.index)
def cagr(s): y=(s.index[-1]-s.index[0]).days/365.25; return (s.iloc[-1]/s.iloc[0])**(1/y)-1
f=P.run(P.days.index('2026-10-05'),i1)
print(f"{os.environ.get('NAME',''):40s}| 全 {cagr(e)*100:5.1f}% | 15-20 {cagr(e['2015':'2020'])*100:5.1f}% | 21-26 {cagr(e['2021':'2026'])*100:5.1f}% | DD {(e/e.cummax()-1).min()*100:5.1f}% | 10月再現 {(f['equity'][-1][1]-1)*100:+5.1f}%",flush=True)
