# ML edge search (wf). Run from a work dir whose parent holds stocks_all.csv.gz, data/*.csv (QQQ,TQQQ,VIX,US10Y) and macro/*.csv (TradingView daily).
import pandas as pd, numpy as np, pickle, lightgbm as lgb, sys, warnings; warnings.filterwarnings("ignore")
H=int(sys.argv[1]) if len(sys.argv)>1 else 5
PERM=int(sys.argv[2]) if len(sys.argv)>2 else 0
D=pickle.load(open("raw.pkl","rb")); F,MK,T,C=D["F"],D["MK"],D["T"],D["C"]
idx=C.index; step=5 if H==5 else 21
dates=idx[260:-(H+2)][::step]
rows=[]
for d in dates:
    x=pd.DataFrame({k:v.loc[d] for k,v in F.items()})
    x=x[C.loc[d].notna()&x.r21.notna()]
    xr=x.rank(pct=True)          # 横断順位化
    for k,v in MK.items(): xr[k]=v.loc[d]
    y=T[H].loc[d,xr.index]
    xr["y"]=y; xr["yr"]=y.rank(pct=True); xr["date"]=d; xr["sym"]=xr.index
    rows.append(xr.dropna(subset=["y"]))
P=pd.concat(rows,ignore_index=True)
feats=[c for c in P.columns if c not in("y","yr","date","sym")]
ud=sorted(P.date.unique()); start=ud.index(next(d for d in ud if d>=ud[0]+pd.Timedelta(days=365)))
retrain=max(1,40//step*5//5) if H==5 else 2
rng=np.random.default_rng(PERM)
out=[]; model=None
for i in range(start,len(ud)):
    d=ud[i]
    if model is None or (i-start)%retrain==0:
        cut=idx[idx.get_loc(d)-(H+2)]          # パージ: 目的変数の期間が検証日前に終わるものだけ
        tr=P[P.date<=cut]
        yt=tr.yr.values.copy()
        if PERM:  # 日付内で目的変数をシャッフル（偽エッジ検出用）
            yt=tr.groupby("date").yr.transform(lambda s: rng.permutation(s.values)).values
        model=lgb.LGBMRegressor(n_estimators=300,learning_rate=0.03,num_leaves=15,min_child_samples=200,
                                subsample=0.7,subsample_freq=1,colsample_bytree=0.7,reg_lambda=5,verbose=-1,random_state=PERM)
        model.fit(tr[feats],yt)
    te=P[P.date==d].copy(); te["p"]=model.predict(te[feats]); out.append(te[["date","sym","y","p"]+feats])
O=pd.concat(out); O.to_pickle(f"oos_h{H}_p{PERM}.pkl")
def stats(O,col="p",k=0.1):
    g=O.groupby("date")
    ic=g.apply(lambda t:t[col].corr(t.y,method="spearman"))
    top=g.apply(lambda t:t.nlargest(max(5,int(len(t)*k)),col).y.mean()-t.y.mean())
    bot=g.apply(lambda t:t.nsmallest(max(5,int(len(t)*k)),col).y.mean()-t.y.mean())
    return ic,top,bot
ic,top,bot=stats(O)
n=len(ic); per=252/H
print(f"H={H} perm={PERM} OOS {ud[start].date()}〜{ud[-1].date()} 期間数={n}")
print(f"  IC平均={ic.mean():.4f}  t={ic.mean()/ic.std()*np.sqrt(n):.2f}  IC>0率={(ic>0).mean():.0%}")
print(f"  上位10% 超過/期={top.mean():+.3%} t={top.mean()/top.std()*np.sqrt(n):.2f} | 下位10% 超過/期={bot.mean():+.3%} t={bot.mean()/bot.std()*np.sqrt(n):.2f}")
h=n//2; print(f"  前半IC={ic.iloc[:h].mean():.4f} 後半IC={ic.iloc[h:].mean():.4f} | 前半top={top.iloc[:h].mean():+.3%} 後半top={top.iloc[h:].mean():+.3%}")
if not PERM:
    imp=pd.Series(model.feature_importances_,feats).sort_values(ascending=False); print("  重要度上位:",list(imp.index[:10]))
    # 単一ファクター基準
    for f in ["r5","r21","mom12_1","resmom63","hi52","vol60","max21","overnight21","since_gap","ibs","rsi2"]:
        i2=O.groupby("date").apply(lambda t:t[f].corr(t.y,method="spearman")); print(f"   単一 {f:12s} IC={i2.mean():+.4f} t={i2.mean()/i2.std()*np.sqrt(n):+.2f}")
