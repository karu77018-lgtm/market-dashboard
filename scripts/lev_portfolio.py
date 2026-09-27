#!/usr/bin/env python3
"""lev_rules.py のシグナルを組み合わせた日次ポートフォリオ・シミュレーション

各銘柄1ポジション。ノーポジ時は優先順(BO→PB→MR→IB)で最初に点灯したルールで翌寄りエントリーし、
そのルールの出口で撤退する。CAGR / 最大DD / 在場率 / 年別リターンを Buy&Hold 等と比較。
使い方: python lev_portfolio.py --csv-dir data
"""
import argparse
import numpy as np, pandas as pd
from lev_rules import load_all, build, PAIRS, START, COST

def run(X, rules):
    """rules: [(name, sig, stop|None, exit_bool, maxhold)] → (日次リターン, 在場率, ルール別回数)"""
    o, l, c = X.o.values, X.l.values, X.c.values
    n = len(X); r = np.zeros(n); pos = np.zeros(n); used = {}; i = 0
    while i < n - 1:
        hit = None
        for nm, sig, sp, ex, mh in rules:
            if sig.values[i]:
                s = sp.values[i] if sp is not None else -np.inf
                if o[i + 1] > s: hit = (nm, s, ex.values, mh); break
        if hit is None:
            i += 1; continue
        nm, s, ex, mh = hit; used[nm] = used.get(nm, 0) + 1
        j = i + 1; pos[j] = 1
        if l[j] <= s:
            r[j] = s / o[j] - 1 - 2 * COST; i = j + 1; continue
        r[j] = c[j] / o[j] - 1 - COST
        while True:
            if ex[j] or j - i >= mh:
                if j + 1 < n: r[j + 1] += o[j + 1] / c[j] - 1 - COST
                i = j + 1; break
            j += 1
            if j >= n: i = n; break
            pos[j] = 1
            if l[j] <= s:
                r[j] = min(o[j], s) / c[j - 1] - 1 - COST; i = j + 1; break
            r[j] = c[j] / c[j - 1] - 1
    return pd.Series(r, X.index), pos.mean(), used

def metrics(r):
    eq = (1 + r).cumprod()
    return (eq.iloc[-1] ** (252 / len(r)) - 1, (eq / eq.cummax() - 1).min(),
            r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1))

def rule_sets(X, lev):
    uc = X.u_c; trend = uc > X.u_sma200
    st = X.l_lo5 * 0.995; ex50 = X.c < X.l_sma50
    rs = X.RS if lev == "SOXL" else pd.Series(True, X.index)
    swing_ = [("BO", X.BO & rs, st, ex50, 60), ("PB", X.PB & rs, st, ex50, 60)]
    short = [("MR", X.MR, None, uc > X.u_sma5, 10), ("IB", X.IB, None, uc > X.u_h.shift(), 10)]
    return {"Buy&Hold": None, "200DMA上だけ保有": [("T", trend, None, ~trend, 10**9)],
            "既存PBのみ": [("PB", X.PB, st, ex50, 60)], "BO+PB(+RS)": swing_,
            "短期MR+IB": short, "全部": swing_ + short}

def line(name, r, ex=None):
    cagr, dd, yr = metrics(r)
    exs = f" 在場 {ex * 100:3.0f}%" if ex is not None else ""
    print(f"| {name} | {cagr * 100:.1f}% | {dd * 100:.1f}% |{exs} {int((yr >= 1).sum())}/{len(yr)} | "
          + " ".join(f"{a % 100:02d}:{b * 100:+.0f}" for a, b in yr.items()) + " |")

def main(D):
    res = {}
    for lev, und in PAIRS.items():
        X = build(D, lev, und); X = X[X.index >= START]
        print(f"\n## {lev}\n| set | CAGR | MaxDD | 在場 / 100%超の年 | 年別% |\n|---|---|---|---|---|")
        for k, rules in rule_sets(X, lev).items():
            if rules is None: r, ex = (X.c / X.c.shift() - 1).fillna(0), 1.0
            else: r, ex, _ = run(X, rules)
            res[(lev, k)] = r; line(k, r, ex)
    print("\n## 2銘柄\n| set | CAGR | MaxDD | 100%超の年 | 年別% |\n|---|---|---|---|---|")
    for k in ["Buy&Hold", "200DMA上だけ保有", "全部"]:
        a = res[("TQQQ", k)]; b = res[("SOXL", k)].reindex(a.index).fillna(0)
        line(f"50/50 {k}", (a + b) / 2)
    for k in ["短期MR+IB", "全部"]:
        a = res[("TQQQ", k)]; b = res[("SOXL", k)].reindex(a.index).fillna(0)
        both = (a != 0) & (b != 0)   # 片方だけ点灯なら資金100%, 両方なら50/50（近似・やや楽観的）
        line(f"点灯側に集中 {k}", pd.Series(np.where(both, (a + b) / 2, a + b), a.index))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--csv-dir"); a = ap.parse_args()
    main(load_all(a.csv_dir))
