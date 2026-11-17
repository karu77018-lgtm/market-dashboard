"""Production engine: skip 本命 signals from the hottest industries / sectors (63-day median return rank)."""
import pandas as pd, copy, prod
R=pd.read_pickle('fi.pkl'); R['k']=R.date.dt.strftime('%Y-%m-%d')+'|'+R.t
ind=dict(zip(R.k,R.ind)); sec=dict(zip(R.k,R.sec))
base=copy.deepcopy(prod.sessions)
def stats(L):
    e=L['eq'].copy(); e.index=pd.to_datetime(e.index); out={}
    for a,b in (('2015-01-02','2026-11-13'),('2015-01-02','2020-12-31'),('2021-01-01','2026-11-13')):
        s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25
        out[a[:4]+'-'+b[2:4]]=(round(((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100,1), round((s/s.cummax()-1).min()*100,1))
    return out
i0=prod.days.index('2015-01-02'); i1=prod.days.index('2026-11-13')
def go(name,drop):
    prod.sessions=copy.deepcopy(base); k=0
    for day,s in prod.sessions.items():
        keep=[x for x in s.get('best',[]) if not drop(day+'|'+x['t'])]; k+=len(s.get('best',[]))-len(keep); s['best']=keep
    pf,L=prod.run(i0,i1,log=True); print(f'{name:28s}',stats(L),'dropped',k,'trades',len(pf['closed']))
go('今のルール',lambda k:False)
go('業種上位20%を除外',lambda k:ind.get(k,0)>=0.8)
go('業種上位33%を除外',lambda k:ind.get(k,0)>=0.67)
go('セクター上位半分を除外',lambda k:sec.get(k,0)>=0.5)
