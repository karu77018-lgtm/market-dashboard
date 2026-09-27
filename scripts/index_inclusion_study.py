#!/usr/bin/env python3
"""S&P500 採用「前」の顔つき研究 → 未来情報なしの候補スクリーン → トランシェ・バックテスト

問い: 採用時点で既にダブルバガーになっているなら、その前（採用の12か月前）に何が見えていたか？

手順
  1) イベントスタディ: 2023〜2025-09 の新規採用（adds.csv）について採用日前後のリターンを確認
  2) パネル: 2022-12〜2024-09 の各月末 × 非S&P500銘柄（推定時価総額 >= 50億$）
     ラベル = その後365日以内に採用されたか / 12か月後リターン
     特徴量 = 推定時価総額 ÷ その時点の採用基準（時価総額下限）, 12M/6Mリターン, 50>200DMA 等
  3) スクリーン「基準超 & 12M +50%以上 & 50DMA>200DMA」内で、その時点で入手可能な
     GAAP EPS から TTM黒字 / 直近1年での黒字転換 を判定し、採用率・将来リターンを比較
  4) 毎月末に新トランシェ（資金の1/12）を等金額で買い12か月保有（採用後も保有 / 採用日に売却）
  5) 上位寄与銘柄の除外（leave-one-out）と、直近月末時点の候補一覧

データ（--dir に置く）
  stocks_big.csv.gz : sym,date,o,h,l,c,v（Webull日足, 分割・配当調整済み）
  mcap.csv          : sym,mcap（取得時点=2026-09の時価総額。過去は 株価比 × 現在時価総額 で推定）
  adds.csv          : sym,eff（S&P500 採用の効力発生日, 2023-03〜2025-09）
  sp500.txt         : 2022年頃のS&P500構成銘柄（既存メンバーをパネルから除外するため）
  eps.txt           : SYM|四半期 希薄化EPS（古い順, 最新=2026Q2）。四半期末+75日で公表済とみなす
  profitable.txt    : 期間中ずっと黒字と公知の銘柄（EPS未取得分の仮定。結果の解釈に注意）
既知の限界
  - 時価総額は「株数一定」の近似（大幅な増資・自社株買い銘柄は誤差大, AMC/MSTRは除外）
  - 採用基準は概略値（14.5B→15.8B→18.0B→20.5B）。浮動株・流動性・セクターバランス・委員会裁量は未反映
  - 上場廃止銘柄は取得不可＝生存者バイアス（ただしプールは現時点20億$以上なので「その後下落した銘柄」も含む）
  - EPSは事後修正値の可能性。黒字転換サンプルは13〜15銘柄と少なく、少数の大当たり（PLTR/HOOD/APP）に依存
"""
import argparse
import numpy as np, pandas as pd

EXCL = {"EPAM", "CE", "MOH", "CAG", "LW", "ENPH", "PAYC", "WBA", "AMC", "MSTR", "CHTRP", "FCNCP", "FCNCO",
        "FCNCB", "CMSA", "CMSD", "FWONA", "IEP", "PFH", "PRS", "FLG", "RKT"}   # 旧メンバー/優先株/株数変動大
INELIGIBLE = {"ET", "QSR", "SCCO", "QXO", "AU", "SN", "RPRX"}                  # MLP・外国籍・データ欠損
LATEST_Q = pd.Period("2026Q2")


def thr(d):
    """S&P500 採用基準の時価総額下限（おおよそ）"""
    return (14.5e9 if d < pd.Timestamp("2023-07-01") else 15.8e9 if d < pd.Timestamp("2024-01-01")
            else 18.0e9 if d < pd.Timestamp("2025-01-01") else 20.5e9)


def load(d):
    df = pd.read_csv(f"{d}/stocks_big.csv.gz", parse_dates=["date"])
    C = df.pivot(index="date", columns="sym", values="c").loc["2021-12-14":]
    H = df.pivot(index="date", columns="sym", values="h").reindex(C.index)
    A = pd.read_csv(f"{d}/adds.csv", parse_dates=["eff"])
    addd = dict(zip(A.sym, A.eff))
    mc = pd.read_csv(f"{d}/mcap.csv").set_index("sym").mcap
    sp22 = set(open(f"{d}/sp500.txt").read().split()) - set(addd) | EXCL
    syms = [s for s in mc.index if s in C and C[s].notna().sum() > 300 and s not in sp22]
    MC = C[syms].div(C[syms].ffill().iloc[-1]) * mc[syms]
    eps = {}
    for line in open(f"{d}/eps.txt"):
        s, v = line.strip().split("|")
        e = [float(x) if x not in ("", "nan") else np.nan for x in v.split(",")]
        if len(e) > len(eps.get(s, [])):
            eps[s] = e
    prof = set(open(f"{d}/profitable.txt").read().split())
    return C, H, MC, addd, eps, prof


def pit_eps(s, d, eps, prof):
    """d 時点で入手可能な四半期EPSから TTM・直近Q・黒字転換 を算出（未来情報なし）"""
    if s in prof:
        return dict(ttm=1.0, lastq=1.0, turn=False)
    if s not in eps:
        return dict(ttm=np.nan, lastq=np.nan, turn=False)
    e = eps[s]; n = len(e)
    av = [e[k] for k in range(n)
          if (LATEST_Q - (n - 1 - k)).end_time.normalize() + pd.Timedelta(days=75) <= d and not np.isnan(e[k])]
    if len(av) < 2:
        return dict(ttm=np.nan, lastq=np.nan, turn=False)
    ttm = sum(av[-4:]) * 4 / len(av[-4:])
    prev = sum(av[-8:-4]) * 4 / len(av[-8:-4]) if len(av) > 4 else av[0] * 4
    return dict(ttm=ttm, lastq=av[-1], turn=(ttm > 0 and prev <= 0))


def features(C, H):
    return dict(r6m=C / C.shift(126) - 1, r12m=C / C.shift(252) - 1,
                trend=C.rolling(50).mean() > C.rolling(200).mean(), off52h=C / H.rolling(252).max() - 1)


def event_study(C, addd):
    print("== 1) 採用イベント: 効力発生日から見たリターン（中央値）")
    rows = []
    for s, e in addd.items():
        if s not in C or e > C.index[-1]:
            continue
        i = C.index.searchsorted(e); p = C[s]
        r = {k: (p.iloc[i] / p.iloc[i - n] - 1) if i - n >= 0 and pd.notna(p.iloc[i - n]) else np.nan
             for k, n in [("-24M", 504), ("-12M", 252), ("-6M", 126)]}
        r["+12M"] = p.iloc[i + 252] / p.iloc[i] - 1 if i + 252 < len(p) else np.nan
        rows.append(r)
    E = pd.DataFrame(rows)
    print("  ", {k: f"{v:+.0%}" for k, v in E.median().items()}, f"n={len(E)}",
          f"| 採用前24Mで2倍以上: {(E['-24M'] >= 1).sum()}/{E['-24M'].notna().sum()}")


def panel(C, H, MC, addd):
    F = features(C, H); fwd = C.shift(-252) / C - 1
    me = pd.Series(C.index, C.index).groupby(C.index.to_period("M")).last()
    me = me[(me >= "2022-12-01") & (me <= "2024-09-30")]
    rows = []
    for d in me:
        for s in MC.columns:
            m = MC.at[d, s]
            if pd.isna(m) or m < 5e9 or (s in addd and addd[s] <= d):
                continue
            rows.append(dict(date=d, sym=s, ratio=m / thr(d),
                             added=(s in addd) and (addd[s] <= d + pd.Timedelta(days=365)),
                             f12=fwd.at[d, s], **{k: v.at[d, s] for k, v in F.items()}))
    return pd.DataFrame(rows).dropna(subset=["r12m"])


def show(X, nm, m):
    g = X[m]
    print(f"  {nm:34s} n={len(g):5d} 銘柄={g.sym.nunique():3d} 1年内採用率={g.added.mean():6.1%}"
          f"  12M後 中央={g.f12.median():+6.1%} 平均={g.f12.mean():+6.1%}")


def tranche_bt(C, X, sel, addd, nm, sell_on_add=False, hold=252):
    """毎月末に資金1/12を等金額で買い、hold営業日バイ&ホールド（該当なし月は現金）"""
    C = C.ffill(); me = sorted(X.date.unique()); D = C.index[C.index >= me[0]]
    paths, tr = [], []
    for d in me:
        ss = sel[sel.date == d].sym.tolist()
        seg = D[D.get_loc(d):min(D.get_loc(d) + hold, len(D) - 1) + 1]
        if not ss:
            paths.append(pd.Series(1.0, index=seg)); continue
        px = C.loc[seg, ss] / C.loc[d, ss]
        if sell_on_add:
            for s in ss:
                if s in addd and d < addd[s] <= seg[-1]:
                    k = seg.searchsorted(addd[s]); px.loc[seg[k:], s] = px[s].iloc[k]
        p = px.mean(axis=1); paths.append(p); tr.append(p.iloc[-1] - 1)
    dr = pd.concat([p.pct_change() for p in paths], axis=1).mean(axis=1).fillna(0)
    eq = (1 + dr).cumprod(); tr = pd.Series(tr)
    print(f"  {nm:34s} CAGR={eq.iloc[-1] ** (252 / len(eq)) - 1:+6.1%} 最大DD={(eq / eq.cummax() - 1).min():6.1%}"
          f" トランシェ12M 中央={tr.median():+6.1%} 平均={tr.mean():+6.1%} 勝率={(tr > 0).mean():4.0%} (n={len(tr)})")


def current(C, H, MC, addd, eps, prof):
    F = features(C, H); d = C.index[-1]
    rows = []
    for s in MC.columns:
        if s in addd or s in INELIGIBLE or pd.isna(MC.at[d, s]):
            continue
        r = MC.at[d, s] / thr(d)
        if r >= 1 and F["r12m"].at[d, s] >= 0.5 and F["trend"].at[d, s]:
            q = pit_eps(s, d, eps, prof)
            rows.append(dict(sym=s, ratio=round(r, 2), r12m=f"{F['r12m'].at[d, s]:+.0%}",
                             ttm_eps=round(q["ttm"], 2), turn=q["turn"]))
    R = pd.DataFrame(rows).sort_values(["turn", "ttm_eps"], ascending=False)
    print(f"== 5) {d.date()} 時点の候補（未採用・適格と思われるもの。2025-10以降の採用有無は要確認）")
    print(R.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    C, H, MC, addd, eps, prof = load(a.dir)
    event_study(C, addd)

    X = panel(C, H, MC, addd)
    print(f"\n== 2) パネル {len(X)} 銘柄月, {X.sym.nunique()} 銘柄, 基本採用率 {X.added.mean():.2%}")
    show(X, "全体", X.f12.notna() | True)
    for lo, hi in [(0, .8), (.8, 1.2), (1.2, 2), (2, 99)]:
        show(X, f"時価総額/基準 {lo}〜{hi}", X.ratio.between(lo, hi, inclusive="left"))
    scr = (X.ratio >= 1) & (X.r12m >= .5) & X.trend & ~X.sym.isin(INELIGIBLE)
    show(X, "スクリーン: 基準超&12M+50%&トレンド", scr)

    Y = X[scr].copy()
    Y = Y.join(pd.DataFrame([pit_eps(s, d, eps, prof) for s, d in zip(Y.sym, Y.date)], index=Y.index))
    Y = Y[Y.ttm.notna()]
    turn = Y.turn | ((Y.ttm <= 0) & (Y.lastq > 0))
    print("\n== 3) スクリーン内の利益状態（その時点で公表済みのEPSのみ）")
    show(Y, "TTM黒字", Y.ttm > 0)
    show(Y, "TTM赤字", Y.ttm <= 0)
    show(Y, "直近1年で黒字転換", Y.turn)
    show(Y, "黒字転換（途上=TTM赤字&直近Q黒字 含む）", turn)
    ok = [(s, pit_eps(s, e - pd.Timedelta(days=1), eps, prof)["ttm"]) for s, e in addd.items()]
    ok = [t for s, t in ok if pd.notna(t)]
    print(f"  参考: 採用直前にTTM黒字だった採用銘柄 {sum(t > 0 for t in ok)}/{len(ok)}")

    for sa in (False, True):
        print(f"\n== 4) 12か月トランシェ（{'採用日に売却' if sa else '採用後も保有'}）")
        tranche_bt(C, X, X, addd, "プール全体(等金額)", sa)
        tranche_bt(C, X, Y, addd, "スクリーン", sa)
        tranche_bt(C, X, Y[Y.ttm > 0], addd, "スクリーン & TTM黒字", sa)
        tranche_bt(C, X, Y[turn], addd, "スクリーン & 黒字転換(途上含む)", sa)
    print("\n  leave-one-out（黒字転換, 採用後も保有）")
    for ex in (["PLTR"], ["HOOD"], ["APP"], ["PLTR", "HOOD", "APP"]):
        tranche_bt(C, X, Y[turn & ~Y.sym.isin(ex)], addd, "除外: " + ",".join(ex))
    print()
    current(C, H, MC, addd, eps, prof)


if __name__ == "__main__":
    main()
