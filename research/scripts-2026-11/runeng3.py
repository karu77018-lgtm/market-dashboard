import os, sys, pickle, pandas as pd, numpy as np
sys.path.insert(0,'.')
import prod3 as P
ex=os.environ.get('EXITLINE')
if ex:
    L=pd.read_pickle(ex)   # dict ticker -> pd.Series of bool "exit at this close" (indexed by date str)
    mode=os.environ.get('EXITMODE','replace')
    def EXIT(t,day,b,p):
        x=L.get(t); hit=bool(x.get(day,False)) if x is not None else False
        base=b[2]<p['ema']
        return hit if mode=='replace' else (hit or base) if mode=='or' else (hit and base)
    P.tp.EXIT=EXIT
i0=P.days.index('2015-01-02'); i1=P.days.index('2026-11-13')
pf,Lg=P.run(i0,i1,log=True)
e=Lg['eq'].copy(); e.index=pd.to_datetime(e.index)
def cagr(s): y=(s.index[-1]-s.index[0]).days/365.25; return (s.iloc[-1]/s.iloc[0])**(1/y)-1
print(f"{os.environ.get('NAME',''):34s}| 2015-26 {cagr(e)*100:5.1f}% | 2015-20 {cagr(e['2015':'2020'])*100:5.1f}% | 2021-26 {cagr(e['2021':'2026'])*100:5.1f}% | DD {(e/e.cummax()-1).min()*100:5.1f}% | trades {len(pf['closed'])}",flush=True)
