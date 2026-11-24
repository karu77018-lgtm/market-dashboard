import os, sys, pandas as pd, numpy as np
sys.path.insert(0,'.')
G=pd.read_pickle('gates.pkl'); name=os.environ['GATE']
pd.to_pickle(G[name],'reg_tmp.pkl'); os.environ['REG']='reg_tmp.pkl'
import prod3 as P
i1=P.days.index('2026-11-13')
pf,Lg=P.run(P.days.index('2015-01-02'),i1,log=True)
e=Lg['eq'].copy(); e.index=pd.to_datetime(e.index)
def cagr(s): y=(s.index[-1]-s.index[0]).days/365.25; return (s.iloc[-1]/s.iloc[0])**(1/y)-1
f=P.run(P.days.index('2026-10-05'),i1)
fr=f['equity'][-1][1]-1; nb=len(f['closed'])+len(f['positions'])
print(f"{name:36s}| 全 {cagr(e)*100:5.1f}% | 15-20 {cagr(e['2015':'2020'])*100:5.1f}% | 21-26 {cagr(e['2021':'2026'])*100:5.1f}% | DD {(e/e.cummax()-1).min()*100:5.1f}% | 10/5開始→11/13 {fr*100:+5.1f}% 買い{nb}件",flush=True)
