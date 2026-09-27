# Concentrated single-stock swing study (conc). Run from a work dir whose parent holds stocks_all.csv.gz and data/QQQ.csv.
import pandas as pd, numpy as np, itertools, sys
S=".."
df=pd.read_csv(f"{S}/stocks_all.csv.gz",parse_dates=["date"])
df=df[~df.sym.isin(["HON","PARA","MRVL","SIRI"])&(df.date>="2021-12-14")]
P={k:df.pivot(index="date",columns="sym",values=k) for k in "ohlcv"}
O,H,L,C,V=P["o"],P["h"],P["l"],P["c"],P["v"]
q=pd.read_csv(f"{S}/data/QQQ.csv",parse_dates=["date"]).set_index("date").c.reindex(C.index)
d=C.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
RSI2=100*up.ewm(alpha=.5).mean()/(up.ewm(alpha=.5).mean()+dn.ewm(alpha=.5).mean())
IBS=(C-L)/(H-L).replace(0,np.nan)
SMA5=C.rolling(5).mean(); SMA200=C.rolling(200).mean()
MOM={n:C/C.shift(n)-1 for n in [63,126]}
MKT=(q>q.rolling(200).mean())
DV=(C*V).rolling(20).mean()
Cn,On,Hn,Ln=C.values,O.values,H.values,L.values
def sim(L_=126,top=0.2,rsi=10,K=2,maxh=10,stop=None,mkt=True,rank="mom",start="2022-10-01",end="2026-09-30",cost=0.001,log=False):
    mom=MOM[L_]; pct=mom.rank(axis=1,pct=True)
    sig=(pct>=1-top)&(C>SMA200)&(RSI2<rsi)&(DV>2e7)
    if mkt: sig=sig&MKT.values[:,None]
    sigv=sig.values; score=(mom if rank=="mom" else -RSI2).values
    idx=C.index; i0=idx.searchsorted(pd.Timestamp(start)); i1=idx.searchsorted(pd.Timestamp(end))
    eq=1.0; pos={}  # j -> (entry_px, entry_i, weight_capital)
    curve=[]; trades=[]
    cash=1.0
    for i in range(i0,min(i1,len(idx)-1)):
        # 1) 寄りで執行: 前日引けで決めた手仕舞い・新規
        # value update at close i
        # exits decided at close i-1 executed at open i
        for j in list(pos):
            e,ei,cap,ex=pos[j]
            if ex:  # exit at open
                px=On[i,j] if not np.isnan(On[i,j]) else Cn[i-1,j]
                r=px/e-1-cost; cash+=cap*(1+r); trades.append((idx[ei],idx[i],C.columns[j],r)); del pos[j]
        # 新規: 前日の引けシグナル
        if i>i0:
            free=K-len(pos)
            if free>0:
                cand=np.where(sigv[i-1])[0]; cand=[j for j in cand if j not in pos and not np.isnan(On[i,j])]
                cand=sorted(cand,key=lambda j:-score[i-1,j])[:free]
                tot=cash+sum(cap*(Cn[i-1,j]/e) for j,(e,ei,cap,ex) in pos.items())
                for j in cand:
                    cap=min(cash,tot/K)
                    if cap<=1e-9: break
                    cash-=cap; pos[j]=[On[i,j],i,cap,False]
        # ストップ(日中) 
        if stop:
            for j in list(pos):
                e,ei,cap,ex=pos[j]
                if not ex and Ln[i,j]<=e*(1+stop):
                    px=min(On[i,j],e*(1+stop)) if ei<i else e*(1+stop)
                    r=px/e-1-cost; cash+=cap*(1+r); trades.append((idx[ei],idx[i],C.columns[j],r)); del pos[j]
        # 引けで手仕舞い判定（翌寄りで執行）
        for j in pos:
            e,ei,cap,ex=pos[j]
            if Cn[i,j]>SMA5.values[i,j] or i-ei+1>=maxh: pos[j][3]=True
        val=cash+sum(cap*(Cn[i,j]/e) for j,(e,ei,cap,ex) in pos.items() if not np.isnan(Cn[i,j]))
        curve.append((idx[i],val))
    eqs=pd.Series(dict(curve)); T=pd.DataFrame(trades,columns=["in","out","sym","r"])
    return eqs,T
def rep(eqs,T,nm):
    y=len(eqs)/252; cagr=eqs.iloc[-1]**(1/y)-1; dd=(eqs/eqs.cummax()-1).min()
    yr=eqs.resample("YE").last().pct_change(); yr.iloc[0]=eqs.resample("YE").last().iloc[0]/eqs.iloc[0]-1
    print(f"{nm:44s} CAGR={cagr:+6.1%} DD={dd:6.1%} 取引={len(T):4d} 勝率={(T.r>0).mean():.0%} 平均={T.r.mean():+.2%} 年別="+" ".join(f"{v:+.0%}" for v in yr.values))
    return cagr,dd
if __name__=="__main__":
    for K in [1,2,3,5]:
        e,T=sim(K=K); rep(e,T,f"基本 K={K}")
