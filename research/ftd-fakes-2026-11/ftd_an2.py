import pandas as pd, numpy as np
X=pd.read_pickle('ftd_events.pkl'); X=X[X.n_after.notna()|(X.date<'2026-10-01')].copy(); X['half']=np.where(X.date<'2010-01-01','~2009','2010~')
X['dayb']=pd.cut(X.day,[3,4,5,7,10,15,400],labels=['4','5','6-7','8-10','11-15','16+'])
g=X.groupby('dayb',observed=True); print(pd.DataFrame({'n':g.size(),'fake25%':g.fake25.mean()*100,'fake10%':g.fake10.mean()*100,'f25med':g.f25.median(),'f60med':g.f60.median()}).round(0).to_string())
for h,gg in X.groupby('half'): print(h,(gg.groupby('dayb',observed=True).fake25.mean()*100).round(0).to_dict())
X['pctb']=pd.cut(X.pct,[1.25,1.5,2,3,99],labels=['1.25-1.5','1.5-2','2-3','3+']); print((X.groupby('pctb',observed=True).fake25.agg(['size','mean'])*[1,100]).round(0).to_string())
print('confirm (other index FTD within 5 days):',(X.groupby(['confirm','half']).fake25.agg(['size','mean'])).round(2).to_string())
# post-FTD early signs: among events NOT yet invalidated by day k, P(fake25)
print('\n=== FTD後の早期サイン：その時点でまだ割れていないFTDのうち、25日以内に騙しになった割合 ===')
def alive(k): return X[(X.n_after.isna())|(X.n_after>k)|(X.why!='a')]
for sig,k,lab in (('below_ftdclose2',2,'2日後の終値がFTD日の終値より下'),('p1',1,'翌日の騰落'),('nohigher3',3,'3日以内にFTD日の終値を一度も上回らない'),('undercut3',3,'3日以内に日中でFTD日の安値を割る（終値では割れず）'),('dist3',3,'3日以内に売り抜け日（下げ・出来高増）'),('down1pct3',3,'3日以内に−1%以上の下げ'),('p5',5,'5日後の騰落')):
    A=alive(k).dropna(subset=[sig])
    if sig in ('p1','p5'):
        m=A[sig]<0; name=lab+'がマイナス'
    else:
        m=A[sig]>=0.5; name=lab
    def s(a,b): return f"{a.fake25.mean()*100:3.0f}% (n={len(a)}) vs {b.fake25.mean()*100:3.0f}% (n={len(b)})"
    parts=[]
    for nm,sub in (('全体',A),('QQQ',A[A.tk=='QQQ']),('SPY',A[A.tk=='SPY']),('~2009',A[A.half=='~2009']),('2010~',A[A.half=='2010~'])):
        mm=m.loc[sub.index]; parts.append(f"{nm} {sub[mm].fake25.mean()*100:.0f}/{sub[~mm].fake25.mean()*100:.0f}")
    print(f"- {name}（{k}日目時点）: 該当 {s(A[m],A[~m])} | "+' '.join(parts))
