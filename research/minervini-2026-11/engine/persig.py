import pandas as pd, numpy as np
O,L,C=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','low','close'))
EL=L.ewm(span=21,adjust=False).mean()
sig=pd.read_pickle('sig_feat.pkl'); pos={d:i for i,d in enumerate(C.index)}
On,Ln,Cn,En=O.to_numpy(),L.to_numpy(),C.to_numpy(),EL.to_numpy(); col={t:j for j,t in enumerate(C.columns)}
def trade(i,j):
    if i+1>=len(Cn) or np.isnan(On[i+1,j]): return np.nan
    e=On[i+1,j]; st=e*0.92; hi=e
    for k in range(i+1,len(Cn)):
        o,l,c,m=On[k,j],Ln[k,j],Cn[k,j],En[k,j]
        if np.isnan(c): continue
        if l<=st: return (o if o<=st else st)/e-1
        hi=max(hi,c)
        if (c<m or c<=hi*0.85) and k+1<len(Cn): return On[k+1,j]/e-1
    return np.nan  # 未決済
sig['ret']=[trade(pos[d],col[t]) for d,t in zip(sig.date,sig.ticker)]
S=sig.dropna(subset=['ret']); S['hi']=S.above_low>=1.0
pf=lambda x: x[x>0].sum()/-x[x<=0].sum()
w=0; print('年  安値+100%以上 PF(件数) | 未満 PF(件数)')
for y in range(2014,2027):
    z=S[S.date.dt.year==y]; a,b=z[z.hi],z[~z.hi]
    if len(a)<5 or len(b)<5: print(y,'件数不足'); continue
    w+=pf(a.ret)>pf(b.ret); print(y,f'{pf(a.ret):5.2f} ({len(a):3d}) | {pf(b.ret):5.2f} ({len(b):3d})')
print('上回った年',w)
for h,(a,b) in {'2014-20':('2014','2020'),'2021-26':('2021','2026')}.items():
    z=S[(S.date>=a)&(S.date<=b+'-12-31')]; print(h,'以上 PF',round(pf(z[z.hi].ret),2),'平均',round(z[z.hi].ret.mean()*100,2),'% | 未満 PF',round(pf(z[~z.hi].ret),2),'平均',round(z[~z.hi].ret.mean()*100,2),'%')
# 月ブロックのブートストラップ（平均の差）
S['m']=S.date.dt.to_period('M'); ms=S.m.unique(); rs=np.random.RandomState(1); D=[]
g={m:z for m,z in S.groupby('m')}
for _ in range(2000):
    z=pd.concat([g[m] for m in rs.choice(ms,len(ms))]); D.append(z[z.hi].ret.mean()-z[~z.hi].ret.mean())
D=np.array(D)*100; print('平均の差 5-95%:',np.percentile(D,[5,95]).round(2),'>0の割合',round((D>0).mean()*100,1),'%')
print('全体 平均差', round((S[S.hi].ret.mean()-S[~S.hi].ret.mean())*100,2))
