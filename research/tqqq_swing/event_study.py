"""Step 1-2: sample counts + Dev-band event study. Writes reports/01_event_study.md."""
from __future__ import annotations

import numpy as np
import pandas as pd

import lib

OUT = lib.ROOT / "reports"
OUT.mkdir(exist_ok=True)
H = (5, 10, 20)
IS_END = "2018-12-31"
OOS_START = "2019-01-01"


def lookahead_check(full: pd.DataFrame) -> str:
    """Recompute on truncated histories; values at the cut bar must not change."""
    t_full, q_full = lib.load("TQQQ"), lib.load("QQQ")
    cols = ["EMA21", "SMA50", "SMA200", "ATR14", "Dev", "DevZ", "AVWAP_L", "AVWAP_H", "Q_Dev", "Q_AVWAP_L", "Regime"]
    rng = np.random.default_rng(0)
    cuts = sorted(rng.choice(np.arange(400, len(full) - 30), 25, replace=False))
    bad = 0
    for c in cuts:
        d = full.index[c]
        t = lib.add_avwap(lib.base_indicators(t_full.loc[:d]))
        q = lib.add_avwap(lib.base_indicators(q_full.loc[:d])).add_prefix("Q_")
        part = t.join(q, how="inner")
        r1 = (part.Q_Close > part.Q_SMA200) & (part.Q_EMA21 > part.Q_SMA50)
        part["Regime"] = np.where(r1, "R1", np.where(part.Q_Close > part.Q_SMA200, "R2", "R3"))
        for k in cols:
            a, b = full.loc[d, k], part.loc[d, k]
            if isinstance(a, str) or isinstance(b, str):
                bad += a != b
            elif not (pd.isna(a) and pd.isna(b)) and not np.isclose(a, b, rtol=1e-9, atol=1e-12):
                bad += 1
    return f"{len(cuts)} random cut dates x {len(cols)} columns, mismatches = {bad}"


def band_labels(x: pd.Series, edges: list[float], fmt) -> pd.Series:
    lab = [f"<{fmt(edges[0])}"] + [f"[{fmt(a)},{fmt(b)})" for a, b in zip(edges[:-1], edges[1:])] + [f">={fmt(edges[-1])}"]
    idx = np.digitize(x, edges)
    s = pd.Series(pd.Categorical.from_codes(np.where(x.isna(), -1, idx), lab), index=x.index)
    return s


def episodes(mask: pd.Series) -> int:
    m = mask.to_numpy()
    return int((m & ~np.r_[False, m[:-1]]).sum())


def summarize(sub: pd.DataFrame, mask_all: pd.Series | None = None) -> dict:
    r = {"N": len(sub)}
    if mask_all is not None:
        r["Ep"] = episodes(mask_all)
    for h in H:
        x = sub[f"R{h}"].dropna()
        r[f"med{h}"] = x.median()
        r[f"win{h}"] = (x > 0).mean()
        r[f"mean{h}"] = x.mean()
    r["MAE10"] = sub.MAE10.median()
    r["MFE10"] = sub.MFE10.median()
    r["MAE20"] = sub.MAE20.median()
    r["MFE20"] = sub.MFE20.median()
    return r


def pct(x, d=1):
    return "" if pd.isna(x) else f"{x*100:.{d}f}%"


def band_table(df: pd.DataFrame, band_col: str, regimes) -> pd.DataFrame:
    rows = []
    for reg in regimes:
        in_reg = df.Regime == reg if reg != "ALL" else df.Regime.notna()
        base = df[in_reg]
        b = summarize(base)
        rows.append({"Regime": reg, "Band": "(全日)", **b, "Ep": np.nan})
        for band in df[band_col].cat.categories:
            m = in_reg & (df[band_col] == band)
            sub = df[m]
            if len(sub) == 0:
                continue
            s = summarize(sub, m)
            s["dmed10"] = s["med10"] - b["med10"]
            x = sub.R10.dropna()
            # crude t-stat of mean excess vs regime baseline, using independent episodes as n
            s["t10"] = (x.mean() - b["mean10"]) / (x.std(ddof=1) / np.sqrt(max(s["Ep"], 1))) if len(x) > 2 else np.nan
            is_ = sub.loc[:IS_END, "R10"].dropna()
            oos = sub.loc[OOS_START:, "R10"].dropna()
            s["IS_med10"], s["IS_n"] = is_.median(), len(is_)
            s["OOS_med10"], s["OOS_n"] = oos.median(), len(oos)
            rows.append({"Regime": reg, "Band": band, **s})
    return pd.DataFrame(rows)


def md_main(t: pd.DataFrame) -> str:
    hdr = ("| Regime | Dev帯 | N日 | 独立Ep | 5d中央 | 5d勝率 | 10d中央 | 10d勝率 | 10d平均 | Δ中央10 vs 全日 | "
           "20d中央 | 20d勝率 | MAE10中央 | MFE10中央 | MAE20中央 | MFE20中央 | IS10中央(n) | OOS10中央(n) |\n"
           "|" + "---|" * 19 + "\n")
    lines = []
    for _, r in t.iterrows():
        ep = "" if pd.isna(r.get("Ep")) else f"{int(r.Ep)}"
        d = "" if pd.isna(r.get("dmed10")) else pct(r.dmed10)
        isn = "" if pd.isna(r.get("IS_n")) else f"{pct(r.IS_med10)} ({int(r.IS_n)})"
        oon = "" if pd.isna(r.get("OOS_n")) else f"{pct(r.OOS_med10)} ({int(r.OOS_n)})"
        flag = " ⚠" if r.N < 60 else ""
        tt = "" if pd.isna(r.get("t10")) else f"{r.t10:+.1f}"
        lines.append(
            f"| {r.Regime} | {r.Band}{flag} | {int(r.N)} | {ep} | {pct(r.med5)} | {pct(r.win5,0)} | {pct(r.med10)} | {pct(r.win10,0)} | "
            f"{pct(r.mean10)} | {d} | {tt} | {pct(r.med20)} | {pct(r.win20,0)} | {pct(r.MAE10)} | {pct(r.MFE10)} | "
            f"{pct(r.MAE20)} | {pct(r.MFE20)} | {isn} | {oon} |")
    return hdr + "\n".join(lines) + "\n"


def trigger_events(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Entry-trigger bars for candidate setups (signal at close t -> buy Open[t+1])."""
    reclaim = df.Close > df.High.shift(1)
    ev = {}
    for k1 in (0.5, 1.0, 1.5):
        setup = (df.Dev <= -k1).shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
        ev[f"A k1={k1} (R1)"] = reclaim & setup & (df.Regime == "R1")
    lo, hi = df.AVWAP_L - df.ATR14, df.AVWAP_L + df.ATR14
    touch = df.AVWAP_L.notna() & (df.Low <= hi) & (df.Close >= lo)
    touch_recent = touch.rolling(3, min_periods=1).max().fillna(0).astype(bool)  # touch on t-2..t
    ev["B AVWAP_L zone (R1/R2)"] = reclaim & touch_recent & df.Regime.isin(["R1", "R2"])
    ev["B AVWAP_L zone (R1)"] = reclaim & touch_recent & (df.Regime == "R1")
    ev["B AVWAP_L zone (R2)"] = reclaim & touch_recent & (df.Regime == "R2")
    capit = (df.DevZ <= -2.5).shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
    ev["C DevZ<=-2.5 (全)"] = reclaim & capit & df.Regime.notna()
    # QQQ-signal variants (signal on QQQ bars, trade TQQQ)
    q_reclaim = df.Q_Close > df.Q_High.shift(1)
    for k1 in (0.5, 1.0, 1.5):
        setup = (df.Q_Dev <= -k1).shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
        ev[f"A[QQQ] k1={k1} (R1)"] = q_reclaim & setup & (df.Regime == "R1")
    qlo, qhi = df.Q_AVWAP_L - df.Q_ATR14, df.Q_AVWAP_L + df.Q_ATR14
    qtouch = df.Q_AVWAP_L.notna() & (df.Q_Low <= qhi) & (df.Q_Close >= qlo)
    ev["B[QQQ] AVWAP_L zone (R1/R2)"] = q_reclaim & qtouch.rolling(3, min_periods=1).max().fillna(0).astype(bool) & df.Regime.isin(["R1", "R2"])
    qcap = (df.Q_DevZ <= -2.5).shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
    ev["C[QQQ] DevZ<=-2.5 (全)"] = q_reclaim & qcap & df.Regime.notna()
    return ev


def dedupe(mask: pd.Series, gap: int = 5) -> pd.Series:
    """Keep the first trigger, then ignore further triggers for `gap` bars."""
    m = mask.to_numpy()
    keep = np.zeros_like(m)
    last = -10**9
    for i, v in enumerate(m):
        if v and i - last > gap:
            keep[i] = True
            last = i
    return pd.Series(keep, index=mask.index)


def main():
    df = lib.build()
    fwd = lib.forward_stats(df, H)
    df = df.join(fwd)
    # study window: regime and DevZ both defined
    valid = df.Regime.notna() & df.DevZ.notna() & df.Q_SMA200.notna()
    st = df[valid].copy()
    edges = [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    st["DevBand"] = band_labels(st.Dev, edges, lambda v: f"{v:+.1f}")
    pct_edges = [-0.15, -0.10, -0.075, -0.05, -0.025, 0.0, 0.025, 0.05, 0.075, 0.10, 0.15]
    st["PctBand"] = band_labels(st.DevPct, pct_edges, lambda v: f"{v*100:+.1f}%")
    st["QDevBand"] = band_labels(st.Q_Dev, edges, lambda v: f"{v:+.1f}")

    la = lookahead_check(df)

    L = []
    L.append("# TQQQ 乖離スイング — Step 1–2: データ・指標・イベントスタディ\n")
    L.append(f"生成: {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M UTC}\n")
    L.append("## 1. データとサンプル数\n")
    t_raw, q_raw = lib.load("TQQQ"), lib.load("QQQ")
    L.append("| 系列 | 本数 | 開始 | 終了 |\n|---|---|---|---|")
    L.append(f"| TQQQ 日足 | {len(t_raw)} | {t_raw.index[0]:%Y-%m-%d} | {t_raw.index[-1]:%Y-%m-%d} |")
    L.append(f"| QQQ 日足 | {len(q_raw)} | {q_raw.index[0]:%Y-%m-%d} | {q_raw.index[-1]:%Y-%m-%d} |")
    L.append(f"| 分析対象（レジーム・DevZ確定後） | {len(st)} | {st.index[0]:%Y-%m-%d} | {st.index[-1]:%Y-%m-%d} |\n")
    L.append("- 取得元: TradingView (NASDAQ:TQQQ / NASDAQ:QQQ)、**分割調整済み・配当未調整**。`MASSIVE_API_KEY` が環境に無く、"
             "外部HTTP（Yahoo/Massive REST）もプロキシで遮断されていたため。Massive MCP（無料枠は直近約2年）で 2025-01〜2026-09 の434本を突き合わせ、OHLCが完全一致することを確認。")
    L.append("- 合成proxyは不使用（実OHLCV）。キャッシュ: `research/tqqq_swing/data/*.parquet`")
    L.append("- 配当未調整の影響: QQQ配当は年0.5–0.8%程度でSMA200判定への影響は軽微、TQQQ配当はほぼゼロ。B&H比較ではQQQのトータルリターンをわずかに過小評価する点に留意。\n")
    rc = st.Regime.value_counts().reindex(["R1", "R2", "R3"])
    L.append("| レジーム | 日数 | 構成比 | エピソード数 |\n|---|---|---|---|")
    for r_, n_ in rc.items():
        L.append(f"| {r_} | {n_} | {n_/len(st):.1%} | {episodes(st.Regime == r_)} |")
    L.append("")
    avl = st.AVWAP_L.notna().mean()
    avh = st.AVWAP_H.notna().mean()
    L.append(f"- スイング安値AVWAP（確定済・起点20本以内）が有効な日: {avl:.1%}、スイング高値AVWAP: {avh:.1%}")
    L.append(f"- 確定スイング安値ピボット数 (TQQQ): {int(df.PivotL.sum())}、高値: {int(df.PivotH.sum())}")
    L.append(f"- DevZ<=-2.5 の日数: {int((st.DevZ <= -2.5).sum())}（エピソード {episodes(st.DevZ <= -2.5)}）")
    L.append(f"- **ルックアヘッド検査**（途中までのデータで再計算し当日値が一致するか）: {la}\n")
    L.append("### 指標定義\n")
    L.append("- EMA21 = `ewm(span=21, adjust=False)`、ATR14 = Wilder RMA（TradingView `ta.atr` と同じ）、SMA50/200 = 単純移動平均")
    L.append("- Dev = (Close−EMA21)/ATR14、DevPct = Close/EMA21−1、DevZ = Devの252日zスコア（平均・標準偏差は t−252…t−1、当日除外）")
    L.append("- ピボット: 左右5本。安値ピボットは左5本より厳密に低く右5本以下。**ピボット足+5本の終値確定後から**使用")
    L.append("- AVWAP: ピボット足を起点に典型価格(H+L+C)/3×出来高で累積。起点からの経過が20本以内のみ有効（確定まで5本かかるので実際に使えるのは経過5〜20本）")
    L.append("- ゾーン: AVWAP±1×ATR14")
    L.append("- 前方リターン: シグナル足tの終値確定→**翌日始値で約定**、h日後終値（Close[t+h]）で評価。MAE/MFEは t+1…t+h の Low/High を約定価格比で。コスト未控除\n")

    L.append("## 2. イベントスタディ: TQQQ Dev帯 × レジーム\n")
    L.append("読み方: N日＝該当日数（連続日は重複カウント＝前方リターンは強く自己相関）、独立Ep＝帯への連続滞在をまとめた回数。"
             "Δ中央10＝同レジーム全日の10日中央値との差（＝条件付けのエッジの目安）。t(平均差,Ep)＝10日平均の対全日差を独立Ep数で割ったt値（重複を割り引いた粗い目安。|t|<2はノイズと見なす）。IS=2011-02–2018, OOS=2019–。⚠=N<60。\n")
    main_t = band_table(st, "DevBand", ["R1", "R2", "R3"])
    L.append(md_main(main_t))
    main_t.to_csv(OUT / "event_dev_band.csv", index=False)

    L.append("\n## 3. 比較: %乖離（Close/EMA21−1）帯 × レジーム\n")
    pt = band_table(st, "PctBand", ["R1", "R2", "R3"])
    L.append(md_main(pt))
    pt.to_csv(OUT / "event_pct_band.csv", index=False)

    L.append("\n## 4. QQQ Dev帯（シグナルQQQ）→ TQQQ 前方リターン\n")
    qt = band_table(st, "QDevBand", ["R1", "R2", "R3"])
    L.append(md_main(qt))
    qt.to_csv(OUT / "event_qqq_dev_band.csv", index=False)

    L.append("\n## 5. 参考: 戦略候補のエントリートリガー足のイベントスタディ（出口ルールなし・固定保有）\n")
    L.append("トリガー定義（Step 3で確定させる前の暫定）: A＝直近5本（t−5…t−1）に Dev<=−k1 があり、当日終値>前日高値。"
             "B＝t−2…t にスイング安値AVWAPゾーン接触（Low<=AVWAP+ATR かつ Close>=AVWAP−ATR）があり当日終値>前日高値。"
             "C＝直近5本に DevZ<=−2.5 があり当日終値>前日高値。いずれも発火後5本は再発火を無視。\n")
    L.append("| トリガー | N | 5d中央 | 10d中央 | 10d勝率 | 10d平均 | 20d中央 | 20d勝率 | MAE10中央 | MFE10中央 | IS10中央(n) | OOS10中央(n) | 2022 10d中央(n) |\n|" + "---|" * 13)
    rows = []
    for name, m in trigger_events(st).items():
        m = dedupe(m.fillna(False))
        sub = st[m]
        s = summarize(sub)
        is_ = sub.loc[:IS_END, "R10"].dropna()
        oos = sub.loc[OOS_START:, "R10"].dropna()
        y22 = sub.loc["2022", "R10"].dropna()
        flag = " ⚠" if len(sub) < 30 else ""
        L.append(f"| {name}{flag} | {len(sub)} | {pct(s['med5'])} | {pct(s['med10'])} | {pct(s['win10'],0)} | {pct(s['mean10'])} | "
                 f"{pct(s['med20'])} | {pct(s['win20'],0)} | {pct(s['MAE10'])} | {pct(s['MFE10'])} | "
                 f"{pct(is_.median())} ({len(is_)}) | {pct(oos.median())} ({len(oos)}) | {pct(y22.median())} ({len(y22)}) |")
        rows.append({"trigger": name, **s})
    pd.DataFrame(rows).to_csv(OUT / "event_triggers.csv", index=False)
    L.append("")
    (OUT / "01_event_study.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
