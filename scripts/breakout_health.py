"""ブレイク成功度 (breakout health): are the swing signals actually paying right now?

Display and allocation guide only; the stock rules never change.

Definition (same as the 2015-2026 backtest):
  For every session in the last 63 sessions whose 10-day outcome is already known
  (signal day d-72 ... d-10), take every 本命-type signal of that day
  (all swing conditions met x weekly SAR bull x not in the HL-side zone; the QQQ
  regime is ignored so the gauge keeps measuring while new entries are paused) and
  average its close-to-close return over the next 10 sessions.  >= 0 is 好調,
  < 0 is 不調 (momentum entries are not being rewarded).

Allocation rule: when 不調 and QQQ is above its 200-day average, put 100% of idle
cash in the TQQQ-rule sleeve (Rules tab 9; QQQ until October 2026); otherwise 60%
(50% before the 2026-10-13 v6 rule).
Re-check with QQQ as the sleeve and next-open fills (2026-10-13, 6 x 1/6, stock trades
unchanged): always 50% 35.0% -> switch 39.0%, max DD -34.1% either way.  The switch
holds about 65% of idle cash on average and a fixed 65% gives 36.9%, so the timing
itself adds roughly +2 points a year (35 of 36 parameter sets positive in the older
signal-close study).
"""
from __future__ import annotations

import html
import math
from typing import Any

import numpy as np
import pandas as pd

HORIZON = 10
WINDOW = 63
HISTORY = 252
MIN_SIGNALS = 5
# 2026-10-18: hysteresis.  Weak (不調) starts when the value goes under 0% and lasts
# until it is back above +1.5%.  Local test 2015-01..2026-10 (v6 + 大底フル + 守りモード
# + 利益保護): 66.2% -> 68.3% a year (2015-20 47.8 -> 50.8%, 2021-26 87.6 -> 88.7%),
# max DD -39.4% unchanged, yearly DD mean -24.2 -> -24.3%.  Every recovery level from
# +0.2% to +3% beat the plain 0% switch (67.1-69.6%); +4% broke down (max DD -45%).
RECOVER = 0.015
CARD_ID = "mc57-breakout-health"
from rules_tab import RULE_ID  # noqa: E402
from swing_allocation import EFFECTIVE_DATE, SLEEVE_NORMAL, SLEEVE_WEAK, STOCK_CAP_LABEL  # noqa: E402
from backtest_summary import CURRENT as BT  # noqa: E402

# Year-by-year backtest (2015-01 .. 2026-08, 6-position rule): idle cash 50% QQQ vs this switch.
YEARLY = [
    (2015, 7.8, 8.8), (2016, -2.4, 2.4), (2017, 19.5, 23.7), (2018, 11.6, 15.3), (2019, 17.6, 20.4),
    (2020, 154.6, 156.0), (2021, 51.1, 60.6), (2022, -16.1, -17.4), (2023, 28.3, 38.3),
    (2024, 141.6, 145.5), (2025, 43.6, 47.5), (2026, 86.8, 87.2),
]


def _weekly_up(h: pd.Series, l: pd.Series, c: pd.Series):
    """Weekly SAR bull flag per completed W-FRI week (causal), as (period_end_ns, up)."""
    from swing_screener import SAR_PARAMS, psar_flags
    df = pd.DataFrame({"h": h, "l": l, "c": c}).dropna()
    if len(df) < 30:
        return None
    wk = df.index.to_period("W-FRI")
    agg = df.groupby(wk).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    if len(agg) < 10:
        return None
    up, _ = psar_flags(agg["h"].to_numpy(float), agg["l"].to_numpy(float), agg["c"].to_numpy(float), *SAR_PARAMS)
    ends = agg.index.to_timestamp(how="end").normalize().to_numpy("datetime64[ns]")
    return ends, up


def _sar_up_at(cache: dict, t: str, h, l, c, day: pd.Timestamp) -> bool:
    """Same answer as swing_screener.weekly_sar_state on data truncated at ``day``."""
    if t not in cache:
        cache[t] = _weekly_up(h[t], l[t], c[t])
    w = cache[t]
    if w is None:
        return False
    ends, up = w
    # Completed weeks only (as weekly_sar_state): this week counts only when ``day`` is a Friday.
    wk_end = np.datetime64(day.to_period("W-FRI").to_timestamp(how="end").normalize(), "ns")
    k = int(np.searchsorted(ends, wk_end, side="right" if day.weekday() == 4 else "left")) - 1
    if k < 9:  # weekly_sar_state needs 10 completed weeks
        return False
    return bool(up[k])


def compute(frame: pd.DataFrame, history: int = HISTORY) -> dict[str, Any] | None:
    from swing_screener import _pivot, _states, structure_pivot
    p = _pivot(frame)
    o, h, l, c, v = p["open"], p["high"], p["low"], p["close"], p["volume"]
    n = len(c)
    need = 260 + HORIZON + WINDOW
    if n < need + 1:
        return None
    history = max(1, min(history, n - need))
    state = _states(c, h, l, v)
    cv, hv, lv = c.to_numpy(float), h.to_numpy(float), l.to_numpy(float)
    col = {t: i for i, t in enumerate(c.columns)}
    dates = c.index
    first_sig = n - 1 - HORIZON - (WINDOW - 1) - (history - 1)
    sums = np.zeros(n)
    cnts = np.zeros(n)
    sar_cache: dict = {}
    for s in range(first_sig, n - HORIZON):
        st = state(s - n)
        sig = st["signal"]
        for t in sig[sig].index:
            j = col[t]
            px, fut = cv[s, j], cv[s + HORIZON, j]
            if not (px > 0) or math.isnan(fut):
                continue
            if not _sar_up_at(sar_cache, t, h, l, c, dates[s]):
                continue
            line, hl = structure_pivot(hv[max(0, s - 259):s + 1, j], lv[max(0, s - 259):s + 1, j])
            inside = not math.isnan(line) and px <= line
            if inside and line > hl and (px - hl) / (line - hl) < 0.5:
                continue  # HL-side zone: not a 本命
            sums[s] += fut / px - 1
            cnts[s] += 1
    cs, ck = np.cumsum(sums), np.cumsum(cnts)
    hist = []
    for d in range(n - history, n):
        a, b = d - HORIZON, d - HORIZON - WINDOW
        k = ck[a] - ck[b]
        val = (cs[a] - cs[b]) / k if k >= MIN_SIGNALS else None
        hist.append((str(dates[d].date()), None if val is None else float(val), int(k)))
    value, count = hist[-1][1], hist[-1][2]
    states = hysteresis([v for _, v, _ in hist])
    # Days since the current state started.
    since = None
    if value is not None:
        cur = states[-1]
        for (dt, val, _), s in zip(reversed(hist), reversed(states)):
            if val is None or s != cur:
                break
            since = dt
    return {"session": str(dates[-1].date()), "value": value, "n": count,
            "on": None if value is None else bool(states[-1]), "since": since, "history": hist,
            "recover": RECOVER}


def hysteresis(values: list) -> list:
    """好調 (True) / 不調 (False) per value: 不調 below 0%, back to 好調 only above +RECOVER."""
    good, out = True, []
    for v in values:
        if v is not None:
            if good and v < 0:
                good = False
            elif not good and v > RECOVER:
                good = True
        out.append(good)
    return out


def allocation(health: dict | None, regime: dict | None, session: str | None = None,
               full: bool | None = None) -> tuple[int, str]:
    """Idle-cash share (%) for the TQQQ-rule sleeve and the reason.

    While the TQQQ rule's 大底フル is on (its latest recorded day), the share is 100%
    whatever the breakout health says; ``full`` overrides the ledger lookup (tests).

    A publication before the v6 cutover (session < EFFECTIVE_DATE) keeps the v5 normal 50%;
    the session defaults to the regime's date, then the health session.
    """
    session = session or (regime or {}).get("date") or (health or {}).get("session")
    if full is None:
        try:
            import tqqq_rule
            fb = tqqq_rule.full_bottom_active(session=session)
        except Exception:
            fb = None
        if fb:
            return SLEEVE_WEAK, f"大底フル（VIX+2σの底確認）であと{fb['left']}営業日"
    elif full:
        return SLEEVE_WEAK, "大底フル（VIX+2σの底確認）"
    if session and str(session) < EFFECTIVE_DATE:
        normal = 50
    else:
        normal = SLEEVE_NORMAL
    if not health or health.get("on") is None:
        return normal, "ブレイク成功度が計算できないため通常どおり"
    if regime is None:
        return normal, "地合い（QQQの200日線）が取れないため通常どおり"
    if not health["on"] and regime.get("on"):
        return SLEEVE_WEAK, "不調かつQQQが200日線より上"
    if not health["on"]:
        return normal, "不調だがQQQが200日線より下なので増やさない"
    return normal, "好調"


def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def _state_word(health: dict | None) -> tuple[str, str]:
    if not health or health.get("on") is None:
        return "計算不可", "#747166"
    return ("好調", "#23824d") if health["on"] else ("不調", "#b42222")


def _spark(hist: list) -> str:
    pts = [(i, v) for i, (_, v, _) in enumerate(hist) if v is not None]
    if len(pts) < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(min(vals), -0.02), max(max(vals), 0.02)
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    W, H, X0 = 668.0, 168.0, 6.0
    x = lambda i: X0 + W * i / max(len(hist) - 1, 1)
    y = lambda v: 6 + H * (hi - v) / (hi - lo)
    zero = y(0.0)
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
    lx, ly = x(pts[-1][0]), y(pts[-1][1])
    last = len(hist) - 1
    ticks = [f'<span>{hist[round(last * q / 4)][0][2:7].replace("-", "/")}</span>' for q in range(5)]
    return ('<div class="chart"><svg preserveaspectratio="none" viewbox="0 0 680 180">'
            f'<rect fill="#25c25f" opacity="0.08" x="6" y="6" width="668" height="{max(zero - 6, 0):.1f}"></rect>'
            f'<rect fill="#df5454" opacity="0.08" x="6" y="{zero:.1f}" width="668" height="{max(174 - zero, 0):.1f}"></rect>'
            f'<line stroke="#aaa591" stroke-width="1.2" stroke-dasharray="4 4" x1="6" x2="674" y1="{zero:.1f}" y2="{zero:.1f}"></line>'
            f'<text fill="#aaa591" font-size="20" font-weight="600" text-anchor="start" x="10" y="{zero - 4:.1f}">0%</text>'
            f'<polyline fill="none" points="{line}" stroke="#1c1b19" stroke-width="2"></polyline>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" fill="#1c1b19" r="3.5"></circle></svg>'
            f'<div class="dax">{"".join(ticks)}</div></div>')


BH_STYLE = (
    '<style id="bh-style">'
    '#mc57-breakout-health .bh-q{font-size:12.5px;color:#6b6858;margin:2px 0 8px}'
    '#mc57-breakout-health .bh-act{border-radius:10px;padding:10px 12px;margin:6px 0 8px;border:1px solid}'
    '#mc57-breakout-health .bh-act.on{background:#eef7f0;border-color:#b9dcc3}'
    '#mc57-breakout-health .bh-act.off{background:#fbf3e3;border-color:#e6cf98}'
    '#mc57-breakout-health .bh-act.na{background:#f3f2ee;border-color:#dedbd2}'
    '#mc57-breakout-health .bh-act b.big{font-size:17px}'
    '#mc57-breakout-health .bh-act .bh-why{font-size:12px;color:#5c594d;margin-top:3px}'
    '#mc57-breakout-health .bh-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:6px 0}'
    '#mc57-breakout-health .bh-grid div{background:#f6f5f1;border-radius:8px;padding:6px 8px;font-size:11.5px;color:#6b6858}'
    '#mc57-breakout-health .bh-grid b{display:block;font-size:14px;color:#1c1b19}'
    '#mc57-breakout-health .bh-next{font-size:12px;color:#3f3d35;margin:4px 0 2px}'
    '#mc57-breakout-health ul.bh-ul{margin:4px 0 0 1.1em;padding:0;font-size:12px;line-height:1.6}'
    '</style>')


WHY_TEXT = {"好調": "好調なので通常の比率"}


def _streak_days(health: dict) -> int:
    """Sessions the current state (好調/不調) has lasted in the shown history."""
    since = health.get("since")
    return sum(1 for d, v, _ in health.get("history", []) if since and d >= since and v is not None)


def _next_switch(health: dict | None, regime: dict | None, pct: int) -> str:
    if not health or health.get("on") is None:
        return "計算できるようになるまで通常の比率のまま。"
    gap = abs(float(health["value"])) * 100
    if not regime or regime.get("on") is None:
        return "地合い（QQQの200日線）が取れない間は、好調・不調にかかわらず通常の比率のまま。"
    if health["on"]:
        tail = (f"、QQQが200日線より上なら余剰資金を{SLEEVE_WEAK}%に増やす" if regime.get("on")
                else "。ただしQQQが200日線より下の間は増やさない")
        return f"0%を下回ると（今はあと{gap:.1f}pt）不調に変わり{tail}。"
    if regime.get("on"):
        back = allocation({"on": True, "value": 0.0, "session": health.get("session")}, regime)[0]
        need = max(0.0, (RECOVER - float(health["value"])) * 100)
        return f"+{RECOVER * 100:.1f}%を超えると（今はあと{need:.1f}pt）好調に戻り、余剰資金は{back}%に戻す。"
    return f"QQQが200日線を回復したら余剰資金を{SLEEVE_WEAK}%に増やす（不調のままなら）。"


def daily_card(health: dict | None, regime: dict | None) -> str:
    word, color = _state_word(health)
    pct, why = allocation(health, regime)
    value = health.get("value") if health else None
    n = health.get("n") if health else 0
    since = health.get("since") if health else None
    on = None if not health else health.get("on")
    cls = "na" if on is None else ("on" if on else "off")
    meaning = ("勢い株は報われている（買った本命が伸びている）" if on else
               "勢い株が報われていない（指数は上がっても本命が伸びない）" if on is False else "判定に必要なシグナルが足りない")
    days = _streak_days(health) if health and since else 0
    hist = health.get("history", []) if health else []
    # a state that began before the shown year is at least that long, not exactly
    truncated = bool(since and hist and since == hist[0][0])
    spark = _spark(hist) if health else ""
    since_txt = f'{since[5:].replace("-", "/")}から' if since else ""
    action = (f'<div class="bh-act {cls}">今日の余剰資金：<b class="big">{pct}%</b> をTQQQルール枠へ'
              f'<div class="bh-why">{html.escape(WHY_TEXT.get(why, why))}。残りは現金。個別株の売買ルールは変えない。</div></div>')
    grid = ('<div class="bh-grid">'
            f'<div>本命の10日後<b>{html.escape(_fmt(value))}</b>平均</div>'
            f'<div>数えた本命<b>{n}件</b>直近63営業日</div>'
            + (f'<div>{html.escape(word)}が続いて<b>{days}営業日{"以上" if truncated else ""}</b>'
               f'{"1年以上前から" if truncated else html.escape(since_txt)}</div>' if since
               else '<div>続いた日数<b>—</b>判定できない</div>')
            + '</div>')
    explain = (
        '<details class="cxpl"><summary>読み方と根拠</summary><div class="cxpl-b"><ul class="bh-ul">'
        f'<li><b>何を測る？</b> 直近63営業日に出た本命が、10日後に平均何%動いたか。マイナスになったら不調、不調は+{RECOVER * 100:.1f}%を超えるまで続く（2026-10-18から。0%の行き来で戻さない）。'
        '10日後の結果が出たものだけを使うので先読みはない（その分、切り替わりは数週間遅れる。一度切り替わると平均3か月ほど続き、2015〜2026/10で不調の日は約半分）。</li>'
        '<li><b>何に使う？</b> 余剰資金の置き場所だけ。不調かつQQQが200日線より上の日は'
        f'{SLEEVE_WEAK}%をTQQQルール枠、それ以外は{SLEEVE_NORMAL}%（10月12日の公開分までは50%）。'
        'QQQが200日線より下では増やさない（2022年のような下げで傷を深くしない）。個別株の新規・損切り・買い増しは変えない。</li>'
        '<li><b>なぜ効く？</b> 指数は上がるのに勢い株が伸びない「退屈な年」（2016・2021・2023年）を不調と判定し、その年を指数側で取りにいく。'
        '退屈な年は不調判定が約3分の2、好調だった2020・2026年は約5%。</li>'
        '<li><b>崩れの警戒とは別物</b>：F1〜F3・MC57は「相場が崩れるか」、これは「買ったシグナルが伸びているか」。</li>'
        '</ul><details class="cxpl"><summary>検証の数字</summary><div class="cxpl-b">'
        f'現行（6銘柄×1/6・株は資産の{STOCK_CAP_LABEL}まで・枠{SLEEVE_NORMAL}%/{SLEEVE_WEAK}%・翌日の寄りで売買）で年率{BT["cagr"]}%・'
        f'最大DD{str(BT["dd"]).replace("-", "−")}%。'
        '置き先をQQQにした検証（株の上限なし）では、常に50%の年率35.0%→切替39.0%（最大DD−34.1%のまま）。'
        '平均すると余剰資金の約65%を置く形で、65%固定なら36.9%＝切り替えそのものの上乗せは年+2pt程度（日数・基準を変えた36通り中35通りでプラス＝旧計算）。<br/>'
        f'2026-10-18：不調から戻る線を+{RECOVER * 100:.1f}%に（手元検証・大底フル・守りモード・利益保護込み）。年率66.2%→68.3%（2015〜20年47.8→50.8%、2021〜26年87.6→88.7%）、最大DD−39.4%は同じ。'
        '戻る線を+0.2〜+3%のどこにしても0%のときより上（67.1〜69.6%）、+4%では崩れる。測り方（中央値・勝率・QQQ超過）・期間（5日後・20日後・窓42/126日）・段階的な比率はどれも今の形を上回らなかった。'
        '</div></details></div></details>')
    return (
        f'<div class="card" id="{CARD_ID}" data-rule="{RULE_ID}">' + BH_STYLE
        + '<div class="chd"><h2>ブレイク成功度<span class="h2en">Breakout Health</span></h2>'
        f'<div class="chd-now" style="color:{color}"><b>{html.escape(_fmt(value))}</b><span>{word}</span></div></div>'
        f'<div class="bh-q">{html.escape(meaning)}</div>'
        + action + grid
        + f'<div class="bh-next"><b>次の切り替え</b>：{html.escape(_next_switch(health, regime, pct))}</div>'
        + (f'{spark}<div class="sub" style="margin-top:2px">線＝その日の値（上の緑＝好調、下の赤＝不調）。1年分。</div>'
           if spark else '<div class="sub" style="margin-top:2px">推移はまだ描けない（計算できた日が足りない）。</div>')
        + explain + '</div>'
    )


def positions_line(health: dict | None, regime: dict | None) -> str:
    if not health or health.get("on") is None:
        return ""
    word, _ = _state_word(health)
    pct, why = allocation(health, regime)
    cls = "on" if health["on"] else "off"
    # crossing 0% changes the share only while QQQ is above its 200-day line
    switch = ("地合いが取れないため比率は通常のまま。" if not regime or regime.get("on") is None
              else "0%をまたぐと切り替え。" if regime.get("on") else "QQQが200日線より下の間は0%をまたいでも比率は同じ。")
    return (f'<div class="sw-reg {cls}" style="{"" if health["on"] else "background:#f3ecd6;color:#6b5a1e;border:1px solid #e0cf98"}">'
            f'ブレイク成功度 <b>{html.escape(_fmt(health["value"]))}</b>（{word}）→ 余剰資金の<b>{pct}%</b>をTQQQルール枠'
            f'<span style="opacity:.85">（{html.escape(WHY_TEXT.get(why, why))}。{switch}詳しくはDailyタブ）</span></div>')


def apply_daily(text: str, health: dict | None, regime: dict | None) -> str:
    """Insert the card in the Daily tab just before 'リーダーの強さ'."""
    if f'id="{CARD_ID}"' in text or health is None:
        return text
    i = text.find("<h2>リーダーの強さ")
    if i < 0:
        return text
    s = text.rfind('<div class="card">', 0, i)
    if s < 0:
        return text
    return text[:s] + daily_card(health, regime) + text[s:]
