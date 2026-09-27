"""Write output/<period>/: summary.md, trades.csv, watchlist.csv, monthly_*.png."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from config import BASELINE_FLOORS, SLIPPAGES  # noqa: E402
from watchlist import NETS  # noqa: E402

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans", "Yu Gothic", "Meiryo",
                               "MS Gothic", "WenQuanYi Zen Hei",
                               "DejaVu Sans"]

INK, INK2, MUTED, GRID, BASE, SURFACE, SERIES = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb", "#2a78d6")

DEVIATIONS = """\
| 項目 | 本番 | このバックテスト | 影響の向き |
|---|---|---|---|
| 判定の細かさ | 5秒ごとの現値 | 1分足の確定値（前の分足の終値→この分足の終値で+3%） | 分の途中の一瞬の急騰は拾えない／発火が最大1分遅れる |
| 約定 | 発火直後に指値、45秒で取消 | 次の1分足で判定。約定値＝max(始値, 指値)＋スリッページ | 悲観側（指値より良い値では絶対に約定させない） |
| -3%見送り | 約定前に合図値から-3%で取消 | 次の足の**始値**が-3%以下なら見送り。始値より後の下落は約定後とみなす | 悲観側 |
| 約定した足 | — | その足では撤退線(-8%)だけ判定し、利確はさせない | 悲観側 |
| 撤退と利確が同じ足 | — | 撤退が先 | 悲観側 |
| 段階の撤退線 | 到達高値をリアルタイムで更新 | 前の足までの高値で更新 | 中立 |
| 利確の約定 | 板に置いた指値 | 高値が利確値に届けば約定、スリッページも差し引く | 悲観側 |
| 売買停止 | — | 1分足が無い分は約定させない。再開後の始値で撤退判定 | 中立〜悲観 |
| 浮動株 | 取れない | 使っていない（監視網・発火のどの条件にも浮動株は無い）。発行済株数での代用も不要 | なし |
| PR銘柄の除外 | PRで監視に足した銘柄は入らない | 過去のPR配信を再現できないので除外していない | 本番より件数が多め |
| 平常値の下限 $30K | 「直近10分の秒あたり売買代金が$30K未満なら見送り」 | 単位が曖昧なため3通り（秒あたり$30K＝分$1.8M ／ 分$30K ／ 10分合計$30K）で出す | 件数が大きく変わる |
| アフター急騰・プレ発の拾い方 | 全銘柄の時間外を監視 | 当日の寄りが前日終値+10%以上の上位15銘柄だけ1分足を取り、その中で条件判定 | 寄りまでに失速した銘柄を拾い漏らす（件数は少なめ） |
| プレ発の判定 | プレ中に条件を満たした時点で追加 | 9:29までの1分足で最初に条件を満たした順に10銘柄 | 中立 |
| 監視網内の並び順 | 設定の実装順 | 前日の売買代金の大きい順（上限40銘柄で切るとき） | 中立 |
| 再点火の「その後」 | — | 急騰日の翌日から前日までの各日の値動きが±20%以内。急騰が前日なら保持率だけ見る | 解釈 |
| 株式分割 | — | 逆分割で見かけの急騰が出ないよう、分割前の値を補正して騰落率を計算 | 誤検知を防ぐ |
| 対象銘柄 | — | 普通株とADRのみ（上場廃止銘柄を含む）。ワラント・ユニット・ETFは除外 | 生存者バイアスなし |
| 期間 | — | 無料プランの約2年。開発期間でパラメータを決め、保留期間は最後に1回だけ | 数年単位の検証は不可 |
"""


def _max_dd(daily_pnl: pd.Series) -> float:
    eq = daily_pnl.sort_index().cumsum()
    return float((eq - eq.cummax()).min()) if len(eq) else 0.0


def _stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"件数": 0, "勝率": "-", "平均損益%": "-", "合計損益$": 0, "最大DD$": 0}
    return {"件数": len(t), "勝率": f"{(t['pnl'] > 0).mean():.0%}", "平均損益%": f"{t['pnl_pct'].mean():+.2%}",
            "合計損益$": round(t["pnl"].sum()), "最大DD$": round(_max_dd(t.groupby("date")["pnl"].sum()))}


def _table(rows: list[dict]) -> str:
    if not rows:
        return "（該当なし）\n"
    df = pd.DataFrame(rows)
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(str(v) for v in r) + " |\n" for r in df.itertuples(index=False))


def _usd(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def _monthly_chart(t: pd.DataFrame, title: str, path: Path) -> None:
    months = pd.period_range(t["date"].min()[:7], t["date"].max()[:7], freq="M") if not t.empty else []
    fig, axes = plt.subplots(len(SLIPPAGES), 1, figsize=(10, 2.6 * len(SLIPPAGES)), sharex=True, sharey=True,
                             facecolor=SURFACE)
    for ax, slip in zip(axes, SLIPPAGES):
        s = t[t["slippage"] == slip]
        m = s.groupby(s["date"].str[:7])["pnl"].sum().reindex([str(p) for p in months], fill_value=0)
        ax.set_facecolor(SURFACE)
        ax.bar(range(len(m)), m.values, width=0.7, color=SERIES, edgecolor=SURFACE, linewidth=2)
        ax.axhline(0, color=BASE, linewidth=1)
        ax.set_title(f"スリッページ片道 {slip:.1%}  合計 {_usd(m.sum())}", loc="left", fontsize=10, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASE)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.set_ylabel("損益 $", color=INK2, fontsize=9)
    axes[-1].set_xticks(range(len(months)), [str(p) for p in months], rotation=45, ha="right")
    fig.suptitle(title, x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def write(period: str, span: tuple[str, str], trades: pd.DataFrame, watch: pd.DataFrame,
          market_ret: pd.DataFrame, out: Path, missing: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if not trades.empty:
        trades.drop(columns=["fills"]).to_csv(out / "trades.csv", index=False)
    watch.to_csv(out / "watchlist.csv", index=False)
    if trades.empty:
        trades = pd.DataFrame(columns=["date", "net", "pnl", "pnl_pct", "slippage", "floor", "from_open"])
    trades = trades.assign(year=trades["date"].str[:4])
    sessions = sorted(watch["date"].unique()) if not watch.empty else []
    L = [f"# 再点火凸 バックテスト（{period}: {span[0]}〜{span[1]}）\n",
         f"- 対象営業日 {len(sessions)}日、監視リスト延べ {len(watch)}銘柄日"
         + (f"、うち1分足が無い {missing}件" if missing else "") + "\n",
         "- 1回 $1,000・買いのみ。1分足での近似（本番は5秒ごとの判定）。浮動株はどの条件にも使っていない\n",
         "- 数字はすべて同じ期間・同じ監視リストで、条件だけを変えたもの\n"]

    L.append("\n## 1. 監視網別・年別（9:40から判定＝本番と同じ）\n")
    for floor in BASELINE_FLOORS:
        L.append(f"\n### 平常値の下限: {floor}\n")
        rows = []
        f = trades[(trades["floor"] == floor) & (~trades["from_open"].astype(bool))]
        for slip in SLIPPAGES:
            s = f[f["slippage"] == slip]
            for net in (*NETS, "合計"):
                n = s if net == "合計" else s[s["net"] == net]
                for year in sorted(n["year"].unique()) + ["全期間"]:
                    y = n if year == "全期間" else n[n["year"] == year]
                    if y.empty and year != "全期間":
                        continue
                    rows.append({"スリッページ": f"{slip:.1%}", "監視網": net, "年": year} | _stats(y))
        L.append(_table(rows))

    L.append("\n## 2. 9:30から判定した版との比較\n")
    rows = []
    for floor in BASELINE_FLOORS:
        for slip in SLIPPAGES:
            for from_open, label in ((False, "9:40から（本番）"), (True, "9:30から")):
                s = trades[(trades["floor"] == floor) & (trades["slippage"] == slip)
                           & (trades["from_open"].astype(bool) == from_open)]
                rows.append({"平常値の下限": floor, "スリッページ": f"{slip:.1%}", "版": label} | _stats(s))
    L.append(_table(rows))

    L.append("\n## 3. 日次損益と IWM・SPY の相関（スリッページ1%、9:40から）\n")
    rows = []
    for floor in BASELINE_FLOORS:
        s = trades[(trades["floor"] == floor) & (trades["slippage"] == 0.01) & (~trades["from_open"].astype(bool))]
        daily = s.groupby("date")["pnl"].sum().reindex(sessions, fill_value=0.0)
        joined = pd.concat([daily.rename("pnl"), market_ret], axis=1, join="inner").dropna()
        traded = joined[joined.index.isin(s["date"].unique())]
        row = {"平常値の下限": floor, "日数": len(joined), "取引日数": len(traded)}
        for etf in ("IWM", "SPY"):
            row[f"{etf} 全日"] = f"{joined['pnl'].corr(joined[etf]):+.2f}" if len(joined) > 2 and joined["pnl"].std() > 0 else "-"
            row[f"{etf} 取引日のみ"] = f"{traded['pnl'].corr(traded[etf]):+.2f}" if len(traded) > 2 else "-"
        rows.append(row)
    L.append(_table(rows))
    L.append("\n目安: |相関| < 0.2 なら「地合いの影響が少ない」と言える。取引日のみの列は、取引しない日の0が相関を薄める効果を除いたもの。\n")

    L.append("\n## 4. 月別損益\n")
    for k, floor in enumerate(BASELINE_FLOORS):
        s = trades[(trades["floor"] == floor) & (~trades["from_open"].astype(bool))]
        name = f"monthly_{k}.png"
        _monthly_chart(s, f"月別損益（平常値の下限: {floor}、9:40から）", out / name)
        L.append(f"\n### {floor}\n\n![月別損益]({name})\n\n")
        piv = (s.assign(month=s["date"].str[:7]).pivot_table(index="month", columns="slippage", values="pnl",
                                                            aggfunc="sum", fill_value=0).round(0))
        L.append(_table([{"月": m} | {f"{c:.1%}": int(v) for c, v in r.items()} for m, r in piv.iterrows()]))

    L.append("\n## 5. 本番とのズレ\n\n" + DEVIATIONS)
    (out / "summary.md").write_text("".join(L))
    print(f"report: {out / 'summary.md'}")
