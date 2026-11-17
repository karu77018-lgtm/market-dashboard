import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
Y=pd.read_pickle('ftd_events2.pkl')
CAND=['day','pct','volr','vol50','clpos','gap','cushion','fromlow','depth','declen','a200','s200slope','d50','d200','confirm','nprevfail','vix','vixoff','term','cred20','d10_20',
      'updays','lowvol','ema21','a50','gapup','prevday','secup','hyg20','usd20','tlt1','tlt20','aaii_bear','aaii_spread','pc10','md_yoy','cape','opex_wk','earn']
E_,L_=Y[Y.date<'2010-01-01'],Y[Y.date>='2010-01-01']
print('corr among the 6:'); print(Y[['day','updays','prevday','usd20','hyg20','tlt1']].corr(method='spearman').round(2).to_string())
picks=[]
for f in CAND:
    x=E_.dropna(subset=[f])
    if len(x)<40: continue
    binary=x[f].nunique()<=2; cut=0.5 if binary else x[f].median()
    if not binary and (x[f]>cut).sum()<5: cut-=1e-9
    h=x[f]>cut
    d_all=x[h].fake25.mean()-x[~h].fake25.mean()
    ds=[x[(x.tk==t)&h].fake25.mean()-x[(x.tk==t)&~h].fake25.mean() for t in ('QQQ','SPY')]
    if abs(d_all)>=0.10 and all(np.sign(v)==np.sign(d_all) and abs(v)>=0.05 for v in ds):
        picks.append((f,cut,np.sign(d_all),round(d_all*100)))
print('\nselected on 1993-2009 only:',picks)
def score(df):
    s=pd.Series(0.0,index=df.index); n=pd.Series(0,index=df.index)
    for f,cut,sg,_ in picks:
        v=df[f]; m=v.notna(); s[m]+=np.where((v[m]>cut)==(sg>0),1,0); n[m]+=1
    return s/n.replace(0,np.nan)
for nm,df in (('1993-2009 (fit)',E_),('2010-2026 (test)',L_)):
    sc=score(df); q=pd.qcut(sc.rank(method='first'),3,labels=['低','中','高'])
    g=df.groupby(q); print(nm,'騙し率 by score tercile:',(g.fake25.mean()*100).round(0).to_dict(),'n',g.size().to_dict(),'| 60日後中央値',g.f60.median().round(1).to_dict())
# day-count only, for reference, on test
L_=L_.copy(); L_['rd']=(L_.day<=7)|(L_.day>=16); print('day-count rule on 2010-:',(L_.groupby('rd').fake25.mean()*100).round(0).to_dict())
