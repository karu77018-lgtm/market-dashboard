# ML edge search (volt). Run from a work dir whose parent holds stocks_all.csv.gz, data/*.csv (QQQ,TQQQ,VIX,US10Y) and macro/*.csv (TradingView daily).
import pandas as pd, numpy as np
S=".."
def ld(p): return pd.read_csv(p,parse_dates=["date"]).drop_duplicates("date").set_index("date")
Q=ld(f"{S}/data/QQQ.csv"); T=ld(f"{S}/data/TQQQ.csv"); idx=T.index[T.index>="2011-01-01"]
q=Q.reindex(idx); t=T.reindex(idx)
tr=t.c.pct_change(); qr=q.c.pct_change()
# 夜間/日中の分解
qon=q.o/q.c.shift(1)-1; qid=q.c/q.o-1; ton=t.o/t.c.shift(1)-1; tid=t.c/t.o-1
def st(r,nm):
    r=r.dropna(); eq=(1+r).cumprod(); y=len(r)/252
    print(f"  {nm:34s} CAGR={eq.iloc[-1]**(1/y)-1:+7.1%} 年率ボラ={r.std()*np.sqrt(252):5.1%} 最大DD={(eq/eq.cummax()-1).min():6.1%}")
print("== 夜間 vs 日中 (2011〜)"); st(qon,"QQQ 夜間のみ(引け→寄り)"); st(qid,"QQQ 日中のみ(寄り→引け)"); st(ton,"TQQQ 夜間のみ"); st(tid,"TQQQ 日中のみ"); st(ton-0.0004,"TQQQ 夜間のみ 往復4bp控除")
st(tr,"TQQQ 買い持ち")
print("== ボラティリティ・ターゲット (TQQQ比率 w=min(1,目標/予想ボラ), 残り現金, 前日までの情報で決定)")
cash=0.0
for span in [10,20]:
    vol=(tr.ewm(span=span).std()*np.sqrt(252)).shift(1)     # 前日までで推定 → 当日引け→翌引け に適用するため 1日ずらし
    for tgt in [0.3,0.45,0.6]:
        w=(tgt/vol).clip(upper=1.0)
        w=w.where((w-w.shift(1)).abs()>0.1).ffill()   # 10%以上変化時のみリバランス
        for trend in [False,True]:
            ww=w*((q.c/q.c.rolling(200).mean()>1).shift(1).astype(float)) if trend else w
            sw=ww.diff().abs().fillna(0)
            r=ww*tr+(1-ww)*cash/252-sw*0.0005
            st(r,f"span{span} 目標{int(tgt*100)}%{' +200日線' if trend else ''} 平均w={ww.mean():.2f}")
