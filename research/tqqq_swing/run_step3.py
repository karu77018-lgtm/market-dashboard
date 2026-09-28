"""Step 3 runner: full grid, walk-forward selection, top rules, figures.

Writes reports/02_backtest.md, reports/grid.csv and reports/fig_*.png.
"""
from __future__ import annotations

import itertools

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

import backtest as bt
import lib

OUT = lib.ROOT / "reports"
OUT.mkdir(exist_ok=True)
MIN_IS_TRADES = 15

# reference palette (light mode), see dataviz skill
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
DIVERGING = LinearSegmentedColormap.from_list("div", ["#b83232", "#e34948", "#f0efec", "#5598e7", "#1c5cab"])


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


plt.rcParams.update({"font.family": ["IPAGothic", "DejaVu Sans"], "axes.unicode_minus": False,
                     "figure.facecolor": SURF, "text.color": INK, "axes.labelcolor": INK2})


def pct(x, d=1):
    return "–" if x is None or pd.isna(x) else f"{x*100:.{d}f}%"


def num(x, d=2):
    return "–" if x is None or pd.isna(x) else f"{x:.{d}f}"


# ---------------------------------------------------------------- grid
def run_grid(d: bt.Data, sigs: dict) -> pd.DataFrame:
    rows = []
    exits = bt.exit_grid()
    spans = {w: d.idx[slice(*d.span(win))] for w, win in bt.WINDOWS.items()}
    for key, entry in sigs.items():
        fam, src, k1 = key
        for ex in exits:
            for sizing in ("full", "risk1"):
                for w, win in bt.WINDOWS.items():
                    eq, tr, held = bt.run(d, entry, src, ex, sizing, win)
                    m = bt.metrics(eq, tr, held, spans[w])
                    rows.append(dict(fam=fam, src=src, k1=k1, k2=ex.k2, k3=ex.k3, stop=ex.stop, n=ex.n,
                                     sizing=sizing, win=w, **m))
    g = pd.DataFrame(rows)
    for c in ("k1", "k2", "k3"):
        g[c] = g[c].astype(float).fillna(-1.0)  # -1 = parameter not used
    return g


PARAM_AXES = {"k1": list(bt.K1), "k2": list(bt.K2), "k3": list(bt.K3), "stop": list(bt.STOPS), "n": list(bt.NS)}


def _key(v):
    return -1.0 if v is None or (isinstance(v, float) and np.isnan(v)) else v


def robust_scores(g_is: pd.DataFrame) -> pd.Series:
    """Median IS MAR over the config and its one-step neighbours (one parameter moved by one grid step)."""
    lut = {}
    for i, r in g_is.iterrows():
        lut[(r.fam, r.src, _key(r.k1), _key(r.k2), _key(r.k3), r.stop, r.n)] = r.MAR
    out = {}
    for i, r in g_is.iterrows():
        base = dict(k1=_key(r.k1), k2=_key(r.k2), k3=_key(r.k3), stop=r.stop, n=r.n)
        vals = [r.MAR]
        for ax, grid in PARAM_AXES.items():
            if ax == "k1" and r.fam != "A":
                continue
            gk = [_key(v) for v in grid]
            j = gk.index(base[ax])
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(gk):
                    nb = dict(base, **{ax: gk[jj]})
                    k = (r.fam, r.src, nb["k1"], nb["k2"], nb["k3"], nb["stop"], nb["n"])
                    if k in lut:
                        vals.append(lut[k])
        out[i] = np.nanmedian(vals)
    return pd.Series(out)


def cfg_label(r) -> str:
    fam = {"A": "A押し目", "B": "B AVWAP", "C": "C投げ売り"}[r.fam] + ("[QQQ]" if r.src == "Q" else "")
    f = lambda v: "–" if v == -1 else f"{v:g}"
    k1 = f" k1={f(r.k1)}" if r.fam == "A" else ""
    return f"{fam}{k1} / k2={f(r.k2)} k3={f(r.k3)} {r.stop} N={int(r.n)}"


def to_exit(r) -> bt.Exit:
    nz = lambda v: None if v == -1 else float(v)
    return bt.Exit(nz(r.k2), nz(r.k3), r.stop, int(r.n))


def sig_key(r):
    return (r.fam, r.src, None if r.k1 == -1 else float(r.k1))


# ---------------------------------------------------------------- reporting helpers
MCOLS = ["CAGR", "MaxDD", "MAR", "Trades", "Win", "PF", "AvgHold", "Exposure", "ExpR"]
MHDR = "| CAGR | MaxDD | MAR | 取引数 | 勝率 | PF | 平均保有日 | 露出率 | 期待値(R) |"


def mrow(m) -> str:
    return (f"| {pct(m['CAGR'])} | {pct(m['MaxDD'])} | {num(m['MAR'])} | {int(m['Trades'])} | {pct(m['Win'],0)} | "
            f"{num(m['PF'])} | {num(m['AvgHold'],1)} | {pct(m['Exposure'],0)} | {num(m['ExpR'])} |")


def yearly(eq: pd.Series) -> pd.Series:
    ye = eq.groupby(eq.index.year).last()
    prev = ye.shift(1)
    prev.iloc[0] = 1.0
    return ye / prev - 1


def regime_daily(eq: pd.Series, regime: pd.Series) -> pd.Series:
    """Annualised log return earned on days of each regime (regime known at prior close)."""
    lr = np.log(eq).diff().fillna(np.log(eq.iloc[0]))
    reg = regime.shift(1).reindex(eq.index)
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return lr.groupby(reg).sum() / years


def trade_table(trades, d: bt.Data) -> pd.DataFrame:
    t = pd.DataFrame(trades)
    if t.empty:
        return t
    t["entry_date"] = d.idx[t.entry]
    t["exit_date"] = d.idx[t.exit]
    t["R"] = t.pnl / t.risk
    t["ret"] = t.pnl / (t.q0 * t.px)
    return t


# ---------------------------------------------------------------- figures
def fig_equity(curves: dict[str, pd.Series], path):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
    for ax in (a1, a2):
        style(ax)
    for i, (name, s) in enumerate(curves.items()):
        col = SERIES[i]
        a1.plot(s.index, s.values, color=col, lw=1.6 if i < 3 else 1.3, label=name, solid_capstyle="round")
        dd = s / s.cummax() - 1
        a2.plot(dd.index, dd.values * 100, color=col, lw=1.1)
        a1.annotate(name.split(" /")[0][:22], (s.index[-1], s.values[-1]), xytext=(4, 0), textcoords="offset points",
                    fontsize=7, color=INK2, va="center")
    a1.set_yscale("log")
    a1.set_ylabel("資産（初期=1, 対数）")
    a2.set_ylabel("ドローダウン (%)")
    a1.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2)
    a1.axvline(pd.Timestamp(bt.OOS[0]), color=MUTED, lw=1)
    a2.axvline(pd.Timestamp(bt.OOS[0]), color=MUTED, lw=1)
    a1.text(pd.Timestamp(bt.OOS[0]), a1.get_ylim()[1], " OOS →", color=MUTED, fontsize=8, va="top")
    a1.set_title("エクイティカーブ（フルイン, 2011-02〜, 翌寄り約定・片道0.05%）", fontsize=11, loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_heat(g: pd.DataFrame, fam: str, src: str, path, title: str):
    sub = g[(g.fam == fam) & (g.src == src) & (g.sizing == "full")]
    k1s = [np.nan] if fam != "A" else list(bt.K1)
    rows_def = [(k2, k3) for k2 in bt.K2 for k3 in bt.K3 if not (k2 and k3 and k3 <= k2)]
    cols_def = [(s, n) for s in bt.STOPS for n in bt.NS]
    fig, axes = plt.subplots(len(k1s), 2, figsize=(11, 4.6 * len(k1s)), squeeze=False)
    for i, k1 in enumerate(k1s):
        for j, w in enumerate(("IS", "OOS")):
            ax = axes[i, j]
            s = sub[sub.win == w]
            if fam == "A":
                s = s[np.isclose(s.k1, k1)]
            M = np.full((len(rows_def), len(cols_def)), np.nan)
            for a, (k2, k3) in enumerate(rows_def):
                for b, (st, n) in enumerate(cols_def):
                    q = s[(s.k2.fillna(-1) == _key(k2)) & (s.k3.fillna(-1) == _key(k3)) & (s.stop == st) & (s.n == n)]
                    if len(q):
                        M[a, b] = q.MAR.iloc[0]
            lim = 1.0
            ax.imshow(M, cmap=DIVERGING, vmin=-lim, vmax=lim, aspect="auto")
            for a in range(M.shape[0]):
                for b in range(M.shape[1]):
                    v = M[a, b]
                    if not np.isnan(v):
                        ax.text(b, a, f"{v:.2f}", ha="center", va="center", fontsize=7,
                                color="#ffffff" if abs(v) > 0.65 else INK)
            ax.set_xticks(range(len(cols_def)), [f"{s_}\nN={n}" for s_, n in cols_def], fontsize=7, color=INK2)
            f = lambda v: "–" if v is None else f"{v:g}"
            ax.set_yticks(range(len(rows_def)), [f"k2={f(k2)} k3={f(k3)}" for k2, k3 in rows_def], fontsize=7, color=INK2)
            for sp in ax.spines.values():
                sp.set_visible(False)
            ttl = f"{w} MAR" + (f"  k1={k1:g}" if fam == "A" else "")
            ax.set_title(ttl, fontsize=9, loc="left", color=INK)
    fig.suptitle(title + "（色: MAR, 青=正/赤=負, ±1.0で飽和）", fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    df = lib.build()
    d = bt.Data(df)
    sigs = bt.entry_signals(df)
    g = run_grid(d, sigs)
    g.to_csv(OUT / "grid.csv", index=False)

    full_is = g[(g.sizing == "full") & (g.win == "IS")].copy()
    full_is["robust"] = robust_scores(full_is)
    full_is["eligible"] = full_is.Trades >= MIN_IS_TRADES
    key_cols = ["fam", "src", "k1", "k2", "k3", "stop", "n"]
    piv = {w: g[(g.sizing == "full") & (g.win == w)].set_index(key_cols) for w in ("FULL", "OOS")}
    piv_r = {w: g[(g.sizing == "risk1") & (g.win == w)].set_index(key_cols) for w in ("FULL", "IS", "OOS")}

    spans = {w: d.idx[slice(*d.span(win))] for w, win in bt.WINDOWS.items()}
    bench = bt.benchmarks(d)
    bres = {}
    for name, tgt in bench.items():
        bres[name] = {w: bt.metrics(*bt.run_target(d, tgt, win), spans[w]) for w, win in bt.WINDOWS.items()}
    qbh = {}
    for w, win in bt.WINDOWS.items():
        eq = bt.qqq_bh(d, win)
        qbh[w] = bt.metrics(eq, [dict(pnl=eq[-1] - 1, entry=0, exit=len(eq) - 1, alloc=1.0)], np.ones(len(eq), bool), spans[w])

    L = ["# TQQQ 乖離スイング — Step 3: 戦略バックテスト\n"]
    L.append(f"生成: {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M UTC}。期間 FULL=2011-02-10〜{d.idx[-1]:%Y-%m-%d}、"
             f"IS=2011-02-10〜2018-12-31（パラメータ選定）、OOS=2019-01-02〜（検証）。各期間はフラットから独立に開始。\n")
    L.append("## 0. 前提\n")
    L.append("- 約定: シグナルは終値確定、翌日始値で約定、片道スリッページ0.05%（手数料・税・金利なし、現金利回り0）。同時保有1。")
    L.append("- 損切りは日中判定: Low<=ストップで min(始値, ストップ) 約定（ギャップは不利側）。m×ATRは**約定価格−m×ATR14(シグナル足)**、SigLowはシグナル足安値。約定始値がストップ以下ならその取引は見送り。")
    L.append("- 部分利確: 終値でDev>=k2 → 翌寄りで半分。全利確: Dev>=k3。EMA21出口: **一度終値がEMA21以上になってから**の終値EMA21割れで翌寄り手仕舞い（Aは乖離マイナスで入るため、即日手仕舞いを避ける）。時間切れ: エントリーからN本目の終値が約定価格未満なら翌寄り撤退（N本目に1回だけ判定）。")
    L.append("- サイズ: フルイン＝資産の100%。リスク1%＝(約定−ストップ)×株数＝資産の1%、上限100%（レバレッジなし）。")
    L.append("- [QQQ]版: エントリー条件・Dev・EMA21出口をQQQの足で判定し、TQQQを売買（ストップはTQQQ価格）。")
    L.append(f"- グリッド: エントリー10種（A×k1 3種、B、C、各々TQQQ/QQQシグナル）× 出口84通り（k2 5×k3 3（k3>k2のみ）×ストップ3×N 2）× サイズ2 = **{len(g)//3}構成**。多重検定の余地が大きい点に注意。")
    L.append(f"- 選定ルール: IS・フルインで、**MARの近傍中央値**（1パラメータを1段ずらした構成との中央値。尖った最適値を避けるため）が最大の構成。IS取引数<{MIN_IS_TRADES}は選定対象外。\n")

    # ---- benchmarks
    L.append("## 1. ベンチマークと対照戦略（フルイン）\n")
    L.append("| 戦略 | 期間 " + MHDR + "\n|" + "---|" * 11)
    for name in ["QQQ B&H", *bench.keys()]:
        for w in ("FULL", "IS", "OOS"):
            m = qbh[w] if name == "QQQ B&H" else bres[name][w]
            L.append(f"| {name} | {w} " + mrow(m))
    L.append("")

    # ---- walk-forward per entry family
    L.append("## 2. ウォークフォワード（エントリー別にISで選定 → OOSで検証、フルイン）\n")
    L.append("| エントリー | IS選定構成 | IS取引 | IS MAR | IS近傍中央MAR | OOS CAGR | OOS MaxDD | OOS MAR | OOS取引 | OOS勝率 | OOS PF | OOS期待値R | OOS MAR順位(84中) | IS↔OOS 順位相関 |\n|" + "---|" * 14)
    picks = []
    for (fam, src), grp in full_is.groupby(["fam", "src"], sort=False):
        el = grp[grp.eligible]
        pool = el if len(el) else grp
        best = pool.loc[pool.robust.idxmax()]
        naive = pool.loc[pool.MAR.idxmax()]
        # rank within same entry signal (same k1 for A)
        same = g[(g.sizing == "full") & (g.win == "OOS") & (g.fam == fam) & (g.src == src)]
        if fam == "A":
            same = same[np.isclose(same.k1, best.k1)]
        k = tuple(best[c] for c in key_cols)
        mo = piv["OOS"].loc[k]
        rank = int((same.MAR > mo.MAR).sum()) + 1
        # IS vs OOS rank correlation across the whole family grid
        is_f = grp.set_index(key_cols).MAR
        oos_f = piv["OOS"].loc[is_f.index].MAR
        rho = is_f.rank().corr(oos_f.rank())
        flag = "" if best.eligible else " ⚠IS取引不足"
        L.append(f"| {sig_label_row(best)}{flag} | {cfg_label(best).split(' / ')[1]} | {int(best.Trades)} | {num(best.MAR)} | {num(best.robust)} | "
                 f"{pct(mo.CAGR)} | {pct(mo.MaxDD)} | {num(mo.MAR)} | {int(mo.Trades)} | {pct(mo.Win,0)} | {num(mo.PF)} | {num(mo.ExpR)} | {rank} | {num(rho)} |")
        picks.append(dict(row=best, naive=naive, oos=mo, rho=rho, eligible=bool(best.eligible)))
    L.append("")
    L.append("参考: IS単純最大MAR（近傍を見ない）で選んだ場合のOOS\n")
    L.append("| エントリー | IS最大MAR構成 | IS MAR | OOS MAR | OOS CAGR | OOS MaxDD |\n|---|---|---|---|---|---|")
    for p in picks:
        nv = p["naive"]
        mo = piv["OOS"].loc[tuple(nv[c] for c in key_cols)]
        L.append(f"| {sig_label_row(nv)} | {cfg_label(nv).split(' / ')[1]} | {num(nv.MAR)} | {num(mo.MAR)} | {pct(mo.CAGR)} | {pct(mo.MaxDD)} |")
    L.append("")

    # ---- grid-wide OOS distribution vs controls
    L.append("## 3. グリッド全体の分布（全84出口 × エントリー、OOS・フルイン）\n")
    sma_oos = bres["TQQQ when QQQ>SMA200"]["OOS"]["MAR"]
    bh_oos = bres["TQQQ B&H"]["OOS"]["MAR"]
    L.append(f"| エントリー | 構成数 | OOS MAR 中央値 | OOS MAR 最大 | OOS CAGR 中央値 | MAR>B&H({bh_oos:.2f})の割合 | MAR>SMA200フィルタ({sma_oos:.2f})の割合 | IS MAR 中央値 |\n|---|---|---|---|---|---|---|---|")
    for key in sigs:
        fam, src, k1 = key
        s = g[(g.sizing == "full") & (g.fam == fam) & (g.src == src)]
        if k1 is not None:
            s = s[np.isclose(s.k1, k1)]
        so, si = s[s.win == "OOS"], s[s.win == "IS"]
        L.append(f"| {bt.sig_label(key)} | {len(so)} | {num(so.MAR.median())} | {num(so.MAR.max())} | {pct(so.CAGR.median())} | "
                 f"{(so.MAR > bh_oos).mean():.0%} | {(so.MAR > sma_oos).mean():.0%} | {num(si.MAR.median())} |")
    L.append("")

    # ---- top 3
    elig = [p for p in picks if p["eligible"]]
    top = sorted(elig, key=lambda p: -p["row"].robust)[:3]
    L.append("## 4. 上位3ルール（IS近傍中央MARの順、エントリー別の選定結果から）\n")
    curves = {}
    fam_colors = {}
    ytab = {}
    for rank_i, p in enumerate(top, 1):
        r = p["row"]
        key = sig_key(r)
        ex = to_exit(r)
        name = cfg_label(r)
        L.append(f"### #{rank_i} {name}\n")
        L.append("| サイズ | 期間 " + MHDR + " 平均投下比率 |\n|" + "---|" * 12)
        for sizing in ("full", "risk1"):
            for w, win in bt.WINDOWS.items():
                eq, tr, held = bt.run(d, sigs[key], key[1], ex, sizing, win)
                m = bt.metrics(eq, tr, held, spans[w])
                L.append(f"| {'フルイン' if sizing=='full' else 'リスク1%'} | {w} " + mrow(m) + f" {pct(m['AvgAlloc'],0)} |")
        eq, tr, held = bt.run(d, sigs[key], key[1], ex, "full", bt.FULL)
        eqs = pd.Series(eq, spans["FULL"])
        curves[name] = eqs
        ytab[f"#{rank_i}"] = yearly(eqs)
        t = trade_table(tr, d)
        L.append("\nレジーム別（シグナル足のレジーム、フルイン, FULL）\n")
        L.append("| レジーム | 取引 | 勝率 | 平均リターン | 期待値(R) | PF |\n|---|---|---|---|---|---|")
        for reg, gg in t.groupby("regime"):
            gp, gl = gg.pnl[gg.pnl > 0].sum(), -gg.pnl[gg.pnl < 0].sum()
            L.append(f"| {reg} | {len(gg)} | {pct((gg.pnl>0).mean(),0)} | {pct(gg.ret.mean())} | {num(gg.R.mean())} | {num(gp/gl if gl>0 else np.nan)} |")
        why = t.why.value_counts()
        L.append("\n出口の内訳: " + "、".join(f"{k} {v}" for k, v in why.items()))
        L.append(f"\n最大連敗: {max_streak(t.pnl < 0)}、最大単発損失: {pct(t.ret.min())}、最大単発利益: {pct(t.ret.max())}\n")
        L.append(f"IS↔OOS 順位相関（同エントリーの全出口構成）: {num(p['rho'])}\n")

    # ---- yearly table
    for name in ("TQQQ B&H", "TQQQ when QQQ>SMA200", "対照: R1中保有"):
        eq, _, _ = bt.run_target(d, bench[name], bt.FULL)
        s = pd.Series(eq, spans["FULL"])
        curves[name] = s
        ytab[name] = yearly(s)
    qs = pd.Series(bt.qqq_bh(d, bt.FULL), spans["FULL"])
    ytab["QQQ B&H"] = yearly(qs)
    L.append("## 5. 年別リターン（フルイン、2026は年初来）\n")
    yt = pd.DataFrame(ytab)
    L.append("| 年 | " + " | ".join(yt.columns) + " |\n|" + "---|" * (len(yt.columns) + 1))
    for y, row in yt.iterrows():
        b = "**" if y == 2022 else ""
        L.append(f"| {b}{y}{b} | " + " | ".join(pct(v) for v in row) + " |")
    L.append("")

    L.append("## 6. レジーム別の年率寄与（日次対数リターンをレジーム別に合計 ÷ 年数、FULL）\n")
    rt = pd.DataFrame({k: regime_daily(v, df.Regime) for k, v in curves.items()}).reindex(["R1", "R2", "R3"])
    L.append("| レジーム | " + " | ".join(c.split(" /")[0] for c in rt.columns) + " |\n|" + "---|" * (len(rt.columns) + 1))
    for reg, row in rt.iterrows():
        L.append(f"| {reg} | " + " | ".join(pct(v) for v in row) + " |")
    L.append("")

    # ---- figures
    eq_curves = dict(list(curves.items())[:len(top)])
    eq_curves["TQQQ B&H"] = curves["TQQQ B&H"]
    eq_curves["QQQ B&H"] = qs
    eq_curves["TQQQ when QQQ>SMA200"] = curves["TQQQ when QQQ>SMA200"]
    fig_equity(eq_curves, OUT / "fig_equity_dd.png")
    fig_heat(g, "A", "T", OUT / "fig_heat_A.png", "A 押し目（TQQQシグナル）")
    fig_heat(g, "B", "T", OUT / "fig_heat_B.png", "B AVWAPリテスト（TQQQシグナル）")
    fig_heat(g, "C", "T", OUT / "fig_heat_C.png", "C 投げ売り（TQQQシグナル）")
    L.append("## 7. 図\n")
    L.append("- `fig_equity_dd.png`: 上位3ルール＋ベンチマークのエクイティカーブとDD")
    L.append("- `fig_heat_A.png` / `fig_heat_B.png` / `fig_heat_C.png`: 出口パラメータ感応度（IS/OOSのMAR）\n")

    (OUT / "02_backtest.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


def sig_label_row(r) -> str:
    return bt.sig_label(sig_key(r))


def max_streak(mask: pd.Series) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


if __name__ == "__main__":
    main()
