# ML edge search (regime). Run from a work dir whose parent holds stocks_all.csv.gz, data/*.csv (QQQ,TQQQ,VIX,US10Y) and macro/*.csv (TradingView daily).
import pandas as pd, numpy as np, lightgbm as lgb, sys, warnings; warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
S=".."
def ld(p):
    d=pd.read_csv(p,parse_dates=["date"]).drop_duplicates("date").set_index("date"); return d
Q=ld(f"{S}/data/QQQ.csv"); TQ=ld(f"{S}/data/TQQQ.csv")
X={s:ld(f"{S}/macro/{s}.csv")["c"] for s in ["HYG","IEF","SPY","RSP","XLU","IWM","XLY","XLP","GLD","VIX3M","HG1","DXY","XLF"]}
X["VIX"]=ld(f"{S}/data/VIX.csv")["c"]; X["TNX"]=ld(f"{S}/data/US10Y.csv")["c"]
idx=Q.index[(Q.index>="2010-06-01")]
c=Q.c.reindex(idx); M={k:v.reindex(idx).ffill() for k,v in X.items()}
r=c.pct_change()
f={}
for n in [5,21,63,126,252]: f[f"q_r{n}"]=c/c.shift(n)-1
for n in [20,50,200]: f[f"q_ma{n}"]=c/c.rolling(n).mean()-1
f["q_vol20"]=r.rolling(20).std(); f["q_vol60"]=r.rolling(60).std(); f["q_volr"]=f["q_vol20"]/f["q_vol60"]
f["q_dd"]=c/c.rolling(252).max()-1
d=c.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
f["q_rsi2"]=up.ewm(alpha=.5).mean()/(up.ewm(alpha=.5).mean()+dn.ewm(alpha=.5).mean())
f["q_rsi14"]=up.ewm(alpha=1/14).mean()/(up.ewm(alpha=1/14).mean()+dn.ewm(alpha=1/14).mean())
V=M["VIX"]; f["vix"]=V; f["vix_ts"]=V/M["VIX3M"]; f["vix_ch5"]=V/V.shift(5)-1; f["vix_pct"]=V.rolling(252).rank(pct=True)
def rel(a,b,n): return (M[a]/M[b])/(M[a]/M[b]).shift(n)-1
f["credit21"]=rel("HYG","IEF",21); f["credit63"]=rel("HYG","IEF",63)
f["credit_ma50"]=(M["HYG"]/M["IEF"])/(M["HYG"]/M["IEF"]).rolling(50).mean()-1
f["breadth63"]=rel("RSP","SPY",63); f["small63"]=rel("IWM","SPY",63); f["small21"]=rel("IWM","SPY",21)
f["disc_stap63"]=rel("XLY","XLP",63); f["util21"]=rel("XLU","SPY",21); f["fin63"]=rel("XLF","SPY",63)
f["gold63"]=M["GLD"]/M["GLD"].shift(63)-1; f["cu_au63"]=rel("HG1","GLD",63); f["dxy63"]=M["DXY"]/M["DXY"].shift(63)-1
f["tnx"]=M["TNX"]; f["tnx_ch63"]=M["TNX"]-M["TNX"].shift(63)
f["dom"]=pd.Series(idx.day,idx); f["tom"]=pd.Series(((idx.day>=25)|(idx.day<=3)).astype(int),idx)
F=pd.DataFrame(f)
# 執行: 引けでシグナル → 翌日寄りで売買（寄り→寄りのリターン）
qo=Q.o.reindex(idx); to=TQ.o.reindex(idx)
qret=qo.shift(-2)/qo.shift(-1)-1; tret=to.shift(-2)/to.shift(-1)-1
H=int(sys.argv[1]) if len(sys.argv)>1 else 10; PERM=int(sys.argv[2]) if len(sys.argv)>2 else 0
y=(qo.shift(-(H+1))/qo.shift(-1)-1)
ok=F.notna().all(axis=1)&y.notna()
dates=idx[ok.values]
start=dates[dates>="2015-01-01"][0]
rng=np.random.default_rng(PERM)
pr=pd.Series(np.nan,idx); prl=pd.Series(np.nan,idx); model=None; last=None
test=idx[(idx>=start)&F.notna().all(axis=1).values]
for d in test:
    if last is None or idx.get_loc(d)-idx.get_loc(last)>=63:
        cut=idx[idx.get_loc(d)-(H+2)]
        tr=dates[dates<=cut]; yt=(y[tr]>0).astype(int).values
        if PERM: yt=rng.permutation(yt)
        model=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.02,num_leaves=7,min_child_samples=100,subsample=0.7,
              subsample_freq=1,colsample_bytree=0.6,reg_lambda=10,verbose=-1,n_jobs=4,random_state=PERM).fit(F.loc[tr],yt)
        lr=make_pipeline(StandardScaler(),LogisticRegression(C=0.05,max_iter=2000)).fit(F.loc[tr],yt)
        base=np.quantile(model.predict_proba(F.loc[tr])[:,1],0.25); basel=np.quantile(lr.predict_proba(F.loc[tr])[:,1],0.25)
        last=d
    blk=test[(test>=d)][:1]
    pr[d]=model.predict_proba(F.loc[[d]])[0,1]; prl[d]=lr.predict_proba(F.loc[[d]])[0,1]
pd.DataFrame({"p_gbm":pr,"p_lr":prl,"tret":tret,"qret":qret,"y":y}).loc[test].to_pickle(f"regime_h{H}_p{PERM}.pkl")
T=pd.DataFrame({"p":pr,"pl":prl,"y":y,"tret":tret,"qret":qret}).loc[test].dropna(subset=["tret"])
from scipy.stats import spearmanr
print(f"H={H} perm={PERM} OOS {test[0].date()}〜{test[-1].date()}  AUC近似: GBM IC={spearmanr(T.p,T.y)[0]:.3f} LR IC={spearmanr(T.pl,T.y)[0]:.3f}")
def perf(pos,ret,nm,cost=0.0005):
    pos=pos.fillna(0); sw=pos.diff().abs().fillna(0); rr=pos*ret-sw*cost
    eq=(1+rr).cumprod(); yrs=len(rr)/252; dd=(eq/eq.cummax()-1).min()
    yr=(1+rr).groupby(rr.index.year).prod()-1
    print(f"  {nm:30s} CAGR={eq.iloc[-1]**(1/yrs)-1:+6.1%} 最大DD={dd:6.1%} 保有率={pos.mean():.0%} 年間売買={sw.sum()/yrs:4.0f}回 最悪年={yr.min():+.0%} 負け年={int((yr<0).sum())}/{len(yr)}")
    return yr
Y={}
Y["BH"]=perf(pd.Series(1.0,T.index),T.tret,"TQQQ 買い持ち")
Y["ma200"]=perf((F.q_ma200>0).astype(float).reindex(T.index),T.tret,"TQQQ QQQ>200日線")
Y["vts"]=perf((F.vix_ts<1).astype(float).reindex(T.index),T.tret,"TQQQ VIX<VIX3M")
for q in [0.4,0.5,0.55]:
    Y[f"g{q}"]=perf((T.p>q).astype(float),T.tret,f"TQQQ GBM p>{q}")
    Y[f"l{q}"]=perf((T.pl>q).astype(float),T.tret,f"TQQQ LR  p>{q}")
if not PERM:
    print(pd.DataFrame(Y).map(lambda v:f"{v:+.0%}").to_string())
    imp=pd.Series(model.feature_importances_,F.columns).sort_values(ascending=False); print("重要度:",list(imp.index[:12]))
