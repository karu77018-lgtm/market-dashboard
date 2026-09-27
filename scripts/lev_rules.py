#!/usr/bin/env python3
"""TQQQ / SOXL エントリールール: シグナル判定 + バックテスト

データ取得（どちらか）:
  1) --csv-dir DIR : DIR/{TQQQ,SOXL,QQQ,SOXX,VIX,US10Y}.csv
                     列: date,o,h,l,c,v（TradingView MCPの出力をそのまま保存でOK）
  2) 指定なし      : yfinance で取得（pip install yfinance）

使い方:
  python lev_rules.py                  # 現在シグナル + バックテスト
  python lev_rules.py --csv-dir data   # CSVから
  python lev_rules.py --json out.json  # 結果をJSONでも保存
"""
import argparse, json, sys
import numpy as np, pandas as pd

PAIRS = {"TQQQ": "QQQ", "SOXL": "SOXX"}
YF = {"TQQQ": "TQQQ", "SOXL": "SOXL", "QQQ": "QQQ", "SOXX": "SOXX", "VIX": "^VIX", "US10Y": "^TNX"}
COST = 0.0005          # 片道
RATE_BP = 25           # G2: 10Y 3か月変化の閾値(bp)
EXT = {"TQQQ": 0.10, "SOXL": 0.15}  # G3(参考表示のみ): 原指数200DMA乖離の過熱ライン
START = "2011-01-01"
SPLIT = "2020-01-01"   # IS / OOS 境界


# ---------------- data ----------------
def load_csv(d, s):
    df = pd.read_csv(f"{d}/{s}.csv", parse_dates=["date"]).set_index("date").sort_index()
    return df[["o", "h", "l", "c"] + (["v"] if "v" in df else [])]

def load_yf(s):
    import yfinance as yf
    df = yf.download(YF[s], start="2006-01-01", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["o", "h", "l", "c", "v"]].dropna(subset=["c"])

def load_all(csv_dir):
    f = (lambda s: load_csv(csv_dir, s)) if csv_dir else load_yf
    return {s: f(s) for s in YF}


# ---------------- features ----------------
def build(D, lev, und):
    L, U = D[lev].copy(), D[und].reindex(D[lev].index)
    X = L[["o", "h", "l", "c"]].copy()
    uc = U.c
    X["u_c"], X["u_h"], X["u_l"], X["u_v"] = uc, U.h, U.l, U.v
    X["u_ema21"] = uc.ewm(span=21, adjust=False).mean()
    X["u_sma50"] = uc.rolling(50).mean()
    X["u_sma200"] = uc.rolling(200).mean()
    X["u_200up"] = X.u_sma200 > X.u_sma200.shift(20)
    X["ext200"] = uc / X.u_sma200 - 1
    X["l_sma50"] = L.c.rolling(50).mean()
    X["l_sma100"] = L.c.rolling(100).mean()
    X["l_ema21"] = L.c.ewm(span=21, adjust=False).mean()
    X["l_lo5"] = L.l.rolling(5).min()
    tr = pd.concat([L.h - L.l, (L.h - L.c.shift()).abs(), (L.l - L.c.shift()).abs()], axis=1).max(axis=1)
    X["l_atrp"] = tr.rolling(14).mean() / L.c * 100
    X["l_hi252"] = L.h.rolling(252).max()
    X["vix"] = D["VIX"].c.reindex(X.index).ffill()
    y = D["US10Y"].c.reindex(X.index).ffill()
    if y.median() > 20: y = y / 10  # ^TNXが利回り×10で来た場合の補正
    X["y10"] = y
    X["dy63"] = (y - y.shift(63)) * 100

    # Gates
    X["G1"] = (uc > X.u_sma200) & X.u_200up
    X["G2"] = X.dy63 < RATE_BP

    # ① FTD（O'Neil式）
    lo20 = X.u_l.rolling(20).min()
    hi60 = uc.rolling(60).max()
    days_from_low = X.u_l.rolling(25).apply(lambda a: len(a) - 1 - np.argmin(a), raw=True)
    X["FTD"] = (((lo20 / hi60 - 1) <= -0.08) & days_from_low.between(3, 12)
                & (uc.pct_change() >= 0.012) & (X.u_v > X.u_v.shift())
                & (X.u_l > lo20)).fillna(False)

    # ② 21EMA押し目
    X["PB"] = (X.G1 & X.G2 & (X.u_sma50 > X.u_sma200)
               & (X.u_l.rolling(3).min() <= X.u_ema21 * 1.005)
               & (uc > X.u_ema21) & (uc > X.u_h.shift())).fillna(False)
    X["PB_raw"] = (X.G1 & (X.u_sma50 > X.u_sma200)
                   & (X.u_l.rolling(3).min() <= X.u_ema21 * 1.005)
                   & (uc > X.u_ema21) & (uc > X.u_h.shift())).fillna(False)

    # ③ 短期リバーサル: 原指数3連続安 & 200DMA上 → 原指数終値>5SMAで翌寄り撤退（最大10日, ストップなし）
    d = uc.diff()
    X["u_sma5"] = uc.rolling(5).mean()
    X["MR"] = ((d < 0) & (d.shift() < 0) & (d.shift(2) < 0) & (uc > X.u_sma200)).fillna(False)
    # ③' IBS押し目: 原指数の終値が日中レンジ下位20% & 3日安値更新 & 200DMA上 → 終値>前日高値で翌寄り撤退（最大10日, ストップなし）
    ibs = (uc - X.u_l) / (X.u_h - X.u_l).replace(0, np.nan)
    X["IB"] = ((ibs < 0.2) & (X.u_l < X.u_l.shift().rolling(3).min()) & (uc > X.u_sma200)).fillna(False)
    # ④ 55日高値ブレイク（G1内, 初回ブレイク日）
    hi55 = uc.rolling(55).max()
    X["BO"] = ((uc >= hi55) & (uc.shift() < hi55.shift()) & X.G1).fillna(False)
    # ⑤ 相対強度: SOXX/QQQ が50日平均より上（SOXLのみ採用）
    rs = (D["SOXX"].c / D["QQQ"].c).reindex(X.index)
    X["RS"] = (rs > rs.rolling(50).mean()).fillna(False)
    return X.dropna(subset=["u_sma200"])


# ---------------- backtest ----------------
def swing(X, sig, maxhold=60, stop=True, exit_=None):
    """翌日寄り付きでエントリー / 損切り=lev5日安値×0.995 / 撤退=lev終値<50SMA → 翌寄り
    stop=False で損切りなし、exit_ で撤退条件(bool Series)を差し替え"""
    o, l, c = X.o.values, X.l.values, X.c.values
    S = sig.values
    SP = (X.l_lo5 * 0.995).values if stop else np.full(len(X), -np.inf)
    XS = (X.c < X.l_sma50).values if exit_ is None else exit_.values
    n, i, out = len(X), 1, []
    while i < n - 1:
        if not S[i]:
            i += 1; continue
        ep, sp = o[i + 1], SP[i]
        if not (ep > sp):
            i += 1; continue
        j, px, why = i + 1, None, "open"
        while j < n:
            if l[j] <= sp:
                px = sp if j == i + 1 else min(o[j], sp); why = "stop"; break
            if XS[j] or j - i >= maxhold:
                why = "exit" if XS[j] else "time"
                if j + 1 < n: px, j = o[j + 1], j + 1
                else: px = c[j]
                break
            j += 1
        if px is None: px, j = c[-1], n - 1
        out.append(dict(signal=X.index[i], entry=X.index[i + 1], ep=ep, stop=sp, exit_px=px,
                        ret=px / ep - 1 - 2 * COST, R=(px - ep) / (ep - sp) if stop else np.nan, days=j - i,
                        dy63=X.dy63.iloc[i], why=why))
        i = j + 1
    return pd.DataFrame(out, columns=["signal", "entry", "ep", "stop", "exit_px", "ret", "R", "days", "dy63", "why"])

def stats(T):
    if len(T) == 0: return dict(n=0)
    w = T.ret > 0
    pf = T.ret[w].sum() / -T.ret[~w].sum() if (~w).any() else float("inf")
    return dict(n=int(len(T)), win=round(w.mean() * 100, 1), avg=round(T.ret.mean() * 100, 2),
                avgWin=round(T.ret[w].mean() * 100, 1) if w.any() else 0,
                avgLoss=round(T.ret[~w].mean() * 100, 1) if (~w).any() else 0,
                PF=round(pf, 2), days=round(T.days.mean(), 1))


# ---------------- report ----------------
def mr_trades(X):
    return swing(X, X.MR, maxhold=10, stop=False, exit_=X.u_c > X.u_sma5)

def ib_trades(X):
    return swing(X, X.IB, maxhold=10, stop=False, exit_=X.u_c > X.u_h.shift())

def report(D):
    res = {}
    for lev, und in PAIRS.items():
        X = build(D, lev, und)
        Xs = X[X.index >= START]
        r = X.iloc[-1]
        bt = {}
        for name, col in [("FTD", "FTD"), ("PB(G2あり)", "PB"), ("PB(G2なし)", "PB_raw")]:
            T = swing(Xs, Xs[col])
            bt[name] = {"ALL": stats(T), "IS": stats(T[T.entry < SPLIT]), "OOS": stats(T[T.entry >= SPLIT])}
        Tr = swing(Xs, Xs["PB_raw"])
        bt["PB 金利上昇時"] = stats(Tr[Tr.dy63 >= RATE_BP])
        bt["PB 金利横ばい低下時"] = stats(Tr[Tr.dy63 < RATE_BP])
        Tg = swing(Xs, Xs["PB"]); Tg["ext"] = Xs.ext200.reindex(Tg.signal).values
        bt[f"PB(G2あり) 乖離<{EXT[lev]:.0%}"] = stats(Tg[Tg.ext < EXT[lev]])
        bt[f"PB(G2あり) 乖離>={EXT[lev]:.0%}"] = stats(Tg[Tg.ext >= EXT[lev]])
        for name, T in [("MR 3連続安リバーサル", mr_trades(Xs)), ("IB IBS押し目", ib_trades(Xs)), ("BO 55日高値ブレイク", swing(Xs, Xs.BO))]:
            bt[name] = {"ALL": stats(T), "IS": stats(T[T.entry < SPLIT]), "OOS": stats(T[T.entry >= SPLIT])}
        if lev == "SOXL":
            for nm, col in [("PB", "PB"), ("BO", "BO")]:
                T = swing(Xs, Xs[col]); T["rs"] = Xs.RS.reindex(T.signal).values
                for k, m in [("SOXX優位", T.rs), ("SOXX劣位", ~T.rs.astype(bool))]:
                    bt[f"{nm} & {k}"] = {"IS": stats(T[m & (T.entry < SPLIT)]), "OOS": stats(T[m & (T.entry >= SPLIT)])}

        recent = X[X.index >= X.index[-60]]
        live = swing(X[X.index >= X.index[-80]], X[X.index >= X.index[-80]]["FTD"] | X[X.index >= X.index[-80]]["PB"])
        live = live[live.why == "open"]
        Xl = X[X.index >= X.index[-30]]
        mr_live = mr_trades(Xl); mr_live = mr_live[mr_live.why == "open"]
        res[lev] = dict(
            date=str(X.index[-1].date()), close=round(r.c, 2),
            G1_trend=bool(r.G1), G2_rate=bool(r.G2), G3_not_extended=bool(r.ext200 < EXT[lev]), y10=round(r.y10, 3), dy63_bp=round(r.dy63, 0),
            und_ext200_pct=round(r.ext200 * 100, 1), vix=round(r.vix, 2),
            lev_sma50=round(r.l_sma50, 2), lev_ema21=round(r.l_ema21, 2), lev_sma100=round(r.l_sma100, 2),
            lev_lo5_stop=round(r.l_lo5 * 0.995, 2), lev_atr_pct=round(r.l_atrp, 2),
            lev_from_52wH_pct=round((r.c / r.l_hi252 - 1) * 100, 1),
            signal_today={"FTD": bool(r.FTD), "PB": bool(r.PB), "MR": bool(r.MR), "IB": bool(r.IB), "BO": bool(r.BO)},
            RS_soxx_over_qqq=bool(r.RS),
            recent_MR=[str(d.date()) for d in recent.index[recent.MR]][-5:],
            recent_IB=[str(d.date()) for d in recent.index[recent.IB]][-5:],
            recent_BO=[str(d.date()) for d in recent.index[recent.BO]],
            open_MR=None if mr_live.empty else {k: (str(v.date()) if hasattr(v, "date") else round(float(v), 3))
                                                 for k, v in mr_live.iloc[-1][["signal", "entry", "ep", "ret"]].items()},
            recent_FTD=[str(d.date()) for d in recent.index[recent.FTD]],
            recent_PB=[str(d.date()) for d in recent.index[recent.PB]],
            open_trade=None if live.empty else {k: (str(v.date()) if hasattr(v, "date") else round(float(v), 3))
                                                 for k, v in live.iloc[-1][["signal", "entry", "ep", "stop", "ret"]].items()},
            backtest=bt,
        )
    return res

def print_md(res):
    for lev, r in res.items():
        print(f"\n## {lev}  {r['date']}  close {r['close']}")
        print(f"- G1トレンド: {'OK' if r['G1_trend'] else 'NG'} / G2金利: {'OK' if r['G2_rate'] else 'NG'} "
              f"(10Y {r['y10']}%, 3M {r['dy63_bp']:+.0f}bp) / G3乖離: {'OK' if r['G3_not_extended'] else '過熱(参考)'}")
        print(f"- 原指数200DMA乖離 {r['und_ext200_pct']}% / VIX {r['vix']} / ATR% {r['lev_atr_pct']} / 52wH比 {r['lev_from_52wH_pct']}%")
        print(f"- lev 21EMA {r['lev_ema21']} / 50SMA {r['lev_sma50']} / 100SMA {r['lev_sma100']} / 5日安値ストップ {r['lev_lo5_stop']}")
        print(f"- 本日シグナル {r['signal_today']} / 直近FTD {r['recent_FTD']} / 直近PB {r['recent_PB']}")
        print(f"- 保有中想定トレード {r['open_trade']}")
        print(f"- SOXX/QQQ相対強度(>50日平均) {'SOXX優位' if r['RS_soxx_over_qqq'] else 'QQQ優位'} / 直近MR {r['recent_MR']} / 直近IB {r['recent_IB']} / 直近BO {r['recent_BO']} / MR保有中 {r['open_MR']}")
        print("| setup | 期間 | n | win% | avg% | avgWin | avgLoss | PF | days |")
        print("|---|---|---|---|---|---|---|---|---|")
        for k, v in r["backtest"].items():
            rows = v.items() if "IS" in v else [("-", v)]
            for per, s in rows:
                if s.get("n", 0) == 0: continue
                print(f"| {k} | {per} | {s['n']} | {s['win']} | {s['avg']} | {s['avgWin']} | {s['avgLoss']} | {s['PF']} | {s['days']} |")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir"); ap.add_argument("--json")
    a = ap.parse_args()
    res = report(load_all(a.csv_dir))
    print_md(res)
    if a.json:
        json.dump(res, open(a.json, "w"), ensure_ascii=False, indent=1, default=str)
