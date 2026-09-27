# ML edge search (feat). Run from a work dir whose parent holds stocks_all.csv.gz, data/*.csv (QQQ,TQQQ,VIX,US10Y) and macro/*.csv (TradingView daily).
import pandas as pd, numpy as np
S=".."
df=pd.read_csv(f"{S}/stocks_all.csv.gz",parse_dates=["date"])
df=df[~df.sym.isin(["HON","PARA","MRVL","SIRI"]) & ~((df.sym=="TCOM")&(df.date<"2021-03-18"))]
df=df[df.date>="2021-12-14"]
P={k:df.pivot(index="date",columns="sym",values=k) for k in "ohlcv"}
O,H,L,C,V=P["o"],P["h"],P["l"],P["c"],P["v"]
q=pd.read_csv(f"{S}/data/QQQ.csv",parse_dates=[0],index_col=0); q.columns=[c.lower() for c in q.columns]
vix=pd.read_csv(f"{S}/data/VIX.csv",parse_dates=[0],index_col=0); vix.columns=[c.lower() for c in vix.columns]
Q=q["c"].reindex(C.index).ffill(); VX=vix["c"].reindex(C.index).ffill()
R=C.pct_change(fill_method=None); qr=Q.pct_change()
ln=np.log(C)
F={}
for n in [1,5,21,63,126]: F[f"r{n}"]=C/C.shift(n)-1
F["mom12_1"]=C.shift(21)/C.shift(252)-1
F["vol20"]=R.rolling(20).std(); F["vol60"]=R.rolling(60).std()
F["dvol60"]=R.where(R<0).rolling(60,min_periods=20).std()
F["skew60"]=R.rolling(60).skew(); F["max21"]=R.rolling(21).max(); F["min21"]=R.rolling(21).min()
F["hi52"]=C/H.rolling(252).max()-1; F["lo52"]=C/L.rolling(252).min()-1
for n in [10,20,50,200]: F[f"ma{n}"]=C/C.rolling(n).mean()-1
F["ma50_200"]=C.rolling(50).mean()/C.rolling(200).mean()-1
d=C.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
F["rsi2"]=up.ewm(alpha=.5).mean()/(up.ewm(alpha=.5).mean()+dn.ewm(alpha=.5).mean())
F["rsi14"]=up.ewm(alpha=1/14).mean()/(up.ewm(alpha=1/14).mean()+dn.ewm(alpha=1/14).mean())
F["ibs"]=(C-L)/(H-L).replace(0,np.nan)
on=O/C.shift(1)-1; intra=C/O-1
F["overnight21"]=on.rolling(21).sum(); F["intraday21"]=intra.rolling(21).sum()
F["vr5_60"]=np.log(V.rolling(5).mean()/V.rolling(60).mean())
F["dv"]=np.log((C*V).rolling(60).mean())
F["range20"]=((H-L)/C).rolling(20).mean()
cov=R.rolling(60).cov(qr); beta=cov.div(qr.rolling(60).var(),axis=0); F["beta60"]=beta
res=R-beta.shift(1).mul(qr,axis=0); F["resmom63"]=res.rolling(63).sum(); F["resmom21"]=res.rolling(21).sum()
# 決算ギャップ代理: 直近63日で |gap|最大 & 出来高3倍 の日, そのギャップ方向と以後のドリフト
vz=V/V.rolling(60).mean().shift(1)
ev=(on.abs()>0.04)&(vz>2.5)
sig=on.where(ev)
last_gap=sig.ffill(limit=63); F["gap_last"]=last_gap
age=ev.astype(float).replace(0,np.nan); idx=pd.DataFrame(np.arange(len(C))[:,None].repeat(C.shape[1],1),index=C.index,columns=C.columns)
age=(idx-idx.where(ev).ffill()); F["gap_age"]=age.where(age<=63)
F["since_gap"]=(C/C.where(ev).ffill()-1).where(age<=63)
MK={"q_r21":Q/Q.shift(21)-1,"q_ma200":Q/Q.rolling(200).mean()-1,"vix":VX,"q_vol20":qr.rolling(20).std()}
# 目的変数: 翌日寄り→h日後寄り（シグナル確定後に執行）
T={h:O.shift(-(h+1))/O.shift(-1)-1 for h in [5,21]}
import pickle; pickle.dump(dict(F=F,MK=MK,T=T,C=C,O=O),open("raw.pkl","wb"))
print(C.shape)
