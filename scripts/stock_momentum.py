#!/usr/bin/env python3
"""個別株モメンタム・ローテーションの検証（2020年以降に毎年100%は可能か）

ユニバースは「2019年末時点で知り得た」銘柄に限定（後知恵バイアス対策）:
  A = 2019年末のNASDAQ-100構成銘柄 / B = 2019年時点の人気成長株（その後暴落した銘柄も含む）
  ※ 上場廃止銘柄（買収・破綻: XLNX, ATVI, CTXS, NVTA, TWTR 等）はデータ取得不可 → 生存者バイアスが残る

ルール: 期末(週/月)の終値で、価格>5・20日平均売買代金>$20M・終値>50DMA>200DMA の銘柄を
        lb日リターンで順位付けし上位N銘柄を等金額で翌寄りに買う。QQQ<200DMAなら現金（mfilt）。
データ: --csv 長形式 sym,date,o,h,l,c,v（Webull get_stock_bars の出力を変換したもの）
使い方: python stock_momentum.py --csv stocks.csv.gz [--grid] [--repro]
"""
import argparse, itertools
from collections import Counter
import numpy as np, pandas as pd

A = ("AAPL MSFT AMZN GOOGL META INTC CSCO CMCSA PEP ADBE NVDA NFLX PYPL COST AMGN TXN AVGO CHTR QCOM GILD "
     "SBUX TMUS MDLZ INTU BKNG ADP ISRG VRTX CSX MU BIIB AMD ILMN AMAT REGN LRCX ADSK JD MELI MAR ROST KHC EXC "
     "CTSH XEL ORLY BIDU MNST LULU EBAY NTES IDXX KLAC VRSK CTAS NXPI PAYX PCAR WTW WDAY SNPS DLTR CDNS FAST "
     "ALGN CPRT VRSN ULTA INCY MCHP CHKP SWKS TTWO NTAP BMRN EXPE UAL TSLA HAS JBHT DXCM FOXA LBTYK TCOM AAL ASML").split()
B = ("SHOP ROKU TTD ZM PTON CRWD OKTA TWLO XYZ DOCU ZS NET DDOG MDB ESTC TEAM SNAP UBER LYFT PINS SPOT ETSY W "
     "CVNA ENPH SEDG PLUG FSLY BYND SE TDOC CHGG APPS PAYC HUBS NOW FVRR BABA IQ NIO SPCE TLRY CGC ACB AMRN GH "
     "SFIX FIVN RNG VEEV").split()
COST = 0.001  # 片道

def load(path):
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[~((df.sym == "TCOM") & (df.date < "2021-03-18"))]  # ADR比率変更前の未調整データを除外
    P = {k: df.pivot(index="date", columns="sym", values=k) for k in "ocv"}
    return P["o"], P["c"], P["v"]

class Engine:
    def __init__(self, O, C, V):
        self.O, self.C = O, C
        q = C["QQQ"]; self.mkt = q > q.rolling(200).mean()
        self.dv = (C * V).rolling(20).mean()
        self.univ = [s for s in A + B if s in C]

    def ranks(self, univ, lb, d):
        c = self.C[univ]
        ok = (c > 5) & (self.dv[univ] > 2e7) & (c > c.rolling(50).mean()) & (c.rolling(50).mean() > c.rolling(200).mean())
        m = (c / c.shift(lb) - 1).loc[d]
        return m[ok.loc[d]].dropna().sort_values(ascending=False)

    def run(self, univ, N=2, lb=63, reb="M", mfilt=True, start="2020-01-01", end=None):
        c, o = self.C[univ], self.O[univ]
        mom = c / c.shift(lb) - 1
        ok = (c > 5) & (self.dv[univ] > 2e7) & (c > c.rolling(50).mean()) & (c.rolling(50).mean() > c.rolling(200).mean())
        idx = c.index[(c.index >= start) & ((c.index <= end) if end else True)]
        per = pd.Series(idx, idx).dt.to_period(reb)
        rebd = set(idx[(per != per.shift(-1)).values])
        w = pd.Series(0.0, index=univ); rets, hold = [], []
        for t, d in enumerate(idx[:-1]):
            nxt = idx[t + 1]; nw = w
            if d in rebd:
                nw = pd.Series(0.0, index=univ)
                if not mfilt or self.mkt[d]:
                    m = mom.loc[d][ok.loc[d]].dropna().sort_values(ascending=False)
                    pick = m.index[:N][m.iloc[:N] > 0]
                    nw[pick] = 1 / N
                hold.append((nxt, tuple(nw[nw > 0].index)))
            gap = (o.loc[nxt] / c.loc[d] - 1).fillna(0); intra = (c.loc[nxt] / o.loc[nxt] - 1).fillna(0)
            full = (c.loc[nxt] / c.loc[d] - 1).fillna(0); same = np.minimum(w, nw)
            r = (same * full).sum() + ((w - same) * gap).sum() + ((nw - same) * intra).sum() - COST * np.abs(nw - w).sum()
            rets.append((nxt, r)); w = nw
        return pd.Series(dict(rets)), hold

def metrics(r):
    eq = (1 + r).cumprod()
    return (eq.iloc[-1] ** (252 / len(r)) - 1, (eq / eq.cummax() - 1).min(),
            r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1))

def grid(E):
    res = []
    for N, lb, reb, mf in itertools.product([1, 2, 3, 5, 10], [21, 63, 126, 252], ["W", "M"], [True, False]):
        c, dd, yr = metrics(E.run(E.univ, N, lb, reb, mf)[0])
        res.append(dict(N=N, lb=lb, reb=reb, mf=mf, CAGR=round(c * 100, 1), DD=round(dd * 100, 1),
                        y100=int((yr >= 1).sum()), **{str(a): round(b * 100) for a, b in yr.items()}))
    R = pd.DataFrame(res).sort_values("CAGR", ascending=False)
    print(R.to_string(index=False))
    print(f"\nCAGR中央値 {R.CAGR.median():.1f}% / 全年100%超の設定 {(R.y100 == len(R.columns) - 7).sum()}個")

def repro(E, N, lb, reb, mf, seed=0):
    rng = np.random.default_rng(seed)
    r, hold = E.run(E.univ, N, lb, reb, mf); c, dd, yr = metrics(r)
    print(f"N={N} lb={lb} {reb} mfilt={mf}: 2020- CAGR {c*100:.1f}% DD {dd*100:.1f}% 年別 {dict((a, round(b*100)) for a, b in yr.items())}")
    c2, dd2, _ = metrics(E.run(E.univ, N, lb, reb, mf, start="2018-03-01", end="2019-12-31")[0])
    print(f"  事前期間2018-19: CAGR {c2*100:.1f}% DD {dd2*100:.1f}%")
    cA = metrics(E.run([s for s in A if s in E.C], N, lb, reb, mf)[0])[0]
    cB = metrics(E.run([s for s in B if s in E.C], N, lb, reb, mf)[0])[0]
    print(f"  Aのみ {cA*100:.1f}% / Bのみ {cB*100:.1f}%")
    cs = np.array([metrics(E.run(list(rng.choice(E.univ, int(len(E.univ) * .7), replace=False)), N, lb, reb, mf)[0])[0] * 100
                   for _ in range(30)])
    print(f"  30%ランダム除外×30: 中央値 {np.median(cs):.1f}% 範囲 {cs.min():.1f}〜{cs.max():.1f}%")
    print("  よく保有:", Counter(s for _, h in hold for s in h).most_common(8))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", required=True)
    ap.add_argument("--grid", action="store_true"); ap.add_argument("--repro", action="store_true")
    a = ap.parse_args(); E = Engine(*load(a.csv))
    if a.grid: grid(E)
    if a.repro: repro(E, 2, 63, "M", True)
    d = E.C.index[-1]
    print(f"\n{d.date()} QQQ>200DMA={bool(E.mkt[d])} 63日モメンタム上位:",
          [(k, round(v * 100)) for k, v in E.ranks(E.univ, 63, d).head(5).items()])
