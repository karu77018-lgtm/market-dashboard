"""Production engine with lamp-based variants: pause new swing entries while all three lamps are calm."""
import pandas as pd, numpy as np, copy
import prod
X=pd.read_pickle('fx.pkl')
calm=((X.f1<.2)&(X.f2<.25)&(X.f3<.4)).reindex(prod.dates).fillna(False)
w=X.f3.rolling(20).max(); clear=((w>=0.6)&(X.f3<=0.35)).reindex(prod.dates).fillna(False)
base=copy.deepcopy(prod.sessions)
def stats(L):
    e=L['eq'].copy(); e.index=pd.to_datetime(e.index)
    out={}
    for a,b in (('2015-01-02','2026-11-13'),('2015-01-02','2020-12-31'),('2021-01-01','2026-11-13')):
        s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25
        out[a[:4]+'-'+b[:4]]=(round(((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100,1), round((s/s.cummax()-1).min()*100,1))
    return out
i0=prod.days.index('2015-01-02'); i1=prod.days.index('2026-11-13')
def go(name,mod):
    prod.sessions=copy.deepcopy(base)
    for i,day in enumerate(prod.days):
        if day in prod.sessions: mod(i,day,prod.sessions[day])
    pf,L=prod.run(i0,i1,log=True); print(f'{name:32s}',stats(L),'trades',len(pf['closed']))
go('今のルール',lambda i,d,s:None)
go('全灯平常の日は新規エントリーなし',lambda i,d,s:s.update(best=[]) if calm.iloc[i] else None)
go('全灯平常の日は余剰TQQQも0%',lambda i,d,s:s.update(qqq_pct=0) if calm.iloc[i] else None)
go('両方',lambda i,d,s:s.update(best=[],qqq_pct=0) if calm.iloc[i] else None)
go('F3回復後20日は余剰TQQQ100%',lambda i,d,s:s.update(qqq_pct=100) if clear.rolling(20).max().iloc[i] else None)
print('calm days',int(calm.sum()),'in',calm[calm].index.to_period('M').nunique(),'months; clear days',int(clear.sum()))
