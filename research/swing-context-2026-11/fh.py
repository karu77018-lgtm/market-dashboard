"""Production engine: pause new swing entries by the phase of the Nasdaq-100 (local replay of 局面チェック)."""
import pandas as pd, numpy as np, copy, prod
n=pd.read_csv('macro/NDX.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').close.loc['2012-01-01':]
hi=n.rolling(252,min_periods=200).max(); dd=n/hi-1; ma50=n.rolling(50).mean(); ret=n.pct_change()*100
state={}; indec=False
for t in range(len(n)):
    d=n.index[t]; c=n.iloc[t]
    if pd.isna(dd.iloc[t]): continue
    if not indec:
        if dd.iloc[t]<=-0.10: indec=True; low=c; li=t; up=None
    elif dd.iloc[t]>=-0.02: indec=False
    else:
        if c<low: low=c; li=t; up=None
        elif up is None and c>=low*1.05:
            s=int(c>ma50.iloc[t])+int(t-li>3)+int(ret.iloc[li+1:t+1].max()<3.7); up=s
    state[str(d.date())]=('high' if not indec else ('down' if up is None else f'up{up}'))
S=pd.Series(state); print(S['2015':].value_counts())
base=copy.deepcopy(prod.sessions)
def stats(L):
    e=L['eq'].copy(); e.index=pd.to_datetime(e.index); out={}
    for a,b in (('2015-01-02','2026-11-13'),('2015-01-02','2020-12-31'),('2021-01-01','2026-11-13')):
        s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25
        out[a[:4]+'-'+b[2:4]]=(round(((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100,1), round((s/s.cummax()-1).min()*100,1))
    return out
i0=prod.days.index('2015-01-02'); i1=prod.days.index('2026-11-13')
def go(name,pause):
    prod.sessions=copy.deepcopy(base); k=0
    for day,s in prod.sessions.items():
        if pause(state.get(day,'high')) and s.get('best'): s['best']=[]; k+=1
    pf,L=prod.run(i0,i1,log=True); print(f'{name:36s}',stats(L),'paused days',k,'trades',len(pf['closed']))
go('今のルール',lambda s:False)
go('下げの途中（+5%前）は新規なし',lambda s:s=='down')
go('戻りの○0個の間は新規なし',lambda s:s=='up0')
go('戻りの○0〜1個の間は新規なし',lambda s:s in('up0','up1'))
go('下げの途中と○0〜1個は新規なし',lambda s:s in('down','up0','up1'))
go('10%以上の下げの間はずっと新規なし',lambda s:s!='high')
