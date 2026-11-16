import pandas as pd, numpy as np, ftd
VIX=ftd.load('VIX'); V3=ftd.load('VIX3M'); IWM=ftd.load('IWM'); RSP=ftd.load('RSP')
baa=pd.read_csv('baa.csv',parse_dates=['observation_date']).set_index('observation_date').iloc[:,0]; baa=pd.to_numeric(baa,errors='coerce').dropna()
tnx=pd.read_csv('macro/TNX.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').close
# stock-panel breadth 2013+
D=pd.read_pickle('core.pkl'); c_,s50_,liq=D['c'],D['s50'],D['liquid']; b50=((c_>s50_)&liq).sum(1)/liq.sum(1)
nh=((c_>=c_.rolling(252).max())&liq).sum(1)/liq.sum(1)
EV={}; DF={}
for tk in ('QQQ','SPY'): DF[tk],EV[tk]=ftd.events(tk)
rows=[]
for tk,other in (('QQQ','SPY'),('SPY','QQQ')):
    df=DF[tk]; c,o,h,l,v=[df[k].to_numpy(float) for k in ('close','open','high','low','volume')]; idx=df.index
    s50=df.close.rolling(50).mean().to_numpy(); s200=df.close.rolling(200).mean().to_numpy(); v50=df.volume.rolling(50).mean().shift(1).to_numpy()
    odates=[e['date'] for e in EV[other]]
    prev_fail=[]
    for k,e in enumerate(EV[tk]):
        i=e['i']; d=e['date']; lo_i=e['low_i']
        w=max(0,lo_i-252); hi_i=w+int(np.argmax(c[w:lo_i+1])) if lo_i>w else lo_i
        end=e['end']; n_after=(end-i) if end is not None else None
        r=dict(tk=tk,date=d,day=e['day'],pct=e['pct']*100,
          volr=v[i]/v[i-1],vol50=v[i]/v50[i] if v50[i]>0 else np.nan,clpos=(c[i]-l[i])/(h[i]-l[i]) if h[i]>l[i] else np.nan,
          gap=(o[i]/c[i-1]-1)*100, cushion=(c[i]/l[i]-1)*100, fromlow=(c[i]/l[lo_i]-1)*100,
          depth=(l[lo_i]/c[hi_i]-1)*100, declen=lo_i-hi_i, a200=float(c[i]>s200[i]) if np.isfinite(s200[i]) else np.nan,
          s200slope=(s200[i]/s200[i-20]-1)*100 if i>=220 else np.nan, d50=(c[i]/s50[i]-1)*100, d200=(c[i]/s200[i]-1)*100 if np.isfinite(s200[i]) else np.nan,
          confirm=float(any(abs((d-x).days)<=5 for x in odates)),
          nprevfail=sum(1 for pf in prev_fail if (d-pf).days<=180), )
        vx=VIX.close
        if d in vx.index:
            vi=vx.index.get_loc(d); r['vix']=vx.iloc[vi]; r['vixoff']=(vx.iloc[vi]/vx.iloc[max(0,vi-30):vi+1].max()-1)*100
        if d in V3.index and d in vx.index: r['term']=vx[d]/V3.close[d]
        for nm,s in (('iwm',IWM),('rsp',RSP)):
            if d in s.index:
                si=s.index.get_loc(d); r[nm]=(s.close.iloc[si]/s.close.iloc[si-1]-1)*100-r['pct']
        r['cred20']=(baa.asof(d)-baa.asof(d-pd.Timedelta(days=28)))*100; r['d10_20']=(tnx.asof(d)-tnx.asof(d-pd.Timedelta(days=28)))*100
        if d in b50.index: r['b50']=b50[d]*100; r['b50ch']=(b50[d]-b50.iloc[b50.index.get_loc(d)-5])*100; r['nh']=nh[d]*100
        # outcome
        r['why']=e['why']; r['n_after']=n_after
        r['fake10']=float(e['why']=='a' and n_after<=10); r['fake25']=float(e['why']=='a' and n_after<=25)
        r['fail_any25']=float(end is not None and n_after<=25)
        for hzn in (10,25,60): r[f'f{hzn}']=(c[i+hzn]/c[i]-1)*100 if i+hzn<len(c) else np.nan
        # post-FTD early signs (day 1..5)
        for kk in (1,2,3,5):
            if i+kk<len(c):
                r[f'p{kk}']=(c[i+kk]/c[i]-1)*100
        if i+5<len(c):
            dd=[(c[i+t]<c[i+t-1]*0.998) and v[i+t]>v[i+t-1] for t in range(1,6)]
            r['dist3']=float(any(dd[:3])); r['dist5']=sum(dd)
            r['undercut3']=float(min(l[i+1:i+4])<l[i]); r['nohigher3']=float(max(c[i+1:i+4])<=c[i])
            r['down1pct3']=float(min(c[i+t]/c[i+t-1]-1 for t in range(1,4))<=-0.01)
            r['below_ftdclose2']=float(c[i+2]<c[i])
        if r['why']=='a': prev_fail.append(df.index[end])
        rows.append(r)
X=pd.DataFrame(rows); X.to_pickle('ftd_events.pkl')
X=X[X.n_after.notna()|(X.date<'2026-10-01')]
print(len(X),'events', X.groupby('tk').size().to_dict())
for tk,g in X.groupby('tk'):
    print(tk,'fake<=10: %.0f%%  fake<=25: %.0f%%  any-invalidation<=25: %.0f%% | median f25 %.1f f60 %.1f'%(g.fake10.mean()*100,g.fake25.mean()*100,g.fail_any25.mean()*100,g.f25.median(),g.f60.median()))
print('fake25 by era:',X.groupby([X.tk,X.date.dt.year//10*10]).fake25.agg(['mean','size']).round(2).to_string())
