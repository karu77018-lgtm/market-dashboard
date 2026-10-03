"""ブレイク成功度 (breakout health): are the swing signals actually paying right now?

Display and allocation guide only; the stock rules never change.

Definition (same as the 2015-2026 backtest):
  For every session in the last 63 sessions whose 10-day outcome is already known
  (signal day d-72 ... d-10), take every 本命-type signal of that day
  (all swing conditions met x weekly SAR bull x not in the HL-side zone; the QQQ
  regime is ignored so the gauge keeps measuring while new entries are paused) and
  average its close-to-close return over the next 10 sessions.  >= 0 is 好調,
  < 0 is 不調 (momentum entries are not being rewarded).

Allocation rule: when 不調 and QQQ is above its 200-day average, hold 100% of idle
cash in QQQ; otherwise 50%.  Backtest (stock trades unchanged): CAGR 28.5% -> 32.3%,
max DD -23.5% -> -23.5%.
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
CARD_ID = "mc57-breakout-health"

# Year-by-year backtest (2015-01 .. 2026-08): idle cash 50% QQQ vs this switch.
YEARLY = [
    (2015, 5.9, 6.9), (2016, -1.0, 3.7), (2017, 17.8, 22.4), (2018, 7.0, 11.4), (2019, 17.0, 20.1),
    (2020, 105.9, 107.0), (2021, 22.0, 30.5), (2022, -16.2, -18.1), (2023, 16.9, 26.3),
    (2024, 103.0, 108.1), (2025, 31.9, 35.1), (2026, 83.5, 83.5),
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
    # Days since the current state started.
    since = None
    if value is not None:
        cur = value >= 0
        for dt, val, _ in reversed(hist):
            if val is None or (val >= 0) != cur:
                break
            since = dt
    return {"session": str(dates[-1].date()), "value": value, "n": count,
            "on": None if value is None else value >= 0, "since": since, "history": hist}


def allocation(health: dict | None, regime: dict | None) -> tuple[int, str]:
    """Idle-cash QQQ share (%) and the reason."""
    if not health or health.get("on") is None:
        return 50, "ブレイク成功度が計算できないため通常どおり"
    if regime is None:
        return 50, "地合い（QQQの200日線）が取れないため通常どおり"
    if not health["on"] and regime.get("on"):
        return 100, "不調かつQQQが200日線より上"
    if not health["on"]:
        return 50, "不調だがQQQが200日線より下なので増やさない"
    return 50, "好調"


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


def daily_card(health: dict | None, regime: dict | None) -> str:
    word, color = _state_word(health)
    pct, why = allocation(health, regime)
    value = health.get("value") if health else None
    since = health.get("since") if health else None
    n = health.get("n") if health else 0
    since_txt = f"・{since[5:].replace('-', '/')}から" if since else ""
    return (
        f'<div class="card" id="{CARD_ID}"><div class="chd"><h2>ブレイク成功度<span class="h2en">Breakout Health</span></h2>'
        f'<div class="chd-now" style="color:{color}"><b>{html.escape(_fmt(value))}</b><span>{word}</span></div></div>'
        f'<div class="sub">スイングの本命シグナルが10日後に平均何%動いたか（直近63営業日・{n}件{since_txt}）。'
        f'<b>余剰資金のQQQ：{pct}%</b>（{html.escape(why)}）</div>'
        '<details class="cxpl"><summary>読み方</summary><div class="cxpl-b">'
        '0%以上＝好調（勢い株が報われている）、マイナス＝不調（指数は上がっても勢い株が伸びない「退屈な年」型）。'
        '不調かつQQQが200日線より上の日は、余剰資金を100%QQQに置く（それ以外は50%）。個別株の売買ルールは変えない。<br/>'
        '2015〜2026年の検証で年率28.5%→32.3%、最大DDは−23.5%のまま。退屈だった2016・2021・2023年は不調判定が約3分の2、'
        '好調だった2020・2026年は約5%。崩れの警戒（F1〜F3・MC57）とは別の問い＝「買ったシグナルが伸びているか」を測る。'
        '10日後の結果が出たシグナルだけを使うので先読みはない。地合い停止中もシグナルは数え続ける。</div></details>'
        + (_spark(health["history"]) if health else "")
        + '</div>'
    )


def positions_line(health: dict | None, regime: dict | None) -> str:
    if not health or health.get("on") is None:
        return ""
    word, _ = _state_word(health)
    pct, why = allocation(health, regime)
    cls = "on" if health["on"] else "off"
    return (f'<div class="sw-reg {cls}" style="{"" if health["on"] else "background:#f3ecd6;color:#6b5a1e;border:1px solid #e0cf98"}">'
            f'ブレイク成功度 <b>{html.escape(_fmt(health["value"]))}</b>：余剰資金のQQQは<b>{pct}%</b>'
            f'<span style="opacity:.85">（{html.escape(why)}）</span></div>')


def apply_daily(text: str, health: dict | None, regime: dict | None) -> str:
    """Insert the card in the Daily tab just before 'リーダーの強さ'."""
    if CARD_ID in text or health is None:
        return text
    i = text.find("<h2>リーダーの強さ")
    if i < 0:
        return text
    s = text.rfind('<div class="card">', 0, i)
    if s < 0:
        return text
    return text[:s] + daily_card(health, regime) + text[s:]
