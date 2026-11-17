"""Control: drop the same share of signals at random (is the sector filter better than dropping signals at all?)."""
import pandas as pd, copy, random, prod
R=pd.read_pickle('fi.pkl'); R['k']=R.date.dt.strftime('%Y-%m-%d')+'|'+R.t; sec=dict(zip(R.k,R.sec))
base=copy.deepcopy(prod.sessions)
allk=[d+'|'+x['t'] for d,s in base.items() for x in s.get('best',[])]
share=sum(1 for k in allk if sec.get(k,0)>=0.5)/len(allk); print('share dropped by sector rule',round(share,3),len(allk))
def stats(L):
    e=L['eq'].copy(); e.index=pd.to_datetime(e.index); out=[]
    for a,b in (('2015-01-02','2026-11-13'),('2015-01-02','2020-12-31'),('2021-01-01','2026-11-13')):
        s=e[a:b]; y=(s.index[-1]-s.index[0]).days/365.25; out.append(round(((s.iloc[-1]/s.iloc[0])**(1/y)-1)*100,1))
    out.append(round((e['2015':]/e['2015':].cummax()-1).min()*100,1)); return out
i0=prod.days.index('2015-01-02'); i1=prod.days.index('2026-11-13')
res=[]
for seed in range(8):
    rnd=random.Random(seed); drop={k for k in allk if rnd.random()<share}
    prod.sessions=copy.deepcopy(base)
    for day,s in prod.sessions.items(): s['best']=[x for x in s.get('best',[]) if day+'|'+x['t'] not in drop]
    pf,L=prod.run(i0,i1,log=True); r=stats(L); res.append(r); print(seed,r,len(pf['closed']),flush=True)
df=pd.DataFrame(res,columns=['all','15-20','21-26','maxdd']); print(df.describe().round(1))
