# Stock-selection study (sel): meta-labeling / selection rules / pyramiding. Run from a work dir whose parent holds stocks_all.csv.gz and data/*.csv.
import pandas as pd, numpy as np
O=pd.read_pickle("meta_oos_rk_p0.pkl")
O["aiq"]=O.groupby("i").p.rank(pct=True); O["momq"]=O.groupby("i").mom126.rank(pct=True)
O["combo"]=O.aiq+O.momq
avg=O.groupby("i").r.mean()
def pick(nm,df,col,filt=None):
    d=df if filt is None else df[filt(df)]
    t=d.loc[d.groupby("i")[col].idxmax()].set_index("i")
    ex=t.r-avg.reindex(t.index)
    h=len(t)//2
    print(f"  {nm:36s} 日数={len(t):4d} 平均r={t.r.mean():+.2%} 勝率={(t.r>0).mean():.0%} 候補平均比={ex.mean():+.2%} (t={ex.mean()/ex.std()*np.sqrt(len(ex)):+.2f}) 前半={t.r.iloc[:h].mean():+.2%} 後半={t.r.iloc[h:].mean():+.2%}")
    return t
print("各日1銘柄を選ぶルール (OOS 2023-10〜2026-09, 1取引あたり, コスト込み)")
print(f"  {'候補の平均(ランダム相当)':36s} 平均r={avg.mean():+.2%}")
pick("6M上昇率1位",O,"mom126")
pick("AI(順位学習)1位",O,"p")
pick("AI上位半分の中で6M上昇率1位",O,"mom126",lambda d:d.aiq>=0.5)
pick("AI順位+6M上昇率順位 合計1位",O,"combo")
pick("過去の押し目成績(hist_r)1位 (n>=3)",O,"hist_r",lambda d:d.hist_n>=3)
pick("6M上昇率1位 & QQQ>200日線",O,"mom126",lambda d:d.mkt_on==1)
pick("combo1位 & QQQ>200日線",O,"combo",lambda d:d.mkt_on==1)
pick("6M上昇率1位 & 候補10銘柄以下(静かな日)",O,"mom126",lambda d:d.ncand<=10)
pick("6M上昇率1位 & 候補10銘柄超(全面安の日)",O,"mom126",lambda d:d.ncand>10)
