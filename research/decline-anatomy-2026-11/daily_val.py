import pandas as pd, numpy as np
W=pd.read_pickle('weekly_state.pkl')
FE=['dd','r63','r252','v200','rv20','vix','sox','spx','small','eqw','gv','dfn','fin','ene','sec50','d10','cred','usd']
OUT=['f20','f60','f120','f250']
def nearest(i, pool_end, k=3, gap=26):
    """top-k analog weeks for row i among rows < pool_end, one per 26-week block, z by pool stats"""
    P=W.iloc[:pool_end]; mu,sd=P[FE].mean(),P[FE].std()
    Z=(P[FE]-mu)/sd; z=(W.iloc[i][FE]-mu)/sd
    m=Z.notna()&z.notna().values
    d=np.sqrt((((Z-z)**2).where(m)).sum(axis=1)/m.sum(axis=1)); d=d[m.sum(axis=1)>=12].sort_values()
    picks=[]
    for t,v in d.items():
        if all(abs((t-p).days)>gap*7 for p,_ in picks): picks.append((t,v))
        if len(picks)==k: break
    return picks
# validation: from 2008 on, every 4th week, past-only pool ending 52 weeks before
rows=[]
for i in range(len(W)):
    t=W.index[i]
    if t<pd.Timestamp('2008-01-01') or i%4: continue
    pe=i-52
    pk=nearest(i,pe); 
    r={'t':t}
    for o in OUT:
        past=W.iloc[:pe][o].dropna()
        r[o]=W.iloc[i][o]; r[o+'_base']=past.mean(); r[o+'_knn']=np.nanmean([W.loc[p,o] for p,_ in pk])
    r['top']=pk[0][0]; r['d']=pk[0][1]; rows.append(r)
R=pd.DataFrame(rows).set_index('t')
for o in OUT:
    x=R[[o,o+'_base',o+'_knn']].dropna()
    print(f"{o}: n={len(x)} MAE knn {(x[o+'_knn']-x[o]).abs().mean():.1f} vs base {(x[o+'_base']-x[o]).abs().mean():.1f} | spearman(knn,actual) {x[o+'_knn'].corr(x[o],method='spearman'):+.2f} | 2008-16 {x[:'2016'][o+'_knn'].corr(x[:'2016'][o],method='spearman'):+.2f} 2017- {x['2017':][o+'_knn'].corr(x['2017':][o],method='spearman'):+.2f}")
# stability: weekly top analog for the last 30 weeks using full pool minus last 52 weeks
n=len(W); print('\nweek -> top3 analogs (pool excludes the last 52 weeks):')
for i in range(n-12,n):
    pk=nearest(i,n-52); print(W.index[i].date(), ' | '.join(f"{p.year}-{p.month:02d} ({d:.2f})" for p,d in pk))
# how often does the top-1 analog change week to week (pool fixed)
tops=[nearest(i,n-52,k=1)[0][0] for i in range(n-60,n)]
same=sum(abs((a-b).days)<=60 for a,b in zip(tops,tops[1:])); print('weeks where top-1 stays within 2 months of last week:',same,'/',len(tops)-1)
# sanity: known dates
for d in ('2008-10-10','2020-03-20','2021-11-19','2022-06-17','2024-08-02','2025-04-04'):
    i=W.index.get_indexer([pd.Timestamp(d)],method='nearest')[0]; pk=nearest(i,max(52,i-52)) 
    print('check',d,'->',' | '.join(f"{p.year}-{p.month:02d}" for p,_ in pk))
