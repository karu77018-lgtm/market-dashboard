import pandas as pd, numpy as np
F=pd.read_pickle('episodes_x.pkl'); F=F.rename(columns={'gold_x':'gold'}).drop(columns=['gold_y'],errors='ignore'); cur=F.iloc[-1]; P=F.iloc[:-1].copy(); P=P[pd.to_datetime(P['T'])<pd.Timestamp('2026-01-01')].reset_index(drop=True)
FAM={'速さ・値動きの形':['days','maxday','bounce','downshare','rv20','qvol'],
     '恐怖・オプション':['vix','dvix','skew','term','vvix'],
     '何が売られたか':['sox','soft','small','spx','gv','eqw','dfn','fin','ene','secup','sec50','secdisp'],
     '金利・信用':['d10','d2y','d3m','curve','cred','dnfci','nfci','baalvl'],
     '景気・金融政策':['fed6m','fedlvl','curve_pk','inv18','sahm','cpi'],
     '他の資産・海外':['usd','jpy','wti','copper','gold','tlt','intl','efa','btc'],
     '位置・暦':['runup','run3y','v200','since','nprev2y','pres','month']}
ALL=[f for v in FAM.values() for f in v]
mu,sd=P[ALL].mean(),P[ALL].std(); z=(cur[ALL].astype(float)-mu)/sd
rank=lambda f: (P[f].dropna()<cur[f]).mean()*100
print('n episodes',len(P))
for fam,fs in FAM.items():
    print('\n['+fam+']')
    for f in fs:
        if pd.isna(cur[f]): continue
        print(f"  {f:9s} now {cur[f]:8.1f} | past median {P[f].median():7.1f} (n={P[f].notna().sum():2d}) z {z[f]:+.1f} pctile {rank(f):3.0f}{'  <<<' if abs(z[f])>=1.5 else ''}")
# predictive screen: two halves by time, same sign and |r|>=0.3 in both
OUT=['more','f60','f120','f250']; res=[]
for f in ALL:
    x=P[[f]+OUT].dropna(subset=[f])
    if len(x)<16 or x[f].nunique()<4: continue
    h=len(x)//2; a,b=x.iloc[:h],x.iloc[h:]
    for o in OUT:
        ra,rb,rall=a[f].corr(a[o],method='spearman'),b[f].corr(b[o],method='spearman'),x[f].corr(x[o],method='spearman')
        res.append((f,o,len(x),rall,ra,rb,(np.sign(ra)==np.sign(rb)) and min(abs(ra),abs(rb))>=0.3))
S=pd.DataFrame(res,columns=['factor','outcome','n','r_all','r_first','r_second','pass'])
print('\ntests',len(S),'passed',int(S['pass'].sum()),'(by chance alone roughly',round(len(S)*0.06,1),')')
print(S[S['pass']].round(2).sort_values(['factor','outcome']).to_string(index=False))
# recession dimension
R=P.dropna(subset=['rec12'])
g=R.groupby('rec12'); print('\nrecession within 12 months (known only afterwards):'); print(pd.DataFrame({'n':g.size(),'more_med':g.more.median(),'P(more<=-10)%':g.more.apply(lambda s:(s<=-10).mean()*100),'f120_med':g.f120.median(),'f250_med':g.f250.median()}).round(1).to_string())
print('recession cases:',[(str(a)[:7],b) for a,b in zip(R[R.rec12==1].peak,R[R.rec12==1].more)])
for nm,m in (('逆イールド経験(18か月内)',P.inv18==1),('失業率上昇 sahm>=0.3',P.sahm>=0.3),('利下げ中 fed6m<=-25',P.fed6m<=-25),('利上げ中 fed6m>=25',P.fed6m>=25),('信用拡大 cred>=15',P.cred>=15),('3年で+150%超 run3y',P.run3y>=150),('2年内に調整3回以上',P.nprev2y>=3),('セクター6以上が上昇',P.secup>=6),('中間選挙年',P.pres==2)):
    a,b=P[m],P[~m & m.notna()]
    print(f"{nm:22s} yes n={len(a):2d} 景気後退 {a.rec12.mean()*100:3.0f}% more中央値 {a.more.median():6.1f} P(-10%超) {(a.more<=-10).mean()*100:3.0f}% f120中央値 {a.f120.median():5.1f} | no n={len(b):2d} 後退 {b.rec12.mean()*100:3.0f}% {b.more.median():6.1f} {(b.more<=-10).mean()*100:3.0f}% {b.f120.median():5.1f}")
print('\ncurrent flags:',{k:cur[k] for k in ('inv18','sahm','fed6m','cred','run3y','nprev2y','secup','pres','gv','eqw','sec50')})
# analogs with expanded features (1999+ full where available)
USE=['days','vix','rv20','runup','run3y','v200','sox','small','spx','gv','eqw','dfn','fin','ene','secup','secdisp','d10','cred','fed6m','curve_pk','sahm','cpi','usd','jpy','intl','nprev2y']
Q=P.dropna(subset=[u for u in USE if u not in ('gv','eqw')]).copy()
Zq=(Q[USE]-Q[USE].mean())/Q[USE].std(); zc=(cur[USE].astype(float)-Q[USE].mean())/Q[USE].std()
def dist(a,b):
    m=a.notna()&b.notna(); return np.sqrt(((a[m]-b[m])**2).mean())
Q['dist']=Zq.apply(lambda r: dist(r,zc),axis=1)
print('\nexpanded analogs (n=%d, 1999+):'%len(Q)); print(Q.sort_values('dist').head(6)[['peak','dist','runup','run3y','secup','gv','dfn','fin','d10','cred','fed6m','sahm','more','f60','f120','f250']].round(1).to_string())
