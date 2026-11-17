"""Production engine: TQQQ sleeve during rally starts by the four signs."""
import pandas as pd, copy, prod
win=pd.read_pickle('up_windows.pkl')
base=copy.deepcopy(prod.sessions)
def stats(L):
    e=L['eq'].copy(); e.index=pd.to_datetime(e.index); out={}
    for a,b in (('2015-01-02','2026-11-13'),('2015-01-02','2020-12-31'),('2021-01-01','2026-11-13')):
        s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25
        out[a[:4]+'-'+b[2:4]]=(round(((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100,1), round((s/s.cummax()-1).min()*100,1))
    return out
i0=prod.days.index('2015-01-02'); i1=prod.days.index('2026-11-13')
def flag(cond):
    out={}
    for a,b,s in win:
        if cond(s):
            for d in pd.bdate_range(a,b): out[str(d.date())]=True
    return out
def go(name,mods):
    prod.sessions=copy.deepcopy(base)
    for day,pct in mods:
        for d in day:
            if d in prod.sessions: prod.sessions[d]['qqq_pct']=pct
    pf,L=prod.run(i0,i1,log=True); print(f'{name:34s}',stats(L))
hi=flag(lambda s:s>=3); lo=flag(lambda s:s<=1); mid=flag(lambda s:s==2)
go('今のルール',[])
go('○3〜4の戻りは余剰TQQQ100%',[(hi,100)])
go('○0〜1の戻りは余剰TQQQ0%',[(lo,0)])
go('両方',[(hi,100),(lo,0)])
go('○2以上は100%・0〜1は0%',[(hi,100),(mid,100),(lo,0)])
print('days flagged hi',len(hi),'lo',len(lo),'mid',len(mid))
