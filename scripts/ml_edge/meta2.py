# Stock-selection study (meta2): meta-labeling / selection rules / pyramiding. Run from a work dir whose parent holds stocks_all.csv.gz and data/*.csv.
import pandas as pd, numpy as np, lightgbm as lgb, sys, warnings; warnings.filterwarnings("ignore")
exec(open("conc2.py").read().split("IS=(")[0])
PERM=int(sys.argv[1]) if len(sys.argv)>1 else 0; TGT=sys.argv[2] if len(sys.argv)>2 else "r"
R1=C.pct_change(fill_method=None)
qq=pd.read_csv("../data/QQQ.csv",parse_dates=["date"]).set_index("date").reindex(C.index)
vix=pd.read_csv("../data/VIX.csv",parse_dates=["date"]).set_index("date").c.reindex(C.index).ffill()
qr=qq.c.pct_change()
beta=R1.rolling(60).cov(qr).div(qr.rolling(60).var(),axis=0)
breadth=(C>SMA200).sum(axis=1)/C.notna().sum(axis=1)
# 1段目: 広めの押し目シグナル
sig=(MOM[126].rank(axis=1,pct=True)>=0.7)&(C>SMA200)&(RSI2<20)&(DV>2e7)
ncand=sig.sum(axis=1)
feat={"mom126r":MOM[126].rank(axis=1,pct=True),"mom63r":MOM[63].rank(axis=1,pct=True),"mom126":MOM[126],
      "r21":C/C.shift(21)-1,"r5":C/C.shift(5)-1,"r1":R1,"rsi2":RSI2,"ibs":IBS,"d200":C/SMA200-1,"d50":C/SMA50-1,
      "vol20":R1.rolling(20).std(),"adr":ADR,"vz":VZ,"hi52":HI52,"beta":beta,
      "gap":O/C.shift(1)-1,"dn3":(R1<0).rolling(3).sum(),"dv":np.log(DV)}
mkt={"q_r5":qq.c/qq.c.shift(5)-1,"q_d200":qq.c/qq.c.rolling(200).mean()-1,"vix":vix,"breadth":breadth,"ncand":ncand,"mkt_on":MKT.astype(float)}
# 取引ラベル: 翌寄りで買い、終値>SMA5 or 10日で翌寄り手仕舞い
idx=C.index; Sv=sig.values; sm5=SMA5.values
ev=[]
for i,j in np.argwhere(Sv):
    if i+12>=len(idx) or np.isnan(On[i+1,j]): continue
    e=On[i+1,j]; x=None
    for k in range(i+1,min(i+11,len(idx)-1)):
        if Cn[k,j]>sm5[k,j] or k-(i+1)+1>=10: x=k; break
    if x is None: continue
    px=On[x+1,j] if not np.isnan(On[x+1,j]) else Cn[x,j]
    ev.append((i,j,px/e-1-0.001,x+1))
E=pd.DataFrame(ev,columns=["i","j","r","xi"])
for k,v in feat.items(): E[k]=v.values[E.i,E.j]
for k,v in mkt.items(): E[k]=v.values[E.i]
# 銘柄の「性格」: その銘柄の過去の押し目取引(決済済み)の平均リターン・勝率
E=E.sort_values("i").reset_index(drop=True)
hist_mean=np.full(len(E),np.nan); hist_n=np.zeros(len(E))
done={}
order=E.sort_values("xi")
for n,(ii,jj) in enumerate(zip(E.i,E.j)):
    pass
tr_by=E.groupby("j")
for j,g in tr_by:
    xs=g.xi.values; rs=g.r.values; ids=g.index.values; ii=g.i.values
    for a in range(len(g)):
        m=xs<ii[a]
        if m.sum()>0: hist_mean[ids[a]]=rs[m].mean(); hist_n[ids[a]]=m.sum()
E["hist_r"]=hist_mean; E["hist_n"]=hist_n
E["date"]=idx[E.i.values]; E["sym"]=C.columns[E.j.values]
E["rk"]=E.groupby("i").r.rank(pct=True)
feats=[c for c in E.columns if c not in("i","j","r","xi","date","sym","rk")]
print("候補取引",len(E),"日数",E.i.nunique(),"平均r",f"{E.r.mean():+.2%}")
# ウォークフォワード
dates=np.sort(E.i.unique()); start=idx.searchsorted(pd.Timestamp("2023-10-01"))
E["p"]=np.nan; rng=np.random.default_rng(PERM); last=None
for i0 in range(start,len(idx),63):
    tr=E[E.xi<i0-1]; te=E[(E.i>=i0)&(E.i<i0+63)]
    if len(te)==0: continue
    y=(tr.rk if TGT=="rk" else tr.r/tr.vol20 if TGT=="rv" else tr.r).values.copy()
    if PERM: y=rng.permutation(y)
    m=lgb.LGBMRegressor(n_estimators=300,learning_rate=0.03,num_leaves=15,min_child_samples=50,subsample=0.8,subsample_freq=1,
                        colsample_bytree=0.7,reg_lambda=5,verbose=-1,n_jobs=4,random_state=PERM).fit(tr[feats],y)
    E.loc[te.index,"p"]=m.predict(te[feats])
O_=E[E.p.notna()].copy()
print(f"OOS {O_.date.min().date()}〜{O_.date.max().date()} 取引候補={len(O_)} 日数={O_.i.nunique()}")
from scipy.stats import spearmanr
ic=O_.groupby("i").apply(lambda g:spearmanr(g.p,g.r)[0] if len(g)>=5 else np.nan).dropna()
print(f"  日内IC={ic.mean():.3f} t={ic.mean()/ic.std()*np.sqrt(len(ic)):.2f} | 全体相関={spearmanr(O_.p,O_.r)[0]:.3f}")
O_["pq"]=pd.qcut(O_.p,5,labels=False)
print("  予測5分位ごとの平均取引リターン:",O_.groupby("pq").r.mean().map(lambda v:f"{v:+.2%}").to_dict(), "勝率:",O_.groupby("pq").r.apply(lambda s:(s>0).mean()).round(2).to_dict())
top=O_.loc[O_.groupby("i").p.idxmax()]; momtop=O_.loc[O_.groupby("i").mom126.idxmax()]
print(f"  各日1位の平均r: AI={top.r.mean():+.2%} 勝率{(top.r>0).mean():.0%} | 6M上昇率1位={momtop.r.mean():+.2%} | 候補平均={O_.groupby('i').r.mean().mean():+.2%}")
O_.to_pickle(f"meta_oos_{TGT}_p{PERM}.pkl")
if not PERM:
    imp=pd.Series(m.feature_importances_,feats).sort_values(ascending=False); print("  重要度:",list(imp.index[:12]))
