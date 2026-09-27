# Concentrated single-stock swing study (conc2). Run from a work dir whose parent holds stocks_all.csv.gz and data/QQQ.csv.
import pandas as pd, numpy as np, itertools, sys
exec(open("conc.py").read().split("def sim(")[0])
SMA10=C.rolling(10).mean(); SMA20=C.rolling(20).mean(); SMA50=C.rolling(50).mean()
HH20=H.rolling(20).max().shift(1); RNG10=(H.rolling(10).max()/L.rolling(10).min()-1)
VZ=V/V.rolling(50).mean()
HI52=C/H.rolling(252,min_periods=150).max()
ADR=((H-L)/C).rolling(20).mean()
def run(sigv,score,K,exitf,maxh,stop,start,end,cost=0.001,seed=None):
    idx=C.index; i0=idx.searchsorted(pd.Timestamp(start)); i1=idx.searchsorted(pd.Timestamp(end))
    rng=np.random.default_rng(seed) if seed is not None else None
    pos={}; cash=1.0; curve=[]; trades=[]
    for i in range(i0,min(i1,len(idx)-1)):
        for j in list(pos):
            e,ei,cap,ex=pos[j]
            if ex:
                px=On[i,j] if not np.isnan(On[i,j]) else Cn[i-1,j]
                r=px/e-1-cost; cash+=cap*(1+r); trades.append((idx[ei],idx[i],C.columns[j],r)); del pos[j]
        if i>i0 and K-len(pos)>0:
            cand=[j for j in np.where(sigv[i-1])[0] if j not in pos and not np.isnan(On[i,j])]
            if rng is not None: rng.shuffle(cand)
            else: cand=sorted(cand,key=lambda j:-score[i-1,j])
            tot=cash+sum(cap*(Cn[i-1,j]/e) for j,(e,ei,cap,ex) in pos.items())
            for j in cand[:K-len(pos)]:
                cap=min(cash,tot/K)
                if cap<=1e-9: break
                cash-=cap; pos[j]=[On[i,j],i,cap,False]
        if stop:
            for j in list(pos):
                e,ei,cap,ex=pos[j]
                if not ex and Ln[i,j]<=e*(1+stop):
                    px=min(On[i,j],e*(1+stop)) if not np.isnan(On[i,j]) else e*(1+stop)
                    r=px/e-1-cost; cash+=cap*(1+r); trades.append((idx[ei],idx[i],C.columns[j],r)); del pos[j]
        for j in pos:
            e,ei,cap,ex=pos[j]
            if exitf(i,j) or i-ei+1>=maxh: pos[j][3]=True
        curve.append((idx[i],cash+sum(cap*(Cn[i,j]/e) for j,(e,ei,cap,ex) in pos.items() if not np.isnan(Cn[i,j]))))
    return pd.Series(dict(curve)),pd.DataFrame(trades,columns=["in","out","sym","r"])
def met(eq):
    y=len(eq)/252; return eq.iloc[-1]**(1/y)-1,(eq/eq.cummax()-1).min()
mk=MKT.values[:,None]
# --- 戦略A: 強い銘柄の押し目 (MR) ---
def A(L_=126,top=0.2,rsi=10,mkt=True):
    s=(MOM[L_].rank(axis=1,pct=True)>=1-top)&(C>SMA200)&(RSI2<rsi)&(DV>2e7)
    return (s.values&mk) if mkt else s.values, MOM[L_].values
exA=lambda i,j: Cn[i,j]>SMA5.values[i,j]
# --- 戦略B: 強い銘柄の収縮後ブレイク (トレンドフォロー) ---
def B(L_=126,top=0.1,rng_=0.15,vz=1.5,mkt=True):
    s=(MOM[L_].rank(axis=1,pct=True)>=1-top)&(C>HH20)&(RNG10.shift(1)<rng_)&(VZ>vz)&(C>SMA50)&(DV>2e7)
    return (s.values&mk) if mkt else s.values, MOM[L_].values
exB10=lambda i,j: Cn[i,j]<SMA10.values[i,j]
exB20=lambda i,j: Cn[i,j]<SMA20.values[i,j]
IS=("2022-10-01","2024-07-01"); OOS=("2024-07-01","2026-09-30")
rows=[]
for L_,top,rsi,K,mh in itertools.product([63,126],[0.1,0.2,0.3],[5,10,20],[1,2,3,5],[5,10]):
    s,sc=A(L_,top,rsi); 
    a=met(run(s,sc,K,exA,mh,None,*IS)[0]); b=met(run(s,sc,K,exA,mh,None,*OOS)[0])
    rows.append(("A",f"L{L_} top{top} rsi{rsi} mh{mh}",K,*a,*b))
for L_,top,rg,vz,K,ex,st in itertools.product([63,126],[0.1,0.2],[0.12,0.2],[1.0,1.5],[1,2,3,5],["10","20"],[None,-0.08]):
    s,sc=B(L_,top,rg,vz); f=exB10 if ex=="10" else exB20
    a=met(run(s,sc,K,f,40,st,*IS)[0]); b=met(run(s,sc,K,f,40,st,*OOS)[0])
    rows.append(("B",f"L{L_} top{top} rng{rg} vz{vz} ex{ex} st{st}",K,*a,*b))
R=pd.DataFrame(rows,columns=["fam","p","K","is_cagr","is_dd","oos_cagr","oos_dd"]); R.to_pickle("conc_grid.pkl")
pd.set_option("display.width",200)
for fam in "AB":
    g=R[R.fam==fam]
    print(f"\n== 戦略{fam}: K別 平均(全パラメータ)"); print(g.groupby("K")[["is_cagr","is_dd","oos_cagr","oos_dd"]].median().map(lambda v:f"{v:+.1%}"))
    print(f"  IS上位10 → OOS"); print(g.sort_values("is_cagr",ascending=False).head(10).to_string(float_format=lambda v:f"{v:+.1%}"))
    print(f"  IS-OOS 順位相関 {g.is_cagr.corr(g.oos_cagr,method='spearman'):.2f}")
