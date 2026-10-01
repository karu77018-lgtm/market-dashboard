#!/usr/bin/env python3
"""Theme gate card: which fine themes pass the three empirical conditions.

Display-only adapter. It never changes MC57, V38, NQSAR, Massive, FRED or
publication logic. Inputs are the already-acquired adjusted OHLCV frame and the
fine theme membership written by the refresh step.

Conditions (from the 2016-2026 theme lifecycle study):
  1. Ignition  : equal-weight theme index within 3% of its 252-day high and
                 63-day return >= +30%.
  2. Breadth   : at least 3 members with RS >= 85 that close above their 200DMA.
  3. Not hot   : theme index no more than +150% above its 200-day average.
Candidates inside a passing theme are second-tier pullbacks: RS >= 70, above the
50DMA, 3-15% below the 60-day high, session change below +3%, and not the
theme's top 63-day gainer. Descriptive only; no orders are generated.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

IGNITION_R63 = 0.30
NEAR_HIGH = 0.97
MAX_EXT200 = 1.50
MIN_LEADERS = 3
LEADER_RS = 85
WATCH_R63 = 0.20
MIN_MEMBERS = 5
CARD_ID = "mc57-theme-gate"


def _rs_percentile(close: pd.DataFrame) -> pd.Series:
    """IBD-style weighted 3/6/9/12-month strength, percentile 1-99 on the last bar."""
    last = close.iloc[-1]

    def ret(n: int) -> pd.Series:
        if len(close) <= n:
            return pd.Series(np.nan, index=close.columns)
        return last / close.iloc[-1 - n] - 1

    raw = 0.4 * ret(63) + 0.2 * ret(126) + 0.2 * ret(189) + 0.2 * ret(252)
    raw = raw.where(raw.notna(), 0.4 * ret(63) + 0.6 * ret(126))
    return (raw.rank(pct=True) * 98 + 1).round()


def _membership(rows: list[dict]) -> dict[str, list[str]]:
    themes: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        theme = str(row.get("theme_name") or row.get("theme_id") or "").strip()
        if ticker and theme:
            themes.setdefault(theme, []).append(ticker)
    return themes


def evaluate(frame: pd.DataFrame, rows: list[dict]) -> dict:
    close = frame.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    high = frame.pivot_table(index="date", columns="ticker", values="high", aggfunc="last").reindex(close.index)
    close = close.ffill(limit=3)
    rets = close.pct_change(fill_method=None).clip(-0.5, 1.0)
    rs = _rs_percentile(close)
    last = close.iloc[-1]
    sma50 = close.rolling(50, min_periods=50).mean().iloc[-1]
    sma200 = close.rolling(200, min_periods=200).mean().iloc[-1]
    hi60 = high.rolling(60, min_periods=20).max().iloc[-1]
    day = close.iloc[-1] / close.iloc[-2] - 1 if len(close) >= 2 else pd.Series(np.nan, index=close.columns)
    r63 = close.iloc[-1] / close.iloc[-64] - 1 if len(close) > 64 else pd.Series(np.nan, index=close.columns)

    out = []
    for theme, members in _membership(rows).items():
        members = [t for t in members if t in close.columns]
        if len(members) < MIN_MEMBERS:
            continue
        sub = rets[members]
        n = sub.notna().sum(axis=1)
        idx = (1 + sub.mean(axis=1).where(n >= MIN_MEMBERS).fillna(0)).cumprod()
        idx = idx.where(n.rolling(20).min() >= MIN_MEMBERS).dropna()
        if len(idx) < 210:
            continue
        hi252 = idx.iloc[-252:].max()
        t_r63 = idx.iloc[-1] / idx.iloc[-64] - 1
        from_high = idx.iloc[-1] / hi252 - 1
        ext200 = idx.iloc[-1] / idx.iloc[-200:].mean() - 1
        leaders = [t for t in members if rs.get(t, 0) >= LEADER_RS and pd.notna(sma200.get(t)) and last[t] > sma200[t]]
        ignition = idx.iloc[-1] >= NEAR_HIGH * hi252 and t_r63 >= IGNITION_R63
        breadth = len(leaders) >= MIN_LEADERS
        not_hot = ext200 <= MAX_EXT200
        if ignition and breadth and not_hot:
            status = "合格"
        elif ignition and breadth and not not_hot:
            status = "過熱"
        elif t_r63 >= WATCH_R63 and from_high >= -0.10 and breadth:
            status = "監視"
        else:
            continue
        top = r63[members].idxmax() if r63[members].notna().any() else None
        cands = []
        for t in members:
            if t == top or not all(pd.notna(x) for x in (rs.get(t), sma50.get(t), hi60.get(t), day.get(t))):
                continue
            off = last[t] / hi60[t] - 1
            if rs[t] >= 70 and last[t] > sma50[t] and -0.15 <= off <= -0.03 and day[t] < 0.03:
                cands.append({"ticker": t, "rs": int(rs[t]), "from_high": float(off), "day": float(day[t])})
        cands.sort(key=lambda c: -c["rs"])
        out.append({"theme": theme, "status": status, "members": len(members), "r63": float(t_r63),
                    "from_high": float(from_high), "ext200": float(ext200), "leaders": len(leaders),
                    "leader_list": sorted(leaders, key=lambda t: -rs[t])[:4], "top": top,
                    "candidates": cands[:3]})
    order = {"合格": 0, "過熱": 1, "監視": 2}
    out.sort(key=lambda x: (order[x["status"]], -x["r63"]))
    return {"session": str(close.index[-1].date()), "themes": out}


STYLE = """
<style id="mc57-theme-gate-style">
#mc57-theme-gate .tg-row{border-top:1px solid #e1dfd6;padding:8px 2px}
#mc57-theme-gate .tg-row:first-of-type{border-top:0}
#mc57-theme-gate .tg-h{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-weight:700}
#mc57-theme-gate .tg-st{font-size:11px;border-radius:5px;padding:1px 6px;color:#fff;white-space:nowrap}
#mc57-theme-gate .tg-ok{background:#23824d}#mc57-theme-gate .tg-hot{background:#b5523f}#mc57-theme-gate .tg-watch{background:#8a7b3c}
#mc57-theme-gate .tg-m{font-size:12px;color:#4d4a40;margin-top:3px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#mc57-theme-gate .tg-c{font-size:12px;margin-top:3px;overflow-wrap:anywhere}
#mc57-theme-gate .tg-empty{font-size:13px;color:#4d4a40;padding:6px 2px}
</style>"""


def _pct(v: float) -> str:
    p = round(v * 100)
    return "0%" if p == 0 else f"{p:+d}%"


def card_html(result: dict) -> str:
    rows = []
    cls = {"合格": "tg-ok", "過熱": "tg-hot", "監視": "tg-watch"}
    for t in result["themes"][:12]:
        e = html.escape
        lead = " ".join(e(x) for x in t["leader_list"])
        cand = " / ".join(f'{e(c["ticker"])}（RS{c["rs"]}・高値{_pct(c["from_high"])}）' for c in t["candidates"])
        if t["status"] == "合格":
            cand_line = f'<div class="tg-c">押し目候補（2番手以降）：{cand or "条件に合う押し目なし（待つ）"}</div>'
        elif t["status"] == "過熱":
            cand_line = '<div class="tg-c">200日線から+150%超。新規は見送り、保有は利益確保を優先。</div>'
        else:
            cand_line = '<div class="tg-c">着火待ち（3か月+30%かつ52週高値圏で合格）。</div>'
        rows.append(
            f'<div class="tg-row"><div class="tg-h"><span class="tg-st {cls[t["status"]]}">{t["status"]}</span>'
            f'<span>{e(t["theme"])}</span></div>'
            f'<div class="tg-m">3か月 {_pct(t["r63"])}・高値から {_pct(t["from_high"])}・200日線 {_pct(t["ext200"])}'
            f'・主導株 {t["leaders"]}/{t["members"]}（{lead}）</div>{cand_line}</div>'
        )
    body = "".join(rows) or '<div class="tg-empty">合格・監視テーマなし。裁量の新規買いは見送り。</div>'
    n_ok = sum(1 for t in result["themes"] if t["status"] == "合格")
    return (
        f'<div class="card" id="{CARD_ID}" data-source-improvement="theme-gate">'
        '<div class="chd"><h2>テーマ判定（3条件）</h2>'
        f'<div class="chd-now" style="color:#23824d"><b>{n_ok}</b><span>合格テーマ</span></div></div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        '自ユニバースの細分テーマごとに構成銘柄の等ウェイト指数を作り、次の3つを判定。'
        '①着火＝52週高値の3%以内かつ3か月+30%以上、②広がり＝RS85以上かつ200日線上の主導株が3銘柄以上、'
        '③過熱でない＝200日線から+150%以内。2016〜2026年の検証では、着火後1年の勝率は約75%、'
        '主導株が固まったテーマは大負けが半分以下、+150%超では3か月後の中央値がマイナス。'
        '候補はテーマ1位を除く2番手以降で、RS70以上・50日線上・60日高値から3〜15%押し・当日+3%未満。'
        '赤字銘柄が多い物語型テーマ（量子・水素・宇宙など）は約3か月で終わる前提で小さく。売買指示ではない。'
        '</div></details>'
        f'<div class="tg-list">{body}</div></div>'
    )


def apply(text: str, frame: pd.DataFrame, membership_path: Path) -> str:
    if CARD_ID in text or not membership_path.is_file():
        return text
    rows = json.loads(membership_path.read_text(encoding="utf-8")).get("rows") or []
    card = card_html(evaluate(frame, rows))
    anchor = text.find("<h2>テーマETFの温度計")
    if anchor < 0:
        return text
    start = text.rfind('<div class="card"', 0, anchor)
    if start < 0:
        return text
    text = text[:start] + card + text[start:]
    return text.replace("</head>", STYLE + "</head>", 1)
