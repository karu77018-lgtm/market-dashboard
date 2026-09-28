"""Step 4 prep: robustness of the adopted rule "hold TQQQ while QQQ > SMA(n)".

Sensitivity over SMA length and a hysteresis band, plus the trade list and a
recent-bar indicator dump for cross-checking the Pine implementation.
Writes reports/03_regime_filter.md, sma200_filter_trades.csv, pine_crosscheck.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import backtest as bt
import lib

OUT = lib.ROOT / "reports"
LENS = (100, 150, 200, 250)
BANDS = (0.0, 0.01, 0.02, 0.03)


def target_with_band(qc: np.ndarray, sma: np.ndarray, band: float) -> np.ndarray:
    """Enter when QQQ > SMA*(1+band), exit when QQQ < SMA*(1-band)."""
    out = np.zeros(len(qc), dtype=bool)
    on = False
    for i in range(len(qc)):
        if np.isnan(sma[i]):
            on = False
        elif not on and qc[i] > sma[i] * (1 + band):
            on = True
        elif on and qc[i] < sma[i] * (1 - band):
            on = False
        out[i] = on
    return out


def pct(x, d=1):
    return "–" if pd.isna(x) else f"{x*100:.{d}f}%"


def main():
    df = lib.build()
    d = bt.Data(df)
    spans = {w: d.idx[slice(*d.span(win))] for w, win in bt.WINDOWS.items()}
    qc = df.Q_Close.to_numpy()
    L = ["# TQQQ 乖離スイング — Step 4 準備: 採用ルール「QQQ>SMA200 の間だけTQQQ保有」の頑健性\n"]
    L.append("約定・コストは Step 3 と同じ（終値判定→翌寄り、片道0.05%）。バンド b: QQQ>SMA×(1+b) で買い、QQQ<SMA×(1−b) で手仕舞い。\n")
    rows = []
    for n in LENS:
        sma = df.Q_Close.rolling(n).mean().to_numpy()
        for b in BANDS:
            tgt = target_with_band(qc, sma, b)
            r = dict(n=n, band=b)
            for w, win in bt.WINDOWS.items():
                m = bt.metrics(*bt.run_target(d, tgt, win), spans[w])
                r.update({f"{w}_{k}": m[k] for k in ("CAGR", "MaxDD", "MAR", "Trades", "Exposure")})
            rows.append(r)
    t = pd.DataFrame(rows)
    for w in ("FULL", "IS", "OOS"):
        L.append(f"### {w} MAR（行: SMA期間、列: バンド）\n")
        L.append("| SMA | " + " | ".join(f"b={b:.0%}" for b in BANDS) + " |\n|" + "---|" * (len(BANDS) + 1))
        for n in LENS:
            s = t[t.n == n]
            L.append(f"| {n} | " + " | ".join(f"{v:.2f}" for v in s[f"{w}_MAR"]) + " |")
        L.append("")
    L.append("### 詳細（FULL）\n")
    L.append("| SMA | バンド | CAGR | MaxDD | MAR | 取引数 | 露出率 | IS MAR | OOS MAR |\n|---|---|---|---|---|---|---|---|---|")
    for _, r in t.iterrows():
        L.append(f"| {int(r.n)} | {r.band:.0%} | {pct(r.FULL_CAGR)} | {pct(r.FULL_MaxDD)} | {r.FULL_MAR:.2f} | {int(r.FULL_Trades)} | "
                 f"{pct(r.FULL_Exposure,0)} | {r.IS_MAR:.2f} | {r.OOS_MAR:.2f} |")
    L.append("")
    bh = {w: bt.metrics(*bt.run_target(d, np.ones(len(df), bool), win), spans[w])["MAR"] for w, win in bt.WINDOWS.items()}
    L.append(f"比較: TQQQ B&H の MAR は FULL {bh['FULL']:.2f} / IS {bh['IS']:.2f} / OOS {bh['OOS']:.2f}\n")
    grid = t.set_index(["n", "band"])
    L.append(f"- SMA200・バンド0% の近傍（SMA150–250 × バンド0–2%、9構成）の FULL MAR: 中央値 "
             f"{grid.loc[(slice(150, 250), slice(0, 0.02)), 'FULL_MAR'].median():.2f}、最小 "
             f"{grid.loc[(slice(150, 250), slice(0, 0.02)), 'FULL_MAR'].min():.2f}")
    L.append(f"- 同近傍でFULL MAR が B&H を上回る割合: "
             f"{(grid.loc[(slice(150, 250), slice(0, 0.02)), 'FULL_MAR'] > bh['FULL']).mean():.0%}")
    L.append(f"- 同近傍でIS MAR が B&H を上回る割合: "
             f"{(grid.loc[(slice(150, 250), slice(0, 0.02)), 'IS_MAR'] > bh['IS']).mean():.0%}\n")
    (OUT / "03_regime_filter.md").write_text("\n".join(L), encoding="utf-8")
    t.to_csv(OUT / "regime_filter_grid.csv", index=False)
    print("\n".join(L))

    # trade list of the adopted rule (SMA200, no band) for TradingView cross-checking
    tgt = (df.Q_Close > df.Q_SMA200).to_numpy()
    _, trades, _ = bt.run_target(d, tgt, bt.FULL)
    tl = pd.DataFrame([dict(signal_date=d.idx[x["sig"]].date(), entry_date=d.idx[x["entry"]].date(), entry_px=round(x["px"], 4),
                            exit_date=d.idx[x["exit"]].date(), status=x["why"],
                            ret=round(x["pnl"] / (x["q0"] * x["px"]), 4)) for x in trades])
    tl.to_csv(OUT / "sma200_filter_trades.csv", index=False)

    cols = ["Close", "EMA21", "SMA50", "SMA200", "ATR14", "Dev", "DevPct", "DevZ", "AVWAP_L", "AgeL", "AVWAP_H", "AgeH",
            "Q_Close", "Q_SMA200", "Q_EMA21", "Q_SMA50", "Regime"]
    df[cols].tail(60).round(4).to_csv(OUT / "pine_crosscheck.csv")


if __name__ == "__main__":
    main()
