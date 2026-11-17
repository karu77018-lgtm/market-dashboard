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
def _rally(q: pd.Series, i0: int, t: int, rule: dict) -> dict:
    """Signs counted on day t for the rise from the low at i0."""
    ma50 = q.rolling(50, min_periods=50).mean()
    rets = q.pct_change().iloc[i0 + 1:t + 1] * 100
    above = None if pd.isna(ma50.iloc[t]) else bool(q.iloc[t] > ma50.iloc[t])
    days = int(t - i0)
    big = float(rets.max()) if len(rets) else 0.0
    signs = [above, days > rule["days"], big < rule["maxday"]]
    return {"date": str(q.index[t].date()), "days": days, "maxday": round(big, 2), "above50": above,
            "signs": [None if s is None else bool(s) for s in signs], "score": int(sum(bool(s) for s in signs))}


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
            cur["up5"] = _rally(q, cur["low_i"], t, UP5)
        if cur["arm10"] and c >= cur["low"] * (1 + UP10["rise"]):
            cur["arm10"] = False
            cur["up10"] = _rally(q, cur["low_i"], t, UP10)
            cur["up10"]["type"], cur["up10"]["drivers"] = _type(px, cur["low_i"], t, slow)
    t = len(q) - 1
    out: dict[str, Any] = {"dd": round(float(dd.iloc[t]) * 100, 1), "in_decline": indec, "last_end": last_end}
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
    return {"dd": round(float(dd.iloc[-1]) * 100, 1), "event": ev}


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


def _odds_table(ref: dict, band: str) -> str:
    rows = ""
    for b, label in (("0", "0個"), ("1-2", "1〜2個"), ("3", "3個")):
        n, ok, h1, h2 = ref[b]
        cur = ' class="pc-cur"' if b == band else ""
        rows += (f'<tr{cur}><td>{label}</td><td><b>{_pct(n, ok)}%</b><small>{ok}/{n}回</small></td>'
                 f'<td>{_pct(*h1)}%</td><td>{_pct(*h2)}%</td></tr>')
    return ('<table class="pc-t"><tr><th>当てはまる数</th><th>本物の底</th><th>1990〜2007</th><th>2008〜2026</th></tr>'
            f'{rows}</table>')


def _signs_list(r: dict, rule: dict, rise: str) -> str:
    a, d, m = r["signs"]
    mark = lambda ok: '<span class="pc-y">○</span>' if ok else ('<span class="pc-n">×</span>' if ok is False else "−")  # noqa: E731
    return ('<ul class="pc-s">'
            f'<li>{mark(a)} 50日線の上にいる</li>'
            f'<li>{mark(d)} ゆっくり戻した：{rise}まで{r["days"]}営業日（{rule["days"] + 1}日以上が○）</li>'
            f'<li>{mark(m)} 急騰の日がない：最大の上げ日 {_signed(r["maxday"])}%（{rule["maxday"]}%未満が○）</li></ul>')


def rally_html(r: dict, kind: str) -> str:
    rule, ref, base = (UP5, REF_UP5, BASE_UP5) if kind == "up5" else (UP10, REF_UP10, BASE_UP10)
    rise = "+5%" if kind == "up5" else "+10%"
    band = _band(r["score"])
    n, ok, _, _ = ref[band]
    ex = EXAMPLES[kind][band]
    out = (f'<div class="pc-h">本物の底らしさ：<b>{r["score"]}/3</b>（{_md(r["date"])}に安値から{rise}）</div>'
           + _signs_list(r, rule, rise)
           + f'<div class="pc-p">過去に同じ数だった{n}回のうち、本物の底だったのは<b>{_pct(n, ok)}%</b>'
             f'（全体では{_pct(base[0], base[1])}%）。最近の例（○＝本物の底）：{html.escape(ex)}</div>'
           + _odds_table(ref, band))
    if kind == "up10" and r.get("type"):
        out += (f'<div class="pc-h">上げの中身：<b>{html.escape(r["type"])}</b></div>'
                f'<div class="pc-p">{html.escape(TYPES[r["type"]])}型は戻りの説明で、型ごとのその後の成績は期間によって逆になったため予想には使いません。</div>')
    return out


def card_html(state: dict) -> str:
    q, s = state["qqq"], state.get("spy") or {}
    parts = []
    if q.get("in_decline"):
        up5, up10 = q.get("up5"), q.get("up10")
        watch = (f'今は{_md(q["low"])}の安値から{_signed(q["from_low"])}%、高値から{_signed(q["dd"])}%。'
                 f'安値{q["low_close"]:.2f}を終値で割ると失敗、高値から−2%以内に戻れば本物の底。')
        if up10:
            title, lead = "上げ（安値から+10%）", "QQQ：" + watch
            body = rally_html(up10, "up10")
        elif up5:
            title, lead = "上げの初動（安値から+5%）", "QQQ：" + watch
            body = rally_html(up5, "up5")
        else:
            title = "下げの途中"
            lead = (f'QQQは高値から{_signed(q["dd"])}%、{_md(q["low"])}の安値（{q["low_close"]:.2f}）から{_signed(q["from_low"])}%。'
                    f'安値から+5%戻した日に「本物の底らしさ」を判定します（{q["low_close"] * 1.05:.2f}以上の終値）。')
            body = ""
        fails = q.get("failed") or []
        if fails and not (up5 or up10):
            f = fails[-1]
            body += (f'<div class="pc-p">直前の戻り（{_md(f["date"])}に安値から{"+5%" if f["kind"] == "up5" else "+10%"}、'
                     f'本物の底らしさ{f["score"]}/3）は{_md(f["broke"])}に安値を割って失敗しました。</div>')
        parts.append((title, lead, body))
    else:
        end = q.get("last_end")
        lead = f'QQQは高値から{_signed(q["dd"])}%。10%以上の下げの途中ではありません。'
        if end:
            lead += f'前回の下げは{_md(end["low"])}の安値から戻り、{_md(end["date"])}に高値圏へ戻りました。'
        parts.append(("高値圏・通常", lead, ""))
    ev = s.get("event") if s else None
    if ev and ev["status"] == "open":
        hi_ = ev["vix"] is not None and ev["vix"] >= VIX_CUT
        k = "hi" if hi_ else "lo"
        n, hit, h1, h2 = REF_DOWN[k]
        lead = (f'S&P500（SPY）は{_md(ev["date"])}に高値から−5%（今は{_signed(s["dd"])}%）。'
                f'その日のVIXは<b>{"未取得" if ev["vix"] is None else ev["vix"]}</b>'
                f'（{VIX_CUT:.0f}以上{"に該当" if hi_ else "ではない"}）。')
        body = (f'<div class="pc-p">VIX{VIX_CUT:.0f}{"以上" if hi_ else "未満"}だった過去{n}回のうち、'
                f'−10%まで下げたのは<b>{_pct(n, hit)}%</b>（1990〜2007 {_pct(*h1)}%、2008〜2026 {_pct(*h2)}%）。'
                f'もう一方は{_pct(REF_DOWN["lo" if hi_ else "hi"][0], REF_DOWN["lo" if hi_ else "hi"][1])}%。'
                f'最近の例（○＝−10%到達）：{html.escape(EXAMPLES["down"][k])}</div>'
                '<div class="pc-p pc-mut">Nasdaq100ではVIXでも他の要素でも見分けられなかったため、S&P500で判定しています。</div>')
        parts.append(("下げの初動（S&P500 −5%）", lead, body))
    elif ev and ev["status"] == "reached" and q.get("in_decline"):
        pass
    sections = "".join(
        f'<div class="pc-sec"><div class="pc-tag">{html.escape(t)}</div><div class="pc-lead">{lead}</div>{body}</div>'
        for t, lead, body in parts)
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div class="card pc-card" id="{CARD_ID}"><div class="chd"><h2>局面チェック<span class="h2en">Phase Check</span></h2></div>'
            f'{sections}'
            '<details class="pc-def"><summary>判定のしかた</summary><ul>'
            '<li><b>下げの途中</b>：Nasdaq100（QQQ）が252日の高値から−10%以下。高値から−2%以内に戻るまで続く。</li>'
            '<li><b>上げの初動</b>：その途中で、それまでの最安値（終値）から+5%戻した最初の日。新しい安値を付けたら判定し直す。</li>'
            '<li><b>本物の底</b>：その後、安値を割る前に高値から−2%以内まで戻ったもの。1990年以降の105回で42%。</li>'
            '<li><b>3つのしるし</b>はどれも、1990〜2007年と2008〜2026年の両方で本物の底の率を10ポイント以上分けたもの。'
            '急騰する戻りほど下げ相場の一時的な戻りになりやすい。</li>'
            '<li><b>上げ</b>（+10%）でも同じ3つ（11日以上・最大の上げ日4%未満）で判定。FTDがあった戻りは65%、なかった戻りは29%（2000年以降）。</li>'
            '<li><b>下げの初動</b>：S&P500が高値から−5%に入った最初の日（−2%以内に戻ると再判定）。−10%まで行ったのは全体で26%。</li>'
            '<li>数字はNasdaq100・S&P500指数での検証（研究：research/phase-starts-2026-11）。表示のみで、売買ルールは変えません。</li>'
            '</ul></details>'
            f'<div class="sub">{html.escape(state["session"])} 終値時点。</div>'
            f'<script id="{STATE_ID}" type="application/json">{raw}</script><span class="pc-end"></span></div>')


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.pc-card .pc-sec{padding:8px 0;border-bottom:1px solid var(--ds-line,#dedbd2)}'
    '.pc-card .pc-sec:last-of-type{border-bottom:0}'
    '.pc-card .pc-tag{display:inline-block;font-size:13px;font-weight:800;padding:2px 8px;border-radius:6px;'
    'background:var(--ds-surface-2,#f4f2ec);color:var(--ds-ink,#1c1b19);margin-bottom:4px}'
    '.pc-card .pc-lead,.pc-card .pc-p{font-size:12.5px;line-height:1.65;color:var(--ds-ink-2,#46443d);margin:3px 0}'
    '.pc-card .pc-mut{color:var(--ds-muted,#6b685e);font-size:11.5px}'
    '.pc-card .pc-h{font-size:13px;font-weight:700;color:var(--ds-ink,#1c1b19);margin:8px 0 2px}'
    '.pc-card .pc-s{list-style:none;margin:2px 0;padding:0}'
    '.pc-card .pc-s li{font-size:12.5px;line-height:1.6;color:var(--ds-ink-2,#46443d)}'
    '.pc-card .pc-y{color:var(--ds-up,#17703f);font-weight:800}.pc-card .pc-n{color:var(--ds-down,#b3362c);font-weight:800}'
    '.pc-card .pc-t{width:100%;border-collapse:collapse;margin:6px 0 2px;font-size:12px}'
    '.pc-card .pc-t th{font-size:11px;font-weight:600;color:var(--ds-muted,#6b685e);text-align:right;padding:3px 4px}'
    '.pc-card .pc-t th:first-child,.pc-card .pc-t td:first-child{text-align:left}'
    '.pc-card .pc-t td{text-align:right;padding:4px;border-top:1px solid var(--ds-line,#dedbd2);color:var(--ds-ink-2,#46443d)}'
    '.pc-card .pc-t td small{display:block;font-size:10.5px;color:var(--ds-muted,#6b685e)}'
    '.pc-card .pc-t tr.pc-cur td{background:var(--ds-surface-2,#f4f2ec);font-weight:700}'
    '.pc-card .pc-def summary{font-size:12.5px;font-weight:800;cursor:pointer;color:var(--ds-accent,#2659ab);margin-top:6px}'
    '.pc-card .pc-def ul{padding-left:1.1em;margin:4px 0}.pc-card .pc-def li{font-size:12px;line-height:1.6;color:var(--ds-ink-2,#46443d);margin:2px 0}'
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
    return out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out


def embedded_state(text: str) -> dict | None:
    m = STATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def rerender(text: str, root: Path) -> str:
    state = embedded_state(text)
    if state is None:
        try:
            seed = json.loads((root / STATE_SEED).read_text(encoding="utf-8"))
            manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return text
        if seed.get("session") != manifest.get("session_date"):
            return text
        state = seed
    return apply(text, state)


def run(text: str, root: Path, session: str) -> str:
    market = da.load_market(root)
    state = build_state(market, da.load_slow(root), session) if market else None
    if state is None:
        print("phase check: market inputs not usable; keeping the page as is", flush=True)
        return rerender(text, root)
    q = state["qqq"]
    print(f"phase check: QQQ dd={q['dd']} in_decline={q['in_decline']} up5={bool(q.get('up5'))} up10={bool(q.get('up10'))} "
          f"SPY event={(state.get('spy') or {}).get('event')}", flush=True)
    return apply(text, state)
