"""What F1-F3 say about the index and the swing entries (local panel 2013-2026)."""
import pandas as pd, numpy as np
F=pd.read_pickle('fseries.pkl')
q=pd.read_csv('ftd_QQQ.csv',parse_dates=['date']).drop_duplicates('date').set_index('date').close.reindex(F.index)
c=q.to_numpy(); n=len(c)
def fwd(k): return pd.Series([c[i+k]/c[i]-1 if i+k<n else np.nan for i in range(n)],F.index)
def mdd(k): return pd.Series([c[i+1:i+k+1].min()/c[i]-1 if i+k<n else np.nan for i in range(n)],F.index)
X=F.copy(); X['r20']=fwd(20); X['r60']=fwd(60); X['r120']=fwd(120); X['dd60']=mdd(60)
X['half']=np.where(X.index<'2020-01-01','2013-19','2020-26')
TH={'f1':(0.20,0.30),'f2':(0.25,0.40),'f3':(0.40,0.60)}
def st(v,w,b): return np.where(v>=b,'警戒',np.where(v>=w,'注意','平常'))
for k,(w,b) in TH.items(): X['s'+k]=st(X[k],w,b)
print('time share %:'); print(pd.DataFrame({k:X['s'+k].value_counts(normalize=True)*100 for k in TH}).round(0))
def tab(by):
    g=X.groupby(['half',by])
    return pd.DataFrame({'日数':g.size(),'r20':g.r20.mean()*100,'r60':g.r60.mean()*100,'r120':g.r120.mean()*100,'DD10%率':g.dd60.apply(lambda x:(x<=-0.10).mean()*100)}).round(1)
for k in TH: print('\n==',k); print(tab('s'+k).to_string())
# quintiles of each lamp
for k in TH:
    X['q'+k]=pd.qcut(X[k].rank(method='first'),5,labels=[1,2,3,4,5])
    g=X.groupby(['half','q'+k],observed=True)
    print('\n== quintile',k); print(pd.DataFrame({'lo':g[k].min().round(2),'r60':g.r60.mean()*100,'DD10':g.dd60.apply(lambda x:(x<=-0.1).mean()*100)}).round(1).unstack(0).to_string())
X.to_pickle('fx.pkl')
