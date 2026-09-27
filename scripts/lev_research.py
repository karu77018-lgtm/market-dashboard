#!/usr/bin/env python3
"""lev_rules.py の新ルール(MR/BO/RS)の頑健性チェック

- ランダムエントリー(同頻度・同出口)との比較: エントリー条件自体に優位性があるか
- パラメータ近傍: 連続安日数 2-4 × 撤退SMA 3/5/10、ブレイク期間 20/55/100/252
使い方: python lev_research.py --csv-dir data
"""
import argparse
import numpy as np, pandas as pd
from lev_rules import load_all, build, swing, stats, PAIRS, START, SPLIT

def fmt(T):
    s = stats(T)
    return f"{s.get('avg', 0):6.2f}/{s.get('PF', 0):5.2f}/{s.get('n', 0):4d}"

def row(name, T):
    print(f"| {name} | {fmt(T[T.entry < SPLIT])} | {fmt(T[T.entry >= SPLIT])} |")

def rand(X, base, sig, reps=200, seed=0, **kw):
    rng = np.random.default_rng(seed); p = (sig & base).mean() / base.mean()
    return pd.concat([swing(X, pd.Series(base.values & (rng.random(len(X)) < p), X.index), **kw) for _ in range(reps)])

def main(D):
    for lev, und in PAIRS.items():
        X = build(D, lev, und); X = X[X.index >= START]
        uc, d, trend = X.u_c, X.u_c.diff(), X.u_c > X.u_sma200
        print(f"\n## {lev}  (avg% / PF / n)\n| setup | IS | OOS |\n|---|---|---|")
        for k in [2, 3, 4]:
            ddk = pd.Series(np.all([d.shift(i).values < 0 for i in range(k)], axis=0), X.index) & trend
            for e in [3, 5, 10]:
                row(f"MR {k}連続安 exit>{e}SMA", swing(X, ddk, maxhold=10, stop=False, exit_=uc > uc.rolling(e).mean()))
        row("MR ランダム(200DMA上) exit>5SMA", rand(X, trend, X.MR, maxhold=10, stop=False, exit_=uc > X.u_sma5))
        for N in [20, 55, 100, 252]:
            hi = uc.rolling(N).max()
            row(f"BO {N}日高値", swing(X, (uc >= hi) & (uc.shift() < hi.shift()) & X.G1))
        row("BO/PB ランダム(G1内) 同出口", rand(X, X.G1, X.BO))
        row("PB(G2あり)", swing(X, X.PB))
        for nm, col in [("PB", "PB"), ("BO", "BO")]:
            row(f"{nm} & SOXX優位", swing(X, X[col] & X.RS)); row(f"{nm} & SOXX劣位", swing(X, X[col] & ~X.RS))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--csv-dir"); a = ap.parse_args()
    main(load_all(a.csv_dir))
