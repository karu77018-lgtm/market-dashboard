"""本命 swing signals (next-open entry, -8% stop, exit on close below low-21EMA) by lamp state at the signal."""
import pandas as pd, numpy as np
X=pd.read_pickle('fx.pkl'); sig=pd.read_pickle('honmei.pkl')
C=pd.read_pickle('close.pkl').astype(float); O=pd.read_pickle('open.pkl').astype(float); L=pd.read_pickle('low.pkl').astype(float)
EL=L.ewm(span=21,adjust=False).mean(); idx=C.index; pos={d:i for i,d in enumerate(idx)}
Cn,On,Ln,En=C.to_numpy(),O.to_numpy(),L.to_numpy(),EL.to_numpy(); col={t:j for j,t in enumerate(C.columns)}
def trade(d,t):
    i,j=pos[d],col[t]
    if i+1>=len(idx) or np.isnan(On[i+1,j]): return np.nan,np.nan
    e=On[i+1,j]; st=e*0.92
    for k in range(i+1,min(len(idx),i+250)):
        if Ln[k,j]<=st: return (min(On[k,j],st) if k>i+1 else st)/e-1, k-i
        if Cn[k,j]<En[k,j]: return Cn[k,j]/e-1, k-i
    return np.nan,np.nan
rows=[]
for d,t in zip(sig.date,sig.ticker):
    if d not in X.index: continue
    r,h=trade(d,t); rows.append(dict(date=d,t=t,ret=r,hold=h,**X.loc[d,['f1','f2','f3','sf1','sf2','sf3','half']].to_dict()))
R=pd.DataFrame(rows).dropna(subset=['ret']); R['ret']=R.ret.clip(upper=3)
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
def tab(by):
    g=R.groupby(['half',by])
    return pd.DataFrame({'件数':g.size(),'平均%':g.ret.mean()*100,'中央%':g.ret.median()*100,'勝率%':g.ret.apply(lambda x:(x>0).mean()*100),'PF':g.ret.apply(pf)}).round(2)
print('all:',len(R)); print(R.groupby('half').ret.agg(['size','mean']).round(3))
for k in ('sf1','sf2','sf3'): print('\n==',k); print(tab(k).to_string())
R.to_pickle('fb.pkl')
