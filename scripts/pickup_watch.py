"""拾う枠（監視・参考）: mid-cap leaders the main swing rule cannot reach.

Display only.  No capital is allocated by the rules; the card is a watch list.

Built from the 2015-2026 study of names that doubled outside the main universe
(50-day dollar volume top 5%).  A name is listed when, at today's close:
  - outside the main universe, close >= $5, 50-day dollar volume >= $10M
  - RS21, RS63 and RS189 all >= 85 (percentile of the 5$/5M universe)
  - close >= 2x its 52-week low, within 35% of its 52-week high
  - weekly SAR bull for at most 8 completed weeks
  - 20-day average daily range >= 4%
  - industry strength (mean RS63 of the industry, ranked across industries) >= 50
  - QQQ above its 200-day average
"形OK" adds the main rule's setup (10/50 range <= 0.9, 5/50 volume <= 0.9,
session < +3%, previous <= +3%, not in the HL-side zone).
Backtest of 形OK entries (exit: close below the 50-day average, stop -10%):
PF 1.92 (2015-18 1.85 / 2019-22 1.98 / 2023-26 1.89; 1.32 without the top 5
names).  As a stand-alone sleeve it made ~14%/yr with a -45% max drawdown, so it
is shown for discretionary use only.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CARD_ID = "mc57-pickup-watch"
from rules_tab import RULE_ID  # noqa: E402
SECTION = '<section id="t-alloc">'
MAP_PATH = Path(__file__).with_name("industry_map.json")

MIN_PRICE, MIN_DV = 5.0, 10e6
RS_MIN, UPLOW_MIN, OFF52_MIN, SAR_MAX, ADR_MIN, IND_MIN = 85, 2.0, -0.35, 8, 0.04, 50
STOP = 0.10


def _pct(values: pd.Series, mask: pd.Series) -> pd.Series:
    return values.where(mask).rank(pct=True) * 100


def compute(frame: pd.DataFrame, industry_map: dict[str, str] | None = None,
            regime: dict | None = None) -> dict[str, Any]:
    from swing_screener import (MAX_CHG, MAX_PREV_CHG, MAX_VC, MAX_VDRY, _pivot, _states,
                                structure_pivot, weekly_sar_state)
    p = _pivot(frame)
    h, l, c, v = p["high"], p["low"], p["close"], p["volume"]
    session = str(c.index[-1].date()) if len(c) else ""
    if len(c) < 260:
        return {"session": session, "rows": [], "reason": "history_short"}
    if industry_map is None:
        try:
            industry_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            industry_map = {}
    last = c.iloc[-1]
    dv50 = (c * v).rolling(50, min_periods=40).mean().iloc[-1]
    ma200 = c.rolling(200).mean().iloc[-1]
    hi252 = h.rolling(252, min_periods=200).max().iloc[-1]
    lo252 = l.rolling(252, min_periods=200).min().iloc[-1]
    ma50 = c.rolling(50).mean().iloc[-1]
    base = (last >= MIN_PRICE) & (dv50 >= 5e6) & ma200.notna() & hi252.notna()
    ret = lambda n: last / c.iloc[-1 - n] - 1
    rs = {n: _pct(ret(n), base) for n in (21, 63, 189)}
    # Main-universe membership (excluded here): close >= $10, dv50 >= $20M, dv50 top 5%.
    liquid = base & (last >= 10) & (dv50 >= 20e6)
    core = liquid & (_pct(dv50, liquid) >= 95)
    # Industry strength: mean RS63 of members, ranked across industries with >= 3 members.
    ind = pd.Series({t: industry_map.get(t) for t in c.columns})
    r63 = rs[63]
    grp = pd.DataFrame({"ind": ind, "rs": r63}).dropna()
    gmean = grp.groupby("ind")["rs"].agg(["mean", "size"])
    gmean = gmean[gmean["size"] >= 3]["mean"]
    ind_rank = gmean.rank(pct=True) * 100
    ind_rs = ind.map(ind_rank)
    adr = (h / l - 1).rolling(20).mean().iloc[-1]
    uplow = last / lo252
    off52 = last / hi252 - 1
    pre = (base & ~core & (last >= MIN_PRICE) & (dv50 >= MIN_DV)
           & (rs[21] >= RS_MIN) & (rs[63] >= RS_MIN) & (rs[189] >= RS_MIN)
           & (uplow >= UPLOW_MIN) & (off52 >= OFF52_MIN) & (adr >= ADR_MIN) & (ind_rs >= IND_MIN))
    state = _states(c, h, l, v)
    s = state(-1)
    rows = []
    for t in pre[pre.fillna(False)].index:
        try:
            up, age = weekly_sar_state(h[t], l[t], c[t])
        except Exception:
            continue
        if not up or age is None or age > SAR_MAX:
            continue
        px = float(last[t])
        line, hl = structure_pivot(h[t].to_numpy(float)[-260:], l[t].to_numpy(float)[-260:])
        inside = not math.isnan(line) and px <= line
        pos = (px - hl) / (line - hl) if inside and line > hl else None
        checks = {
            "値幅の縮小": bool(s["vc"].get(t, np.nan) <= MAX_VC),
            "出来高減": bool(s["vdry"].get(t, np.nan) <= MAX_VDRY),
            "当日+3%未満": bool(s["chg"].get(t, np.nan) < MAX_CHG),
            "前日+3%以下": bool(s["prev_chg"].get(t, np.nan) <= MAX_PREV_CHG),
            "HL寄りでない": not (pos is not None and pos < 0.5),
        }
        missing = [k for k, ok in checks.items() if not ok]
        rows.append({"ticker": t, "close": px, "chg": float(s["chg"].get(t, 0.0)),
                     "rs21": int(round(rs[21][t])), "rs63": int(round(rs[63][t])), "rs189": int(round(rs[189][t])),
                     "uplow": float(uplow[t]), "off52": float(off52[t]), "adr": float(adr[t]), "sar_age": int(age),
                     "industry": ind.get(t) or "", "ind_rs": int(round(ind_rs[t])), "ma50": float(ma50[t]),
                     "stop": px * (1 - STOP), "missing": missing, "ready": not missing})
    rows.sort(key=lambda r: (not r["ready"], len(r["missing"]), -r["rs63"]))
    return {"session": session, "rows": rows, "regime_on": None if regime is None else bool(regime.get("on"))}


STYLE = """
<style id="mc57-pickup-watch-style">
#mc57-pickup-watch .pw-row{border-top:1px solid #e3e1db;padding:8px 2px;cursor:pointer}
#mc57-pickup-watch .pw-row:active{background:#ecebe6}
#mc57-pickup-watch .pw-top{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
#mc57-pickup-watch .pw-tk{font-size:15px;font-weight:800}
#mc57-pickup-watch .pw-px{font-size:12.5px;font-variant-numeric:tabular-nums;color:#33312a}
#mc57-pickup-watch .pw-ind{margin-left:auto;font-size:10.5px;color:#6f6c62;max-width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#mc57-pickup-watch .pw-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
#mc57-pickup-watch .pw-c{font-size:10.5px;font-weight:700;border-radius:5px;padding:1px 6px;white-space:nowrap;background:#ecebe6;color:#55524a}
#mc57-pickup-watch .pw-c.ok{background:#7a4fb3;color:#fff}
#mc57-pickup-watch .pw-c.need{background:#f1f4f8;color:#3c4a5e;border:1px solid #dbe3ee;font-weight:600}
#mc57-pickup-watch .pw-lv{font-size:10.5px;color:#55524a;margin-top:4px;font-variant-numeric:tabular-nums}
#mc57-pickup-watch .pw-lv b{color:#b42222}
#mc57-pickup-watch .pw-note{font-size:10.5px;line-height:1.55;color:#6f5a8a;background:#f1ecf7;border-radius:8px;padding:6px 9px;margin:0 0 6px}
#mc57-pickup-watch .pw-up{color:#18813e}#mc57-pickup-watch .pw-dn{color:#b42222}
</style>"""


def _p(v: float) -> str:
    return f"{v * 100:+.1f}%".replace("-", "−")


def card_html(res: dict) -> str:
    e = html.escape
    rows = res["rows"]
    ready = [r for r in rows if r["ready"]]
    stopped = res.get("regime_on") is not True  # unknown regime = stopped

    def item(r: dict) -> str:
        cls = "pw-up" if r["chg"] >= 0 else "pw-dn"
        chips = ('<span class="pw-c ok">形OK・本日の終値で候補</span>' if r["ready"] else
                 "".join(f'<span class="pw-c need">{e(m)}待ち</span>' for m in r["missing"]))
        chips += (f'<span class="pw-c">RS {r["rs21"]}/{r["rs63"]}/{r["rs189"]}</span>'
                  f'<span class="pw-c">安値から{r["uplow"]:.1f}倍</span>'
                  f'<span class="pw-c">高値{_p(r["off52"])}</span>'
                  f'<span class="pw-c">週足SAR {r["sar_age"]}週目</span>'
                  f'<span class="pw-c">値幅{r["adr"] * 100:.1f}%</span>'
                  f'<span class="pw-c">業種 {r["ind_rs"]}</span>')
        return (f'<div class="pw-row" data-tkone="{e(r["ticker"])}"><div class="pw-top">'
                f'<span class="pw-tk">{e(r["ticker"])}</span><span class="pw-px">${r["close"]:,.2f}</span>'
                f'<span class="pw-px {cls}">{_p(r["chg"])}</span><span class="pw-ind">{e(r["industry"])}</span></div>'
                f'<div class="pw-chips">{chips}</div>'
                f'<div class="pw-lv">損切り −10% <b>${r["stop"]:,.2f}</b>・手仕舞い 50日線 ${r["ma50"]:,.2f} 割れ</div></div>')

    body = "".join(item(r) for r in rows[:15]) or '<div class="sw-empty" style="font-size:12px;color:#6f6c62">本日の該当なし。</div>'
    tks = ",".join(r["ticker"] for r in rows[:15])
    copy = (f'<button class="cp" data-tk="{e(tks)}" onclick="copyTk(event,this)">コピー <span class="n">{min(len(rows), 15)}</span></button>'
            if tks else "")
    return (
        f'<div class="card" id="{CARD_ID}" data-source-improvement="pickup-watch" data-rule="{RULE_ID}">'
        '<div class="chd"><h2>拾う枠（監視）<span class="h2en">Mid-cap Leaders</span></h2>'
        f'<div class="chd-now" style="color:#7a4fb3"><b>{len(ready)}</b><span>形OK</span></div></div>'
        f'<div class="sub">{e(res["session"])} 終値基準・本体（売買代金上位5%）の外で、しっかり伸びている中堅株。'
        f'該当{len(rows)}銘柄。タップで銘柄詳細。</div>'
        '<div class="pw-note">参考の監視リスト（資金は割り当てない）。形OKの検証PFは1.92と高いが、'
        '単独で運用すると年率約14%・最大DD−45%で、本体に足すと全体の伸びは下がる。'
        f'{("地合い停止中（QQQが200日線割れ）は新規なし。" if res.get("regime_on") is False else "地合い判定不可（QQQ未取得・日付不一致）のため新規なし。") if stopped else ""}</div>'
        f'<div style="display:flex;justify-content:flex-end;margin:-2px 0 2px">{copy}</div>'
        + body
        + '<details class="cxpl" style="margin-top:8px"><summary>条件と検証</summary><div class="cxpl-b">'
        '<b>候補</b>：本体の選定外・株価$5以上・売買代金$10M以上／RS21・63・189がすべて85以上／'
        '52週安値の2倍以上・52週高値から−35%以内／週足SARブル8週以内／1日の値幅4%以上／業種の強さが上位半分／地合いOK。<br/>'
        '<b>形OK</b>：本体と同じ（10日/50日の値幅0.9以下・5日/50日の出来高0.9以下・当日+3%未満・前日+3%以下・HL寄りでない）。<br/>'
        '<b>手仕舞い</b>：50日線割れで引け・損切り−10%（安値21EMAだと2023〜26年の成績が落ちる）。<br/>'
        '<b>検証</b>（2015〜2026年）：形OKのPF 1.92（2015〜18年 1.85／2019〜22年 1.98／2023〜26年 1.89、'
        '上位5銘柄を除くと1.32）。見逃していた大化けのうちVECO・TNDM・ENPH・MOD・STRL・GGALなどに乗れる。'
        '一方、値動きの荒い銘柄が一斉に崩れる局面（2021〜22年など）でDDが深く、単独運用は年率約14%・最大DD−45%。'
        '業績（EPS・売上の伸び）は成績をほとんど改善しなかった。現存銘柄のみの検証で、実際はもっと悪い可能性がある。'
        '</div></details></div>'
    )


def apply(text: str, frame: pd.DataFrame, regime: dict | None = None) -> str:
    """Insert at the top of the Positions tab (the swing card is inserted above it afterwards)."""
    if f'id="{CARD_ID}"' in text or SECTION not in text:
        return text
    try:
        res = compute(frame, regime=regime)
        card = card_html(res)
    except Exception as exc:  # display-only
        print(f"pickup watch skipped: {exc!r}", flush=True)
        return text
    print(f"pickup watch: {len(res['rows'])} names ({sum(r['ready'] for r in res['rows'])} ready)", flush=True)
    text = text.replace(SECTION, SECTION + card, 1)
    return text.replace("</head>", STYLE + "</head>", 1)
