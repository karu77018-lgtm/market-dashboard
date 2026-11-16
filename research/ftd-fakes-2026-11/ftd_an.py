import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
X=pd.read_pickle('ftd_events.pkl'); X=X[X.n_after.notna()|(X.date<'2026-10-01')].copy()
X['half']=np.where(X.date<'2010-01-01','~2009','2010~')
FE=['day','pct','volr','vol50','clpos','gap','cushion','fromlow','depth','declen','a200','s200slope','d50','d200','confirm','nprevfail','vix','vixoff','term','iwm','rsp','cred20','d10_20','b50','b50ch','nh']
base=X.fake25.mean()
rows=[]
for f in FE:
    x=X.dropna(subset=[f])
    if x[f].nunique()<=2:
        cut=0.5
    else:
        cut=x[f].median()
    hi=x[f]>cut if x[f].nunique()>2 else x[f]>=0.5
    def rate(m): return x[m].fake25.mean()*100
    cells={}
    for nm,sub in (('all',x),('QQQ',x[x.tk=='QQQ']),('SPY',x[x.tk=='SPY']),('~2009',x[x.half=='~2009']),('2010~',x[x.half=='2010~'])):
        h=(sub[f]>cut) if x[f].nunique()>2 else (sub[f]>=0.5)
        cells[nm]=(sub[h].fake25.mean()-sub[~h].fake25.mean())*100 if h.sum()>=5 and (~h).sum()>=5 else np.nan
    same=all(np.sign(cells[k])==np.sign(cells['all']) for k in ('QQQ','SPY','~2009','2010~') if not np.isnan(cells[k]))
    rows.append(dict(f=f,n=len(x),cut=round(cut,2),hi=round(x[hi].fake25.mean()*100),lo=round(x[~hi].fake25.mean()*100),**{k:round(v) if not np.isnan(v) else None for k,v in cells.items()},consistent=same and abs(cells['all'])>=10 and min(abs(cells[k]) for k in ('QQQ','SPY','~2009','2010~') if not np.isnan(cells[k]))>=5))
R=pd.DataFrame(rows).sort_values('all'); pd.set_option('display.width',250)
print(f'base fake25 {base*100:.0f}%  (hi = above median / yes)'); print(R.to_string(index=False))
R.to_pickle('ftd_screen.pkl')
