"""GS2 readings on 本命 signal days vs the rule's own trade outcome (next-open entry, -8% stop, 21EMA-of-lows exit)."""
import pandas as pd, numpy as np, gs2
O,H,L,C,V=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','high','low','close','volume'))
M=gs2.metrics(O,H,L,C,V,C['SPY']); pd.to_pickle(M,'gs2_metrics.pkl')
sig=pd.read_pickle('honmei.pkl')
EL=L.ewm(span=21,adjust=False).mean(); idx=C.index; pos={d:i for i,d in enumerate(idx)}; col={t:j for j,t in enumerate(C.columns)}
Cn,On,Ln,En=C.to_numpy(),O.to_numpy(),L.to_numpy(),EL.to_numpy()
def trade(d,t):
    i,j=pos[d],col[t]
    if i+1>=len(idx) or np.isnan(On[i+1,j]): return np.nan
    e=On[i+1,j]; st=e*0.92
    for k in range(i+1,min(len(idx),i+250)):
        if Ln[k,j]<=st: return (min(On[k,j],st) if k>i+1 else st)/e-1
        if Cn[k,j]<En[k,j]: return Cn[k,j]/e-1
    return np.nan
rows=[]
for d,t in zip(sig.date,sig.ticker):
    r=trade(d,t)
    if np.isnan(r): continue
    rows.append(dict(date=d,t=t,ret=min(r,3),**{k:M[k].at[d,t] for k in M}))
R=pd.DataFrame(rows); R['half']=np.where(R.date<'2020-01-01','2014-19','2020-26'); R.to_pickle('g1.pkl')
print(len(R), R.groupby('half').size().to_dict())
print(R[list(M)].describe().round(1).T[['mean','25%','50%','75%']])
