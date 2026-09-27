# Concentrated single-stock swing study (luck). Run from a work dir whose parent holds stocks_all.csv.gz and data/QQQ.csv.
exec(open("conc2.py").read().split("IS=(")[0])
import numpy as np
full=("2022-10-01","2026-09-30")
for nm,(s,sc),ex,mh,st in [("A 押し目 L126 top0.3 rsi10",A(126,0.3,10),exA,10,None),("B ブレイク L126 top0.1 rng0.12 vz1.5",B(126,0.1,0.12,1.5),exB20,40,-0.08)]:
    for K in [1,3,5]:
        base=met(run(s,sc,K,ex,mh,st,*full)[0])
        rr=[met(run(s,sc,K,ex,mh,st,*full,seed=k)[0]) for k in range(40)]
        c=np.array([x[0] for x in rr]); d=np.array([x[1] for x in rr])
        print(f"{nm} K={K}: 順位付き CAGR={base[0]:+.1%} DD={base[1]:.0%} | 同じシグナルからランダムに選ぶ40通り: CAGR 5%点={np.percentile(c,5):+.1%} 中央={np.median(c):+.1%} 95%点={np.percentile(c,95):+.1%} DD中央={np.median(d):.0%}")
