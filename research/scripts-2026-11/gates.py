import pandas as pd, numpy as np
C,O,L,V=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('close','open','low','volume'))
dates=C.index; q=C['QQQ']; qv=V['QQQ']
rd=lambda f: pd.read_csv(f,parse_dates=['date']).set_index('date').close.reindex(dates).ffill()
base=q>q.rolling(200).mean()
G={}
G['今のルール(200日線)']=base
G['50日線の上だけ']=q>q.rolling(50).mean()
G['200日線＋50日線']=base&(q>q.rolling(50).mean())
G['200日線＋21EMA']=base&(q>q.ewm(span=21,adjust=False).mean())
dd=((q/q.shift(1)-1)<=-0.002)&(qv>qv.shift(1))
for k in (4,5,6,7): G[f'200日線＋売り抜け日{k}未満(25日)']=base&(dd.rolling(25).sum()<k)
hb=rd('x_SPHB.csv')/rd('x_SPLV.csv'); ch=hb/hb.shift(20)-1
for k in (-0.04,-0.05,-0.06): G[f'200日線＋SPHB/SPLV 20日{int(k*100)}%でない']=base&~(ch<=k)
ts=rd('x_VIX.csv')/rd('x_VIX3M.csv')
for k in (0.95,1.0,1.05): G[f'200日線＋VIX/VIX3M<{k}']=base&(ts<k)
# 本命の損切り連発: signals' -8% stop hits (entry next open) counted on the hit day
sig=pd.read_pickle('honmei.pkl'); pos={d:i for i,d in enumerate(dates)}; col={t:j for j,t in enumerate(C.columns)}
Cn,On,Ln=C.to_numpy(),O.to_numpy(),L.to_numpy(); EL=L.ewm(span=21,adjust=False).mean().to_numpy()
hits=np.zeros(len(dates)); n=len(dates)
live=[]  # (entry index, exit index, entry price, j)
for d,t in zip(sig.date,sig.ticker):
    i,j=pos[d],col[t]
    if i+1>=n or np.isnan(On[i+1,j]): continue
    e=On[i+1,j]; st=e*0.92; x=n-1
    for k in range(i+1,min(n,i+250)):
        if Ln[k,j]<=st: hits[k]+=1; x=k; break
        if Cn[k,j]<EL[k,j]: x=k; break
    live.append((i+1,x,e,j))
H=pd.Series(hits,index=dates)
for w,k in ((10,2),(10,3),(10,4),(15,3),(20,4)): G[f'200日線＋本命損切り{w}日で{k}件未満']=base&(H.rolling(w).sum()<k)
# 速い勢い: 直近15営業日に出た本命の、今日までの平均損益
ret=np.full(n,np.nan)
for s in range(n):
    r=[Cn[min(s,x),j]/e-1 for (a,x,e,j) in live if s-15<a<=s]
    if len(r)>=3: ret[s]=np.nanmean(r)
R=pd.Series(ret,index=dates)
for k in (0,-0.02,-0.04): G[f'200日線＋直近本命平均{int(k*100)}%未満でない']=base&~(R<k)
pd.to_pickle(G,'gates.pkl')
for k,v in G.items(): print(f'{k:36s} on日数 {v["2015":].mean()*100:4.0f}%')
