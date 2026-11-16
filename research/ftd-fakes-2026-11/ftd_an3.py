import pandas as pd, numpy as np
X=pd.read_pickle('ftd_events.pkl'); A=X[X.n_after.notna()|(X.date<'2026-10-01')].copy(); A['half']=np.where(A.date<'2010-01-01','~2009','2010~')
A['risky_day']=(A.day<=7)|(A.day>=16)
alive1=A[(A.why!='a')|(A.n_after>1)].dropna(subset=['p1'])
print('FTD当日×翌日（翌日時点でまだ割れていないもの）: 25日以内の騙し率')
for rd in (True,False):
    for neg in (True,False):
        s=alive1[(alive1.risky_day==rd)&((alive1.p1<0)==neg)]
        print(f"  {'Day4-7/16+' if rd else 'Day8-15  '} × 翌日{'マイナス' if neg else 'プラス  '}: {s.fake25.mean()*100:3.0f}% (n={len(s)}) | ~2009 {s[s.half=='~2009'].fake25.mean()*100:.0f}% 2010~ {s[s.half=='2010~'].fake25.mean()*100:.0f}% | 60日後中央値 {s.f60.median():+.1f}%")
alive3=A[(A.why!='a')|(A.n_after>3)].dropna(subset=['dist3','p1'])
print('3日目時点：翌日マイナス・3日以内の売り抜け日の数（0〜2）')
alive3['warn']=(alive3.p1<0).astype(int)+alive3.dist3.astype(int)
for w,g in alive3.groupby('warn'): print(f"  警告{w}個: 騙し {g.fake25.mean()*100:.0f}% (n={len(g)}) ~2009 {g[g.half=='~2009'].fake25.mean()*100:.0f}% 2010~ {g[g.half=='2010~'].fake25.mean()*100:.0f}% | 60日後中央値 {g.f60.median():+.1f}%")
# what happens to non-fakes: f60 distribution for fake25 vs not
print('騙しでなかったFTDの60日後中央値 %+.1f%% / 騙しだったFTD %+.1f%%'%(A[A.fake25==0].f60.median(),A[A.fake25==1].f60.median()))
cur=X[(X.tk=='QQQ')&(X.date>='2026-11-01')]; print(cur[['tk','date','day','pct','volr','cushion','p1','dist3','why','n_after']].to_string())
import ftd; df,_=ftd.events('QQQ'); print(df.loc['2026-11-04':'2026-11-14',['open','high','low','close','volume']].round(2).to_string())
