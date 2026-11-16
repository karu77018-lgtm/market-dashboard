import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
Y=pd.read_pickle('ftd_events2.pkl'); Y=Y[Y.n_after.notna()|(Y.date<'2026-10-01')].copy()
# post: the other index confirms with its own FTD in the next 5 sessions
dates={tk:sorted(Y[Y.tk==tk].date) for tk in ('QQQ','SPY')}
Y['conf_post']=[float(any(0<(x-d).days<=7 for x in dates['SPY' if tk=='QQQ' else 'QQQ'])) for tk,d in zip(Y.tk,Y.date)]
PRE=['updays','lowvol','ema21','a50','gapup','prevday','secup','hyg1','hyg20','usd20','tlt1','tlt20','aaii_bear','aaii_spread','pc10','md_yoy','cape','opex_wk','earn','upshare','upvol','nhnl','nhnl_ch','ttr','ttr_ch','bo_pre','ninety']
POST={'bo_post':5,'b50_post':5,'upvol_post':5,'conf_post':5}
def screen(f,data):
    x=data.dropna(subset=[f]); binary=x[f].nunique()<=2
    cut=0.5 if binary else x[f].median()
    if not binary and (x[f]>cut).sum()<5: cut=x[f].median()-1e-9
    mid=x.date.sort_values().iloc[len(x)//2]
    res={}
    for nm,sub in (('all',x),('QQQ',x[x.tk=='QQQ']),('SPY',x[x.tk=='SPY']),('early',x[x.date<mid]),('late',x[x.date>=mid])):
        h=sub[f]>cut if not binary else sub[f]>=0.5
        res[nm]=(sub[h].fake25.mean()-sub[~h].fake25.mean())*100 if h.sum()>=5 and (~h).sum()>=5 else np.nan
    hi=x[f]>cut if not binary else x[f]>=0.5
    ok=all(np.sign(res[k])==np.sign(res['all']) and abs(res[k])>=5 for k in ('QQQ','SPY','early','late') if not np.isnan(res[k])) and abs(res['all'])>=10
    return dict(f=f,n=len(x),since=x.date.min().year,cut=round(cut,2),hi=round(x[hi].fake25.mean()*100),lo=round(x[~hi].fake25.mean()*100),**{k:(None if np.isnan(v) else round(v)) for k,v in res.items()},ok=ok)
pd.set_option('display.width',250)
print('=== FTD当日（hi=中央値より上・該当）: 25日以内の騙し率 ===  base %.0f%%'%(Y.fake25.mean()*100))
print(pd.DataFrame([screen(f,Y) for f in PRE]).sort_values('all').to_string(index=False))
print('\n=== FTD後5日（5日目時点で生きているもの） ===')
alive=Y[(Y.why!='a')|(Y.n_after>5)]
print(pd.DataFrame([screen(f,alive) for f in POST]).sort_values('all').to_string(index=False))
Y.to_pickle('ftd_events2.pkl')
