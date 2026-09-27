#!/usr/bin/env python3
"""ダブルバガーの「上昇前の顔つき」分析 → スクリーン化 → 未来情報なしの月次バックテスト

手順
  1) 各月末 × 各銘柄で「その後12か月以内に終値が2倍以上」をラベル付け（2022-07〜2025-09）
  2) その時点までの価格だけでテクニカル特徴量を計算し、倍化率を横断5分位で比較（前期/後期で一貫性確認）
  3) テクニカル条件を満たした銘柄について、公表遅れを考慮したファンダ（売上YoY/EPS）を比較
     - ファンダはケース・コントロール抽出（倍化した全銘柄＋倍化しなかった銘柄の無作為抽出）
     - 対照群には逆確率重み（非倍化銘柄数/抽出数）を掛けて母集団推定に戻す
  4) 月末シグナル→翌営業日寄りで買い、1/3/6か月トランシェ保有で評価（往復0.2%）

データ（--dir に置く）
  stocks_all.csv.gz : sym,date,o,h,l,c,v（Webull日足, 分割・配当調整済み）
  fund.txt          : SYM|売上YoY%×16|EPS×16（TradingView 四半期, 古い順, 最新=2026年8月中旬公表と仮定）
                      各四半期の利用可能日 = 最新公表日 − 91日×遡り四半期数 + 30日（保守的バッファ）
ユニバース: 2022年末時点のS&P500（以降の採用銘柄は除外, 以降の除外銘柄は追加）＋2019年時点のNASDAQ100/成長株
既知の限界: 上場廃止銘柄（SIVB等）は取得不可＝生存者バイアス。ファンダは事後修正値の可能性。
"""
import argparse
import numpy as np, pandas as pd

TECH = dict(vol_q=4, rs_q=5)   # ボラ上位40% & 6か月RS上位20% & 50DMA>200DMA
REV_TH = 30                    # 直近四半期 売上YoY >= 30%

def load(d):
    df = pd.read_csv(f"{d}/stocks_all.csv.gz", parse_dates=["date"])
    df = df[~df.sym.isin(["HON", "PARA", "MRVL", "SIRI"]) & ~((df.sym == "TCOM") & (df.date < "2021-03-18"))]
    P = {k: df.pivot(index="date", columns="sym", values=k) for k in "ohlcv"}
    F = {}
    for line in open(f"{d}/fund.txt"):
        s, r, e = line.strip().split("|")
        F[s] = (np.array(r.split(","), float), np.array(e.split(","), float))
    return P, F

def events(P, end="2026-08-31"):
    C = P["c"].loc["2021-06-01":]; H, L, V = (P[k].reindex(C.index) for k in "hlv")
    univ = [s for s in C.columns if s not in ("QQQ", "SPY")]
    f = dict(r6m=C / C.shift(126) - 1, r12m=C / C.shift(252) - 1, off52h=C / H.rolling(252).max() - 1,
             sma50_200=C.rolling(50).mean() / C.rolling(200).mean() - 1,
             vol60=np.log(C).diff().rolling(60).std() * np.sqrt(252),
             tight20=(H.rolling(20).max() - L.rolling(20).min()) / C)
    fmax = C[::-1].rolling(252, min_periods=200).max()[::-1].shift(-1)
    fmin = C[::-1].rolling(252, min_periods=200).min()[::-1].shift(-1)
    me = pd.Series(C.index, C.index).groupby(C.index.to_period("M")).last()
    me = me[(me >= "2022-07-01") & (me <= end)]
    rows = [dict(date=d, sym=s, dbl=fmax.at[d, s] / C.at[d, s] >= 2, half=fmin.at[d, s] / C.at[d, s] <= .5,
                 f12=C.shift(-252).at[d, s] / C.at[d, s] - 1, **{k: v.at[d, s] for k, v in f.items()})
            for d in me for s in univ if pd.notna(C.at[d, s]) and pd.notna(f["r12m"].at[d, s])]
    X = pd.DataFrame(rows)
    for k in ["vol60", "r6m"]:
        X[k + "_q"] = X.groupby("date")[k].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    X["tech"] = (X.vol60_q >= TECH["vol_q"]) & (X.r6m_q >= TECH["rs_q"]) & (X.sma50_200 > 0)
    return X

def add_fund(X, F, latest_pub="2026-08-15"):
    avail = [pd.Timestamp(latest_pub) - pd.Timedelta(days=91 * (15 - i)) + pd.Timedelta(days=30) for i in range(16)]
    lab = X[X.tech & (X.date <= "2025-09-30") & (X.date >= "2022-10-01")].groupby("sym").dbl.any()
    nw = set(lab[~lab].index); w_ctrl = len(nw) / max(1, len(nw & set(F)))
    E = X[X.tech & X.sym.isin(F) & (X.date >= "2023-03-01")].copy()
    def feat(x):
        k = max(i for i in range(16) if avail[i] <= x.date); r, e = F[x.sym]
        return pd.Series(dict(rev=r[k], accel=r[k] - r[k - 1], eps_pos=e[k] > 0))
    E = pd.concat([E, E.apply(feat, axis=1)], axis=1)
    E["w"] = np.where(E.sym.isin(nw), w_ctrl, 1.0)
    return E

def backtest(P, E, sel, H=3, cost=0.002):
    C, O = P["c"], P["o"]
    me = pd.Series(C.index, C.index).groupby(C.index.to_period("M")).last()
    me = me[me >= E.date.min()].tolist()
    nx = lambda d: C.index[min(C.index.get_loc(d) + 1, len(C.index) - 1)]
    tr, out = [], []
    for i, d in enumerate(me[:-1]):
        b, s = nx(d), nx(me[i + 1]); g = E[(E.date == d) & sel]
        tr = (tr + [g if len(g) else None])[-H:]
        rs = []
        for g in tr:
            if g is None: rs.append(0.0); continue
            r = O.loc[s, g.sym].values / O.loc[b, g.sym].values - 1; ok = ~np.isnan(r)
            rs.append(np.average(r[ok], weights=g.w.values[ok]))
        out.append((me[i + 1], np.mean(rs + [0.0] * (H - len(rs))) - cost / H))
    return pd.Series(dict(out))

def summary(r, name):
    eq = (1 + r).cumprod(); yr = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    print(f"| {name} | {(eq.iloc[-1] ** (12 / len(r)) - 1) * 100:.1f}% | {(eq / eq.cummax() - 1).min() * 100:.1f}% | "
          + " ".join(f"{a}:{b * 100:+.0f}" for a, b in yr.items()) + " |")

def main(d):
    P, F = load(d); X = events(P)
    L = X[X.date <= "2025-09-30"].copy(); L["per"] = np.where(L.date < "2024-01-01", "前期", "後期")
    print(f"倍化率: 全体 {L.dbl.mean() * 100:.1f}% / テクニカル条件 {L[L.tech].dbl.mean() * 100:.1f}%")
    E = add_fund(X, F)
    print("| 保有 | 条件 | CAGR | 最大DD | 年別 |\n|---|---|---|---|---|")
    for H in [1, 3, 6]:
        summary(backtest(P, E, pd.Series(True, E.index), H), f"{H}M テクニカルのみ")
        summary(backtest(P, E, E.rev >= REV_TH, H), f"{H}M テク+売上YoY>={REV_TH}%")
    last = E[(E.date == E.date.max()) & (E.rev >= REV_TH)]
    print(f"\n{E.date.max().date()} シグナル:", ", ".join(f"{s}(売上{r:+.0f}%)" for s, r in zip(last.sym, last.rev)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True); main(ap.parse_args().dir)
