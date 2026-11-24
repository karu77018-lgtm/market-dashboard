import os, subprocess, pandas as pd, numpy as np, x2
O,H,L,C,V=(pd.read_pickle(f'{k}.pkl').astype('float64') for k in ('open','high','low','close','volume'))
sig=pd.read_pickle('honmei.pkl'); tick=sorted(set(sig.ticker))
H,L,C,V=H[tick],L[tick],C[tick],V[tick]
on,off,val=x2.squeeze(H,L,C)
fired=(off & on.shift(1).fillna(False).astype(bool)).rolling(5,min_periods=1).max().astype(bool)   # squeeze released in last 5 bars
ud=x2.updn(C,V)
g=lambda P,d,t: P.at[d,t]
sig['sqz_on']=[bool(g(on,d,t)) for d,t in zip(sig.date,sig.ticker)]
sig['sqz_fired']=[bool(g(fired,d,t)) for d,t in zip(sig.date,sig.ticker)]
sig['mom_up']=[(g(val,d,t)>0) and (g(val,d,t)>val[t].shift(1).at[d]) for d,t in zip(sig.date,sig.ticker)]
sig['ud']=[g(ud,d,t) for d,t in zip(sig.date,sig.ticker)]
R=pd.read_pickle('g1.pkl')[['date','t','ret']].rename(columns={'t':'ticker'})
S=sig.merge(R,on=['date','ticker']); S['half']=np.where(S.date<'2020-01-01','2014-19','2020-26'); S.to_pickle('en1.pkl')
def pf(x): return x[x>0].sum()/-x[x<=0].sum()
def line(z): return f'PF{pf(z.ret):5.2f} 平均{z.ret.mean()*100:+5.1f}% n{len(z):4d}'
tests={'スクイーズ中':S.sqz_on,'スクイーズ解放(5日内)':S.sqz_fired,'モメンタム上向き':S.mom_up,'UD比≥1.5':S.ud>=1.5,'UD比≥2':S.ud>=2,'UD比<1.2':S.ud<1.2}
for k,m in tests.items():
    print(f'{k:16s} 該当', ' | '.join(line(S[(S.half==h)&m]) for h in ('2014-19','2020-26')), '|| 非該当', ' | '.join(line(S[(S.half==h)&~m]) for h in ('2014-19','2020-26')))
print('UD比 中央値',S.ud.median().round(2))
