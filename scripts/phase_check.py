"""局面チェック（下げの初動・上げの初動・上げの分解）, Market tab, just above 今回の下げの分解. Display only.

Rules and numbers come from research/phase-starts-2026-11 (Nasdaq-100 and S&P 500, 1990-2026, local study):
- 上げの初動: during a decline of 10% or more (from the 252-session closing high), the first close 5% above the
  lowest close so far (a new low re-arms it).  Three signs of a real bottom, counted on that day:
  above the 50-day line / took 4 sessions or more / no single day up 3.7% or more.
- 上げ: the same at +10% (took 11 sessions or more / no day up 4% or more), plus what drove it (type).
- 本物の底 = afterwards the index got back within 2% of its high before closing below that low.
- 下げの初動: the S&P 500's first close 5% below its high (re-armed back within 2%); VIX 23 or more that day.
The live card uses QQQ and SPY from the refresh's market inputs (the study used the indices).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

import decline_anatomy as da
import fold

CARD_ID = "phase-check"
STATE_ID = "phase-check-state"
STYLE_ID = "phase-check-style"
STATE_SEED = "seed/phase-check-state.json"

DECLINE, NEAR_HIGH = -0.10, -0.02
UP5 = {"rise": 0.05, "days": 3, "maxday": 3.7}     # sign 2: days > 3, sign 3: biggest day < 3.7%
UP10 = {"rise": 0.10, "days": 10, "maxday": 4.0}
DOWN_START, VIX_CUT = -0.05, 23.0

# (events, real bottoms) by number of signs; and by half (1990-2007, 2008-2026)
REF_UP5 = {"0": (45, 9, (25, 2), (20, 7)), "1-2": (49, 25, (24, 15), (25, 10)), "3": (11, 10, (7, 6), (4, 4))}
REF_UP10 = {"0": (20, 6, (13, 2), (7, 4)), "1-2": (13, 8, (6, 4), (7, 4)), "3": (20, 19, (12, 12), (8, 7))}
BASE_UP5, BASE_UP10 = (105, 44), (53, 33)
# 4th sign (research/phase-starts-2026-11/ud5.py): financial conditions (Chicago Fed NFCI) not tightening
# over the 4 weeks before the day (change <= 0; values as known a week earlier).  (events, real bottoms)
EASE_CELLS = {"up5": {("0", True): (3, 1), ("0", False): (42, 8), ("1-2", True): (18, 12), ("1-2", False): (31, 13),
                      ("3", True): (4, 4), ("3", False): (7, 6)},
              "up10": {("1-2", True): (4, 3), ("1-2", False): (9, 5), ("3", True): (14, 14), ("3", False): (6, 5),
                       ("0", False): (20, 6)}}
EASE_ALL = {"up5": {True: (25, 17, (18, 12), (7, 5)), False: (80, 27, (38, 11), (42, 16))},
            "up10": {True: (18, 17, (10, 10), (8, 7)), False: (35, 16, (21, 8), (14, 8))}}
CELL_MIN = 10
CREDIT_TYPE = "信用不安・質への逃避型"   # +5% bounces after this kind of decline: 9% / 35% real, others 63% / 50%
# S&P 500 at -5%: (events, reached -10%) for VIX >= 23 / below
REF_DOWN = {"hi": (34, 15, (14, 6), (20, 9)), "lo": (31, 2, (21, 1), (10, 1))}
BASE_DOWN = (65, 17)
EXAMPLES = {
    "up5": {"0": "2025-04○・2022-03×・2020-03○", "1-2": "2026-08○・2026-04○・2025-03×", "3": "2023-01○・2020-09○・2018-04○"},
    "up10": {"0": "2025-04○・2020-03○・2019-01○", "1-2": "2026-04○・2024-08○・2022-11×", "3": "2023-01○・2022-07×・2020-10○"},
    "down": {"hi": "2026-03×・2025-11×・2025-03○", "lo": "2024-04×・2023-09○・2019-05×"},
}
TYPES = {
    "信用回復型": "信用スプレッドが0.15%以上縮小（社債の不安が和らいだ戻り）。",
    "金利低下型": "10年金利が0.2%以上低下（利下げ・金利低下を好感した戻り）。",
    "ハイテク主導型": "Nasdaq100がS&P500を5ポイント以上上回る（ハイテクだけが戻した）。",
    "小型・景気敏感主導型": "小型株と景気敏感（一般消費・資本財・金融）が上回る。",
    "全面高型": "特定の主役がない、広く買い戻された戻り。",
}


def _band(n: int) -> str:
    return "3" if n == 3 else ("0" if n == 0 else "1-2")


def _pct(a: int, b: int) -> int:
    return round(b / a * 100) if a else 0


# ---------------------------------------------------------------- state
def _nfci4(slow: dict, day: pd.Timestamp) -> float | None:
    s = da._series(slow, "nfci")
    if s.empty or (day - s.index[-1]).days > 28:     # weekly series; older than that is not today's reading
        return None
    a, b = da._asof(s, day, 7), da._asof(s, day, 35)
    return None if a is None or b is None else round(a - b, 3)


def _rally(q: pd.Series, i0: int, t: int, rule: dict, slow: dict | None = None) -> dict:
    """Signs counted on day t for the rise from the low at i0."""
    ma50 = q.rolling(50, min_periods=50).mean()
    rets = q.pct_change().iloc[i0 + 1:t + 1] * 100
    above = None if pd.isna(ma50.iloc[t]) else bool(q.iloc[t] > ma50.iloc[t])
    days = int(t - i0)
    big = float(rets.max()) if len(rets) else 0.0
    signs = [above, days > rule["days"], big < rule["maxday"]]
    n4 = _nfci4(slow or {}, q.index[t])
    return {"date": str(q.index[t].date()), "days": days, "maxday": round(big, 2), "above50": above,
            "signs": [None if s is None else bool(s) for s in signs], "score": int(sum(bool(s) for s in signs)),
            "nfci4": n4, "ease": None if n4 is None else bool(n4 <= 0)}


def rate_of(r: dict, kind: str) -> tuple[int, int, str]:
    """(events, real bottoms, basis): the sign count's band, refined by financial conditions when that cell is big enough."""
    band = _band(r["score"])
    ref = REF_UP5 if kind == "up5" else REF_UP10
    n, ok = ref[band][:2]
    e = r.get("ease")
    if e is not None:
        cell = EASE_CELLS[kind].get((band, e))
        if cell and cell[0] >= CELL_MIN:
            return cell[0], cell[1], f"○{r['score']}つ・金融環境{'○' if e else '×'}"
    return n, ok, f"○{r['score']}つ"


def _type(px: pd.DataFrame, i0: int, t: int, slow: dict) -> tuple[str | None, dict]:
    def ret(sym: str) -> float | None:
        if sym not in px:
            return None
        a, b = px[sym].iloc[i0], px[sym].iloc[t]
        return None if pd.isna(a) or pd.isna(b) or a == 0 else float(b / a - 1) * 100

    def diff(a: str, b: str) -> float | None:
        x, y = ret(a), ret(b)
        return None if x is None or y is None else x - y

    tnx = px["^TNX"] if "^TNX" in px else None
    d10 = None if tnx is None or pd.isna(tnx.iloc[t]) or pd.isna(tnx.iloc[i0]) else float(tnx.iloc[t] - tnx.iloc[i0]) * 100
    baa = da._series(slow, "baa")
    b1, b0 = da._asof(baa, px.index[t]), da._asof(baa, px.index[i0])
    cred = None if b1 is None or b0 is None else (b1 - b0) * 100
    cyc_parts = [ret(s) for s in ("XLY", "XLI", "XLF")]
    spy = ret("SPY")
    cyc = None if spy is None or None in cyc_parts else sum(cyc_parts) / 3 - spy
    f = {"d10": d10, "cred": cred, "spx": diff("SPY", da.INDEX), "small": diff("IWM", "SPY"), "cyc": cyc}
    if cred is not None and cred <= -15:
        kind = "信用回復型"
    elif d10 is not None and d10 <= -20:
        kind = "金利低下型"
    elif f["spx"] is not None and f["spx"] <= -5:
        kind = "ハイテク主導型"
    elif f["small"] is not None and cyc is not None and f["small"] >= 2 and cyc >= 1:
        kind = "小型・景気敏感主導型"
    elif None in (d10, f["spx"]):
        kind = None
    else:
        kind = "全面高型"
    return kind, {k: None if v is None else round(v, 1) for k, v in f.items()}


def qqq_phase(px: pd.DataFrame, slow: dict) -> dict:
    """Replays the study's rules on QQQ up to the last session."""
    q = px[da.INDEX]
    hi = q.rolling(252, min_periods=200).max()
    dd = q / hi - 1
    indec = False
    cur: dict[str, Any] = {}
    last_end: dict | None = None
    for t in range(len(q)):
        if pd.isna(dd.iloc[t]):
            continue
        c = float(q.iloc[t])
        if not indec:
            if dd.iloc[t] <= DECLINE:
                indec = True
                cur = {"start": t, "low_i": t, "low": c, "arm5": True, "arm10": True, "up5": None, "up10": None, "failed": []}
            continue
        if dd.iloc[t] >= NEAR_HIGH:
            last_end = {"date": str(q.index[t].date()), "low": str(q.index[cur["low_i"]].date())}
            indec = False
            continue
        if c < cur["low"]:
            for k in ("up5", "up10"):
                if cur[k]:
                    cur["failed"].append({**cur[k], "kind": k, "broke": str(q.index[t].date())})
            cur.update(low_i=t, low=c, arm5=True, arm10=True, up5=None, up10=None)
            continue
        if cur["arm5"] and c >= cur["low"] * (1 + UP5["rise"]):
            cur["arm5"] = False
            cur["up5"] = _rally(q, cur["low_i"], t, UP5, slow)
        if cur["arm10"] and c >= cur["low"] * (1 + UP10["rise"]):
            cur["arm10"] = False
            cur["up10"] = _rally(q, cur["low_i"], t, UP10, slow)
            cur["up10"]["type"], cur["up10"]["drivers"] = _type(px, cur["low_i"], t, slow)
    t = len(q) - 1
    ma50 = q.rolling(50, min_periods=50).mean().iloc[t]
    out: dict[str, Any] = {"dd": round(float(dd.iloc[t]) * 100, 1), "in_decline": indec, "last_end": last_end,
                           "close": round(float(q.iloc[t]), 2), "high": round(float(hi.iloc[t]), 2),
                           "ma50": None if pd.isna(ma50) else round(float(ma50), 2)}
    if indec:
        lo = cur["low_i"]
        out.update(peak=str(q.iloc[max(0, cur["start"] - 252):cur["start"] + 1].idxmax().date()),
                   low=str(q.index[lo].date()), low_close=round(cur["low"], 2),
                   from_low=round((float(q.iloc[t]) / cur["low"] - 1) * 100, 1),
                   up5=cur["up5"], up10=cur["up10"], failed=cur["failed"][-2:])
    return out


def spy_phase(px: pd.DataFrame) -> dict | None:
    if "SPY" not in px:
        return None
    s = px["SPY"].dropna()
    hi = s.rolling(252, min_periods=200).max()
    dd = s / hi - 1
    vix = px["^VIX"] if "^VIX" in px else None
    armed, ev = False, None
    for t in range(len(s)):
        d = dd.iloc[t]
        if pd.isna(d):
            continue
        if not armed and d >= NEAR_HIGH:
            armed = True
            if ev and ev["status"] == "open":
                ev["status"] = "recovered"
                ev["end"] = str(s.index[t].date())
        elif armed and d <= DOWN_START:
            armed = False
            day = s.index[t]
            v = None if vix is None or pd.isna(vix.get(day)) else round(float(vix[day]), 1)
            ev = {"date": str(day.date()), "vix": v, "status": "open", "end": None}
        if ev and ev["status"] == "open" and d <= DECLINE:
            ev["status"] = "reached"
            ev["end"] = str(s.index[t].date())
    return {"dd": round(float(dd.iloc[-1]) * 100, 1), "event": ev, "close": round(float(s.iloc[-1]), 2),
            "high": round(float(hi.iloc[-1]), 2)}


def build_state(market: dict, slow: dict, session: str | None = None) -> dict | None:
    px = da._closes(market)
    if px is None:
        return None
    if session:
        px = px[px.index <= pd.Timestamp(session)]
    return {"session": str(px.index[-1].date()), "qqq": qqq_phase(px, slow), "spy": spy_phase(px)}


# ---------------------------------------------------------------- rendering
def _md(day: str | None) -> str:
    if not day:
        return ""
    t = pd.Timestamp(day)
    return f"{t.month}/{t.day}"


def _signed(v: float, nd: int = 1) -> str:
    return f"{v:+.{nd}f}".replace("-", "−")


PHASES = (("high", "高値圏"), ("down_start", "下げの初動"), ("down", "下げ"), ("up5", "上げの初動"), ("up10", "上げ"))


def phase_of(state: dict) -> str:
    q, ev = state["qqq"], ((state.get("spy") or {}).get("event") or {})
    if q.get("in_decline"):
        return "up10" if q.get("up10") else "up5" if q.get("up5") else "down"
    return "down_start" if ev.get("status") == "open" else "high"


def _word(p: int) -> str:
    return "かなり期待できる" if p >= 80 else "五分五分" if p >= 40 else "一時的な戻りで終わることが多い"


def _odds_table(ref: dict, band: str) -> str:
    rows = ""
    for b, label in (("0", "0個"), ("1-2", "1〜2個"), ("3", "3個")):
        n, ok, h1, h2 = ref[b]
        cur = ' class="pc-cur"' if b == band else ""
        rows += (f'<tr{cur}><td>{label}</td><td><b>{_pct(n, ok)}%</b><small>{ok}/{n}回</small></td>'
                 f'<td>{_pct(*h1)}%</td><td>{_pct(*h2)}%</td></tr>')
    return ('<table class="pc-t"><tr><th>○の数</th><th>本物の底</th><th>1990〜2007</th><th>2008〜2026</th></tr>'
            f'{rows}</table>')


def _signs(r: dict, rule: dict, rise: str) -> str:
    a, d, m = r["signs"]
    mk = lambda ok: '<i class="pc-y">○</i>' if ok else ('<i class="pc-n">×</i>' if ok is False else "<i>−</i>")  # noqa: E731
    return ('<ul class="pc-s">'
            f'<li>{mk(a)}<span>50日線より上で戻した<small>{_md(r["date"])}の終値で判定</small></span></li>'
            f'<li>{mk(d)}<span>ゆっくり戻した<small>{rise}まで{r["days"]}営業日（{rule["days"] + 1}日以上で○）</small></span></li>'
            f'<li>{mk(m)}<span>急騰の日がない<small>いちばん大きい上げ {_signed(r["maxday"])}%（{rule["maxday"]}%未満で○）</small></span></li>'
            + (f'<li>{mk(r.get("ease"))}<span>金融環境が引き締まっていない（補助）<small>シカゴ連銀の金融環境指数NFCIの4週の変化 '
               + ("未取得" if r.get("nfci4") is None else f'{_signed(r["nfci4"], 3)}') + '（0以下で○）</small></span></li>')
            + '</ul>')


def _ladder(q: dict, nxt: float | None) -> str:
    """QQQ between the failure line (the low) and the real-bottom line (2% under the high)."""
    lo, hi_line, now = q["low_close"], (q.get("high") or 0) * 0.98, q.get("close")
    if not now or not hi_line or hi_line <= lo:
        return ""
    W, x0, x1 = 340, 14, 326
    x = lambda v: x0 + (x1 - x0) * (min(max(v, lo), hi_line) - lo) / (hi_line - lo)  # noqa: E731
    parts = [f'<svg class="pc-lad" viewBox="0 0 {W} 70" role="img" aria-label="安値から高値圏までのどこにいるか">',
             f'<line x1="{x0}" x2="{x1}" y1="30" y2="30" class="pc-axis"/>',
             f'<circle cx="{x0}" cy="30" r="4" class="pc-bad"/><circle cx="{x1}" cy="30" r="4" class="pc-good"/>',
             f'<text x="{x0}" y="52" class="pc-lt" text-anchor="start">失敗 {lo:.2f}</text>',
             f'<text x="{x1}" y="52" class="pc-lt" text-anchor="end">本物の底 {hi_line:.2f}</text>']
    if nxt and lo < nxt < hi_line:
        parts.append(f'<line x1="{x(nxt):.1f}" x2="{x(nxt):.1f}" y1="24" y2="36" class="pc-tick"/>'
                     f'<text x="{x(nxt):.1f}" y="66" class="pc-lt" text-anchor="middle">再判定 {nxt:.2f}</text>')
    parts.append(f'<path d="M{x(now):.1f},26 l-6,-10 h12 z" class="pc-now"/>'
                 f'<text x="{x(now):.1f}" y="11" class="pc-nt" text-anchor="middle">今 {now:.2f}</text></svg>')
    return "".join(parts)


def _rally_parts(q: dict, kind: str) -> tuple[str, str, str]:
    r = q[kind]
    rule, ref, base = (UP5, REF_UP5, BASE_UP5) if kind == "up5" else (UP10, REF_UP10, BASE_UP10)
    rise = "+5%" if kind == "up5" else "+10%"
    band = _band(r["score"])
    n, ok, basis = rate_of(r, kind)
    p = _pct(n, ok)
    big = (f'<div class="pc-big"><div class="pc-k">この戻りが本物の底になる率</div><div class="pc-v">{p}<small>%</small></div>'
           f'<div class="pc-w">{_word(p)}</div></div>')
    nxt = q["low_close"] * 1.10 if kind == "up5" else None
    say = (f'{_md(r["date"])}に安値から{rise}戻した。本物の底らしさは<b>○{r["score"]}つ</b>（3つ中）。'
           f'過去に同じ条件（{basis}）だった{n}回のうち{ok}回が本物の底だった（全体では{_pct(base[0], base[1])}%）。')
    if q.get("decline_type") == CREDIT_TYPE:
        say += ('<br><b>注意</b>：今回の下げは信用不安型。過去、信用不安型の下げからの戻りは本物の底になりにくかった'
                '（+5%の戻りで9%・35%、ほかの型は63%・50%。1990〜2007年・2008〜2026年）。')
    watch = (f'終値で安値<b>{q["low_close"]:.2f}</b>を割ると失敗。'
             + (f'安値から+10%（<b>{nxt:.2f}</b>）に届いたら、もう一度判定する。' if nxt else "")
             + (f'高値の−2%（<b>{q["high"] * 0.98:.2f}</b>）まで戻れば本物の底。' if q.get("high") else "高値から−2%以内まで戻れば本物の底。"))
    ea = EASE_ALL[kind]
    detail = (_odds_table(ref, band) + f'<div class="pc-p pc-mut">最近の例（○＝本物の底）：{html.escape(EXAMPLES[kind][band])}</div>'
              f'<div class="pc-p pc-mut">補助の金融環境：引き締まっていない戻りは{_pct(ea[True][0], ea[True][1])}%'
              f'（{ea[True][1]}/{ea[True][0]}回、1990〜2007 {_pct(*ea[True][2])}%・2008〜2026 {_pct(*ea[True][3])}%）、'
              f'引き締まり中は{_pct(ea[False][0], ea[False][1])}%（同 {_pct(*ea[False][2])}%・{_pct(*ea[False][3])}%）。'
              f'○の数が同じでも差が出たので、同じ組み合わせが{CELL_MIN}回以上ある場合は大きな数字に反映している。</div>')
    if kind == "up10" and r.get("type"):
        detail += (f'<div class="pc-p"><b>上げの中身：{html.escape(r["type"])}</b>　{html.escape(TYPES[r["type"]])}'
                   '型ごとのその後の成績は期間によって逆になったため、予想には使いません。</div>')
    return big + f'<div class="pc-p">{say}</div>' + _signs(r, rule, rise), \
        f'<div class="pc-h">ここを見る（QQQ）</div>{_ladder(q, nxt)}<div class="pc-p">{watch}</div>', detail


def key_of(state: dict) -> str:
    """One line for the folded card: the phase and its number."""
    q, s = state["qqq"], state.get("spy") or {}
    ph = phase_of(state)
    out = [dict(PHASES)[ph]]
    if ph in ("up5", "up10"):
        n, ok, _ = rate_of(q[ph], ph)
        out.append(f"本物の底になる率 {_pct(n, ok)}%")
    elif ph == "down":
        out.append(f'高値から{_signed(q["dd"])}%')
    ev = s.get("event") or {}
    if ev.get("status") == "open":
        n, hit = REF_DOWN["hi" if ev.get("vix") is not None and ev["vix"] >= VIX_CUT else "lo"][:2]
        out.append(f"S&P500が−10%まで {_pct(n, hit)}%")
    return "｜".join(out)


def card_html(state: dict) -> str:
    q, s = state["qqq"], state.get("spy") or {}
    ph = phase_of(state)
    steps = "".join(f'<span class="pc-st{" pc-on" if k == ph else ""}">{t}</span>' for k, t in PHASES)
    main, watch, detail = "", "", ""
    if ph in ("up5", "up10"):
        main, watch, detail = _rally_parts(q, ph)
        head = f'QQQは{_md(q["low"])}の安値から{_signed(q["from_low"])}%（高値から{_signed(q["dd"])}%）'
    elif ph == "down":
        head = f'QQQは高値から{_signed(q["dd"])}%、{_md(q["low"])}の安値から{_signed(q["from_low"])}%'
        main = (f'<div class="pc-p">まだ安値から+5%戻していない。<b>{q["low_close"] * 1.05:.2f}</b>以上で引けた日に、'
                '本物の底らしさを判定する。</div>')
        f = (q.get("failed") or [None])[-1]
        if f:
            main += (f'<div class="pc-p pc-mut">直前の戻り（{_md(f["date"])}、○{f["score"]}つ）は'
                     f'{_md(f["broke"])}に安値を割って失敗した。</div>')
    else:
        head = f'QQQは高値から{_signed(q["dd"])}%'
        if ph == "high":
            main = '<div class="pc-p">特別な局面ではない。S&P500が高値から−5%に入ったら「下げの初動」を判定する。</div>'
    ev = s.get("event") or {}
    spy_box = ""
    if ev.get("status") == "open":
        hi_ = ev.get("vix") is not None and ev["vix"] >= VIX_CUT
        k = "hi" if hi_ else "lo"
        n, hit, h1, h2 = REF_DOWN[k]
        other = REF_DOWN["lo" if hi_ else "hi"]
        lvl = f'（SPY {s["high"] * 0.90:.2f}）' if s.get("high") else ""
        spy_box = (f'<div class="pc-sub"><div class="pc-h">S&P500の下げの初動</div>'
                   f'<div class="pc-big pc-big-s"><div class="pc-k">−10%まで下げる率</div><div class="pc-v">{_pct(n, hit)}<small>%</small></div>'
                   f'<div class="pc-w">VIX {ev["vix"] if ev.get("vix") is not None else "未取得"}（{VIX_CUT:.0f}{"以上" if hi_ else "未満"}）</div></div>'
                   f'<div class="pc-p">{_md(ev["date"])}に高値から−5%に入った（今は{_signed(s["dd"])}%）。その日のVIXが'
                   f'{VIX_CUT:.0f}{"以上" if hi_ else "未満"}だった過去{n}回のうち{hit}回が−10%{lvl}まで下げた'
                   f'（VIX{"低め" if hi_ else "高め"}なら{_pct(other[0], other[1])}%）。</div>'
                   f'<div class="pc-p pc-mut">1990〜2007 {_pct(*h1)}%、2008〜2026 {_pct(*h2)}%。最近の例（○＝到達）：{html.escape(EXAMPLES["down"][k])}。'
                   'Nasdaq100では見分けられる要素がなかったため、S&P500で見ている。</div></div>')
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    body = (f'<div class="pc-steps">{steps}</div><div class="pc-head">{head}</div>{main}{watch}{spy_box}'
            f'<details class="pc-def"><summary>くわしく（過去の率・判定のしかた）</summary>{detail}<ul>'
            '<li><b>下げ</b>：Nasdaq100（QQQ）が252日の高値から−10%以下。高値から−2%以内に戻るまで続く。</li>'
            '<li><b>上げの初動</b>：その途中で、それまでの最安値（終値）から+5%戻した最初の日。新しい安値を付けたら判定し直す。'
            '<b>上げ</b>は同じく+10%の日。</li>'
            '<li><b>本物の底</b>：その後、安値を終値で割る前に高値から−2%以内まで戻ったもの。1990年以降、+5%の戻り105回のうち42%。</li>'
            '<li><b>3つの○</b>は、1990〜2007年と2008〜2026年の両方で本物の底の率を10ポイント以上分けたものだけ。'
            '急騰する戻りほど、下げ相場の一時的な戻りになりやすい。+10%では「11日以上」「4%未満」で判定。'
            'FTDがあった+10%の戻りは65%、なかった戻りは29%（2000年以降）。</li>'
            '<li><b>下げの初動</b>：S&P500が高値から−5%に入った最初の日（−2%以内に戻ると再判定）。−10%まで行ったのは全体で26%。</li>'
            '<li>数字はNasdaq100・S&P500指数での検証（research/phase-starts-2026-11）。表示のみで、売買ルールは変えません。</li>'
            f'</ul></details><div class="sub">{html.escape(state["session"])} 終値時点。</div>')
    return (f'<div class="card pc-card" id="{CARD_ID}">'
            + fold.card("phase-check", '<h2>局面チェック<span class="h2en">Phase Check</span></h2>', key_of(state), body)
            + f'<script id="{STATE_ID}" type="application/json">{raw}</script><span class="pc-end"></span></div>')


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.pc-card .pc-steps{display:flex;gap:3px;margin:2px 0 10px}'
    '.pc-card .pc-st{flex:1;text-align:center;font-size:10.5px;font-weight:700;padding:5px 1px;border-radius:5px;'
    'background:var(--ds-surface-2,#f4f2ec);color:var(--ds-muted,#6b685e);white-space:nowrap}'
    '.pc-card .pc-st.pc-on{background:var(--ds-ink,#1c1b19);color:var(--ds-surface,#fff)}'
    '.pc-card .pc-head{font-size:13px;font-weight:700;color:var(--ds-ink,#1c1b19);margin-bottom:6px}'
    '.pc-card .pc-big{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;padding:8px 10px;border-radius:8px;'
    'background:var(--ds-surface-2,#f4f2ec);margin:4px 0 6px}'
    '.pc-card .pc-k{font-size:12px;font-weight:700;color:var(--ds-ink-2,#46443d);flex-basis:100%}'
    '.pc-card .pc-v{font-size:30px;font-weight:800;line-height:1.1;color:var(--ds-ink,#1c1b19)}'
    '.pc-card .pc-v small{font-size:15px;margin-left:1px}'
    '.pc-card .pc-w{font-size:13px;font-weight:700;color:var(--ds-ink-2,#46443d)}'
    '.pc-card .pc-p{font-size:12.5px;line-height:1.65;color:var(--ds-ink-2,#46443d);margin:4px 0}'
    '.pc-card .pc-mut{color:var(--ds-muted,#6b685e);font-size:11.5px}'
    '.pc-card .pc-h{font-size:13px;font-weight:800;color:var(--ds-ink,#1c1b19);margin:10px 0 2px}'
    '.pc-card .pc-s{list-style:none;margin:4px 0;padding:0}'
    '.pc-card .pc-s li{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.5;padding:3px 0;color:var(--ds-ink,#1c1b19)}'
    '.pc-card .pc-s li i{font-style:normal;font-weight:800;width:1.1em;text-align:center}'
    '.pc-card .pc-s small{display:block;font-size:11px;color:var(--ds-muted,#6b685e)}'
    '.pc-card .pc-y{color:var(--ds-up,#17703f)}.pc-card .pc-n{color:var(--ds-down,#b3362c)}'
    '.pc-card .pc-lad{display:block;width:100%;height:auto;margin:2px 0}'
    '.pc-card .pc-axis{stroke:var(--ds-line,#dedbd2);stroke-width:4;stroke-linecap:round}'
    '.pc-card .pc-bad{fill:var(--ds-down,#b3362c)}.pc-card .pc-good{fill:var(--ds-up,#17703f)}'
    '.pc-card .pc-tick{stroke:var(--ds-muted,#6b685e);stroke-width:2}'
    '.pc-card .pc-now{fill:var(--ds-ink,#1c1b19)}'
    '.pc-card .pc-lt{font-size:10.5px;fill:var(--ds-muted,#6b685e)}.pc-card .pc-nt{font-size:11px;font-weight:700;fill:var(--ds-ink,#1c1b19)}'
    '.pc-card .pc-sub{margin-top:10px;padding-top:6px;border-top:1px solid var(--ds-line,#dedbd2)}'
    '.pc-card .pc-t{width:100%;border-collapse:collapse;margin:6px 0 2px;font-size:12px}'
    '.pc-card .pc-t th{font-size:11px;font-weight:600;color:var(--ds-muted,#6b685e);text-align:right;padding:3px 4px}'
    '.pc-card .pc-t th:first-child,.pc-card .pc-t td:first-child{text-align:left}'
    '.pc-card .pc-t td{text-align:right;padding:4px;border-top:1px solid var(--ds-line,#dedbd2);color:var(--ds-ink-2,#46443d)}'
    '.pc-card .pc-t td small{display:block;font-size:10.5px;color:var(--ds-muted,#6b685e)}'
    '.pc-card .pc-t tr.pc-cur td{background:var(--ds-surface-2,#f4f2ec);font-weight:700}'
    '.pc-card .pc-def{margin-top:8px}'
    '.pc-card .pc-def summary{font-size:12.5px;font-weight:800;cursor:pointer;color:var(--ds-accent,#2659ab)}'
    '.pc-card .pc-def ul{padding-left:1.1em;margin:6px 0}'
    '.pc-card .pc-def li{font-size:12px;line-height:1.6;color:var(--ds-ink-2,#46443d);margin:2px 0}'
    '.pc-card .pc-end{display:none}'
    '</style>'
)
CARD_RE = re.compile(rf'<div class="card pc-card" id="{CARD_ID}">.*?<span class="pc-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def apply(text: str, state: dict | None) -> str:
    if not state:
        return text
    card = card_html(state)
    if CARD_RE.search(text):
        out = CARD_RE.sub(lambda _: card, text, count=1)
    else:
        at = text.find(f'<div class="card da-card" id="{da.CARD_ID}">')
        if at < 0:
            print("phase check: decline card not found; card not inserted", flush=True)
            return text
        out = text[:at] + card + text[at:]
    out = STYLE_RE.sub("", out)
    out = out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out
    return fold.ensure(out)


def embedded_state(text: str) -> dict | None:
    m = STATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def rerender(text: str, root: Path) -> str:
    """Display path: the state stored in the page; the committed seed when it is of the same session
    (it may carry fields an older page lacks) or when the page has none."""
    state = embedded_state(text)
    try:
        seed = json.loads((root / STATE_SEED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seed = None
    if seed and state and seed.get("session") == state.get("session"):
        state = seed
    if state is None:
        try:
            manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return text
        if not seed or seed.get("session") != manifest.get("session_date"):
            return text
        state = seed
    return apply(text, state)


def run(text: str, root: Path, session: str) -> str:
    market = da.load_market(root)
    state = build_state(market, da.load_slow(root), session) if market else None
    dec = da.embedded_state(text) or {}
    if state and dec.get("active") and dec.get("session") == state["session"]:
        state["qqq"]["decline_type"] = dec.get("type")
    if state is None:
        print("phase check: market inputs not usable; keeping the page as is", flush=True)
        return rerender(text, root)
    q = state["qqq"]
    print(f"phase check: QQQ dd={q['dd']} in_decline={q['in_decline']} up5={bool(q.get('up5'))} up10={bool(q.get('up10'))} "
          f"SPY event={(state.get('spy') or {}).get('event')}", flush=True)
    return apply(text, state)
