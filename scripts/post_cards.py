"""SNS用カード「相場の局面」 (Publish tab, display only), in the same frame and style as the original share cards.

A 1680x1080 card in an iframe (full-screen button; fits and rotates like the originals) built from the states the
Daily tab stores in the page, plus a small state computed in the refresh (seed/post-cards-state.json):
- QQQ over a year with each day's phase (下げ / 上げの初動 / 上げ) and every bounce judged, with its outcome
- the daily count of 本命 (swing picks) over two years (counts only; no names, no rule details)
- 局面チェック, the S&P 500 -10% check, the lamps (F1-F3), 今回の下げの中身, FTD, セクターの勢い, 予測の答え合わせ
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

BLOCK_ID = "post-cards"
STATE_ID = "post-cards-state"
STYLE_ID = "post-cards-style"
SEED = "seed/post-cards-state.json"
COUNTS = "seed/honmei-counts.json"
DAYS_Q, DAYS_C = 260, 520
COL = {"ink": "#1B1D1C", "mut": "#727569", "line": "#D5D1C6", "acc": "#17685C", "pos": "#1E7A4D", "posbg": "#DBEBDF",
       "neg": "#B23A2E", "negbg": "#F1DED9", "warn": "#B07A16", "warnbg": "#F0E6CF", "neubg": "#E6E3DB"}
SANS = "-apple-system,'Helvetica Neue',Arial,'Hiragino Sans','Noto Sans JP',sans-serif"
MONO = "ui-monospace,'SF Mono',Menlo,monospace"


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _md(day: str | None) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}" if day else ""


def _ym(day: str) -> str:
    return f"{day[:4]}年{int(day[5:7])}月"


def _sg(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:+.{nd}f}".replace("-", "−")


# ---------------------------------------------------------------- refresh-side state
def timeline(q: pd.Series) -> dict:
    """Each day's phase on QQQ and every +5% bounce with its outcome (the 局面チェック rules, replayed)."""
    import phase_check as pc
    hi = q.rolling(252, min_periods=200).max()
    dd = q / hi - 1
    ph, events = [], []
    indec, low, li, up5, up10, cur = False, 0.0, 0, False, False, None
    for t in range(len(q)):
        c, d = float(q.iloc[t]), dd.iloc[t]
        if pd.isna(d):
            ph.append("h")
            continue
        if not indec:
            if d <= pc.DECLINE:
                indec, low, li, up5, up10 = True, c, t, False, False
        elif d >= pc.NEAR_HIGH:
            indec = False
            if cur is not None:
                cur["ok"], cur = 1, None
        else:
            if c < low:
                if cur is not None:
                    cur["ok"], cur = 0, None
                low, li, up5, up10 = c, t, False, False
            else:
                if not up5 and c >= low * (1 + pc.UP5["rise"]):
                    up5 = True
                    cur = {"i": t, "date": str(q.index[t].date()), "score": pc._rally(q, li, t, pc.UP5)["score"], "ok": None}
                    events.append(cur)
                if not up10 and c >= low * (1 + pc.UP10["rise"]):
                    up10 = True
        ph.append("h" if not indec else ("u10" if up10 else "u5" if up5 else "d"))
    return {"phase": ph, "events": events}


def load_counts(root: Path, session: str) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        out.update(json.loads((root / COUNTS).read_text(encoding="utf-8")).get("counts", {}))
    except (OSError, ValueError):
        pass
    try:
        ses = json.loads((root / "track-record" / "signals.json").read_text(encoding="utf-8")).get("sessions", {})
        for d, s in ses.items():
            if d <= session:
                out[d] = len(s.get("best") or [])
    except (OSError, ValueError, AttributeError):
        pass
    return dict(sorted((d, v) for d, v in out.items() if d <= session))


def build_state(q: pd.Series, root: Path, session: str) -> dict:
    q = q[q.index <= pd.Timestamp(session)].dropna()
    tl = timeline(q)
    n = min(DAYS_Q, len(q))
    off = len(q) - n
    ev = [{"k": e["i"] - off, "date": e["date"], "score": e["score"], "ok": e["ok"]} for e in tl["events"] if e["i"] >= off]
    counts = load_counts(root, session)
    cd = list(counts)[-DAYS_C:]
    return {"session": session, "q_dates": [str(d.date()) for d in q.index[off:]], "q": [round(float(v), 2) for v in q.iloc[off:]],
            "phase": tl["phase"][off:], "events": ev, "c_dates": cd, "c": [counts[d] for d in cd]}


# ---------------------------------------------------------------- drawing helpers
def _qqq_chart(st: dict, w: int, h: int) -> str:
    q, ph, n = st["q"], st["phase"], len(st["q"])
    lo, hi = min(q) * 0.97, max(q) * 1.01
    pl, pr, pt, pb = 44, 58, 6, 22
    step = (w - pl - pr) / max(n - 1, 1)
    X = lambda i: pl + step * i  # noqa: E731
    Y = lambda v: pt + (h - pt - pb) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    band = {"d": COL["negbg"], "u5": COL["warnbg"], "u10": COL["posbg"]}
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ph[j + 1] == ph[i]:
            j += 1
        if ph[i] in band:
            x0, x1 = max(X(i) - step / 2, pl), min(X(j) + step / 2, w - pr)
            out.append(f'<rect x="{x0:.1f}" y="{pt}" width="{x1 - x0:.1f}" height="{h - pt - pb}" fill="{band[ph[i]]}"/>')
        i = j + 1
    for k in range(4):
        v = lo + (hi - lo) * (k + .5) / 4
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{COL["line"]}" stroke-dasharray="2 3"/>'
                   f'<text x="{pl - 6}" y="{Y(v) + 4:.1f}" font-family="{MONO}" font-size="10.5" fill="{COL["mut"]}" text-anchor="end">{v:.0f}</text>')
    for i, d in enumerate(st["q_dates"]):
        if i > 5 and d[:7] != st["q_dates"][i - 1][:7]:
            lab = f"{d[:4]}年1月" if d[5:7] == "01" else f"{int(d[5:7])}月"
            out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{h - pb}" y2="{h - pb + 4}" stroke="{COL["mut"]}"/>'
                       f'<text x="{X(i):.1f}" y="{h - 6}" font-family="{SANS}" font-size="10.5" fill="{COL["mut"]}" text-anchor="middle">{lab}</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(q))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{COL["ink"]}" stroke-width="2" stroke-linejoin="round"/>')
    for e in st["events"]:
        x, y = X(e["k"]), Y(q[e["k"]])
        col = COL["pos"] if e["ok"] == 1 else COL["neg"] if e["ok"] == 0 else COL["warn"]
        mark = "○" if e["ok"] == 1 else "×" if e["ok"] == 0 else "?"
        out.append(f'<path d="M{x:.1f},{y + 8:.1f} l-7,12 h14 z" fill="{col}"/>'
                   f'<rect x="{x - 19:.1f}" y="{y + 23:.1f}" width="38" height="18" rx="5" fill="#fff" stroke="{col}"/>'
                   f'<text x="{x:.1f}" y="{y + 36:.1f}" font-family="{SANS}" font-size="11.5" font-weight="800" fill="{col}" text-anchor="middle">{mark} {e["score"]}</text>')
    x, y = X(n - 1), Y(q[-1])
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{COL["ink"]}" stroke="#fff" stroke-width="2"/>'
               f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" font-family="{MONO}" font-size="12" font-weight="800" fill="{COL["ink"]}">{q[-1]:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


def _bars(st: dict, w: int, h: int) -> str:
    c, d = st["c"], st["c_dates"]
    n = len(c)
    top = max(max(c) if c else 1, 1)
    pl, pb = 24, 20
    bw = (w - pl) / max(n, 1)
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    i = 0
    while i < n:                                  # pale band where there were no picks at all
        if c[i] == 0:
            j = i
            while j + 1 < n and c[j + 1] == 0:
                j += 1
            if j - i >= 2:
                out.append(f'<rect x="{pl + i * bw:.1f}" y="0" width="{(j - i + 1) * bw:.1f}" height="{h - pb}" fill="{COL["neubg"]}"/>')
            i = j + 1
        else:
            i += 1
    for k in sorted({0, top // 2, top}):
        y = (h - pb) * (1 - k / top)
        out.append(f'<line x1="{pl}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" stroke="{COL["line"]}" stroke-dasharray="2 3"/>'
                   f'<text x="{pl - 5}" y="{min(max(y + 4, 10), h - pb):.1f}" font-family="{MONO}" font-size="10" fill="{COL["mut"]}" text-anchor="end">{k}</text>')
    for i, v in enumerate(c):
        if v:
            bh = (h - pb) * v / top
            out.append(f'<rect x="{pl + i * bw:.2f}" y="{h - pb - bh:.1f}" width="{max(bw - .4, .8):.2f}" height="{bh:.1f}" fill="{COL["acc"]}"/>')
    for i, day in enumerate(d):
        if i and day[:7] != d[i - 1][:7] and int(day[5:7]) in (1, 4, 7, 10):
            lab = f"{day[:4]}年" if day[5:7] == "01" else f"{int(day[5:7])}月"
            out.append(f'<text x="{pl + i * bw:.1f}" y="{h - 5}" font-family="{SANS}" font-size="10.5" fill="{COL["mut"]}" text-anchor="middle">{lab}</text>')
    out.append("</svg>")
    return "".join(out)


def _spark(vals: list, w: int, h: int, warn: float, bad: float) -> str:
    vals = [v for v in vals if v is not None]
    n = len(vals)
    X = lambda i: w * i / max(n - 1, 1)  # noqa: E731
    Y = lambda v: h * (1 - min(max(v, 0), .8) / .8)  # noqa: E731
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    col = COL["neg"] if vals[-1] >= bad else COL["warn"] if vals[-1] >= warn else COL["pos"]
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect x="0" y="0" width="{w}" height="{Y(bad):.1f}" fill="{COL["negbg"]}"/>'
            f'<rect x="0" y="{Y(bad):.1f}" width="{w}" height="{Y(warn) - Y(bad):.1f}" fill="{COL["warnbg"]}"/>'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.8"/></svg>')


def _levels(q: dict, kind: str) -> str:
    """QQQ: the close that fails the bounce, the level of a real bottom, and now."""
    if kind not in ("up5", "up10") or not (q.get("low_close") and q.get("high") and q.get("close")):
        return ""
    lo, top, now = q["low_close"], q["high"] * 0.98, q["close"]
    w, x0, x1 = 360, 14, 346
    X = lambda v: x0 + (x1 - x0) * (min(max(v, lo), top) - lo) / (top - lo)  # noqa: E731
    svg = (f'<svg viewBox="0 0 {w} 62" width="{w}" height="62">'
           f'<line x1="{x0}" x2="{x1}" y1="30" y2="30" stroke="{COL["line"]}" stroke-width="6" stroke-linecap="round"/>'
           f'<circle cx="{x0}" cy="30" r="6" fill="{COL["neg"]}"/><circle cx="{x1}" cy="30" r="6" fill="{COL["pos"]}"/>'
           f'<path d="M{X(now):.1f},22 l-7,-12 h14 z" fill="{COL["ink"]}"/>'
           f'<text x="{min(max(X(now), 40), w - 40):.1f}" y="8" font-family="{MONO}" font-size="11" font-weight="800" fill="{COL["ink"]}" text-anchor="middle">今 {now:.2f}</text>'
           f'<text x="0" y="56" font-family="{SANS}" font-size="11" font-weight="800" fill="{COL["neg"]}">割ると失敗 {lo:.2f}</text>'
           f'<text x="{w}" y="56" font-family="{SANS}" font-size="11" font-weight="800" fill="{COL["pos"]}" text-anchor="end">本物の底 {top:.2f}</text></svg>')
    return f'<div class="k" style="margin-top:auto;padding-top:8px;border-top:1px solid var(--line)">QQQ ここを見る（終値）</div>{svg}'


CSS = """
*{box-sizing:border-box;margin:0;padding:0}html{-webkit-text-size-adjust:100%;height:100%}
body{background:#E9E7DF;font-family:-apple-system,'Helvetica Neue',Arial,'Hiragino Sans','Noto Sans JP',sans-serif;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#1B1D1C}
.stage{width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}.scaler{transform-origin:center center;flex:none}
.card{width:1680px;height:1080px;background:#E9E7DF;color:#1B1D1C;padding:22px 26px 14px;display:flex;flex-direction:column;
--ink:#1B1D1C;--mut:#727569;--line:#D5D1C6;--card:#F6F4EE;--accent:#17685C;--pos:#1E7A4D;--posbg:#DBEBDF;--neg:#B23A2E;--negbg:#F1DED9;
--warn:#B07A16;--warnbg:#F0E6CF;--neubg:#E6E3DB;--fnum:ui-monospace,'SF Mono',Menlo,monospace}
.num{font-family:var(--fnum);font-variant-numeric:tabular-nums;letter-spacing:-.01em}.pos{color:var(--pos)}.neg{color:var(--neg)}.warnc{color:var(--warn)}
.hd{display:flex;align-items:center;gap:12px;margin-bottom:8px}.hd .bar{width:5px;height:24px;background:var(--accent);border-radius:3px}
.hd h1{font-size:24px;font-weight:800;letter-spacing:-.02em}.hd .state{font-size:13px;font-weight:800;border:1.5px solid;border-radius:8px;padding:3px 12px}
.hd .stats{font-size:12.5px;color:var(--mut);font-weight:700}.hd .stats b{color:var(--ink)}.hd .date{margin-left:auto;font-size:14px;color:var(--mut);font-weight:700}
.read{font-size:14px;font-weight:700;color:#33352E;margin-bottom:10px;line-height:1.4;padding:8px 12px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px}
.read b{color:var(--accent)}.read .dn{color:var(--neg)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:392px 266px 1fr;gap:10px;flex:1;min-height:0}
.sp2{grid-column:span 2}.sp3{grid-column:span 3}
.t{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px;min-height:0;overflow:hidden;display:flex;flex-direction:column}
.th{display:flex;align-items:center;gap:6px;margin-bottom:6px;white-space:nowrap}.th h4{font-size:13.5px;font-weight:800;letter-spacing:-.01em}
.th h4 .en{font-size:9px;font-weight:600;color:var(--mut);margin-left:5px;letter-spacing:.02em}.th .s{font-size:10.5px;color:var(--mut);font-weight:700;overflow:hidden;text-overflow:ellipsis}
.th .s b{color:var(--ink);font-family:var(--fnum)}
.lg{display:flex;gap:10px;font-size:10.5px;color:var(--mut);font-weight:700;margin-left:auto}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:3px;vertical-align:-1px}
.steps{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}.steps span{font-size:12.5px;font-weight:800;padding:5px 10px;border-radius:7px;background:var(--neubg);color:var(--mut)}
.steps span.on{background:var(--ink);color:#fff}
.big{display:flex;align-items:baseline;gap:4px}.big .v{font-size:58px;font-weight:800;line-height:1;font-family:var(--fnum);letter-spacing:-.03em}
.big .u{font-size:22px;font-weight:800}.big .w{font-size:14px;font-weight:800;margin-left:8px}.k{font-size:11.5px;color:var(--mut);font-weight:700;margin-bottom:3px}
.sg{display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;margin-top:8px;font-size:12px;font-weight:700}
.sub{font-size:11.5px;color:var(--mut);font-weight:700;line-height:1.5;margin-top:6px}.sub b{color:var(--ink)}
.lamp{display:grid;grid-template-columns:92px 230px 1fr;align-items:center;gap:8px;margin:3px 0}.lamp .n{font-size:13px;font-weight:800;line-height:1.1}.lamp .n small{display:block;font-size:9.5px;color:var(--mut)}
.lamp .v{font-family:var(--fnum);font-weight:800;font-size:16px;text-align:right}.lamp svg{display:block}
table.an{width:100%;border-collapse:collapse;font-size:12.5px}table.an th{font-size:10.5px;color:var(--mut);text-align:right;font-weight:700;padding:3px 6px;border-bottom:1.5px solid var(--line)}
table.an th:first-child,table.an td:first-child{text-align:left}table.an td{padding:6px;text-align:right;border-bottom:1px solid var(--line);font-family:var(--fnum);font-weight:700}
table.an td small{font-family:-apple-system,'Hiragino Sans',sans-serif;color:var(--mut);font-weight:700;font-size:10px;margin-left:6px}
.typ{font-size:22px;font-weight:800;margin:0 0 8px}.typ small{font-size:12px;color:var(--mut);margin-left:8px}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.chips span{font-size:11px;font-weight:800;padding:2px 7px;border-radius:6px;background:var(--negbg);color:var(--neg)}
.chips span.c{background:var(--neubg);color:var(--mut)}.row{font-size:12px;font-weight:700;line-height:1.45;padding:4px 0;border-bottom:1px solid var(--line)}.row b{font-family:var(--fnum)}
.row:last-child{border-bottom:0}.foot{font-size:10.5px;color:var(--mut);font-weight:700;margin-top:7px;display:flex}.foot span{margin-left:auto;color:var(--accent);font-weight:800}
"""
FIT = ("<script>function fit(){var s=document.getElementById('scaler');var W=window.innerWidth,H=window.innerHeight,cw=1680,ch=1080;"
       "if(H>W){var sc=Math.min(W/ch,H/cw);s.style.transform='rotate(90deg) scale('+sc+')';}else{var sc=Math.min(W/cw,H/ch);"
       "s.style.transform='scale('+sc+')';}s.style.width=cw+'px';s.style.height=ch+'px';}fit();window.addEventListener('resize',fit);</script>")


def card_doc(st: dict, page: str, root: Path) -> tuple[str, str]:
    import phase_check as pc
    import decline_anatomy as da
    import regime_history as rh
    import ftd_check as fc
    import sector_heat as sh
    import prediction_log as pl
    ph = pc.embedded_state(page) or {}
    dec = da.embedded_state(page) or {}
    reg = rh.embedded_state(page)
    ftd = fc.embedded_state(page) or {}
    heat = sh.embedded_state(page)
    q = ph.get("qqq") or {}
    s = ph.get("spy") or {}
    kind = pc.phase_of(ph) if ph else "high"
    label = dict(pc.PHASES)[kind]
    colk = {"high": "pos", "down_start": "warn", "down": "neg", "up5": "warn", "up10": "pos"}[kind]
    cap: list[str] = []
    # header + one reading line
    stats = f'QQQ 高値から <b class="num">{_sg(q.get("dd"))}%</b>'
    if s:
        stats += f' ・ S&amp;P500 <b class="num">{_sg(s.get("dd"))}%</b>'
    if dec.get("active"):
        stats += f' ・ 下げ <b class="num">{dec.get("days_now")}</b>日目'
    read = f'QQQは<b>{label}</b>'
    p_bottom = None
    if kind in ("up5", "up10"):
        r = q[kind]
        n, ok, basis = pc.rate_of(r, kind)
        p_bottom = pc._pct(n, ok)
        read += f'（{_md(q.get("low"))}の安値から{"+5%" if kind == "up5" else "+10%"}）。この戻りが本物の底になる率は<b>{p_bottom}%</b>'
        cap.append(f"QQQは{_md(q.get('low'))}の安値から戻した「{label}」。本物の底になる率は過去検証で{p_bottom}%。")
    elif kind == "down":
        read += f'、高値から<span class="dn">{_sg(q.get("dd"))}%</span>。安値から+5%戻した日に底らしさを判定'
        cap.append(f"QQQは高値から{_sg(q.get('dd'))}%の下げの途中。")
    ev = s.get("event") or {}
    p_down = n2 = hit = None
    if ev.get("status") == "open":
        kk = "hi" if ev.get("vix") is not None and ev["vix"] >= pc.VIX_CUT else "lo"
        n2, hit = pc.REF_DOWN[kk][:2]
        p_down = pc._pct(n2, hit)
        read += f'。S&amp;P500は−5%入りの日のVIXが{ev.get("vix")}で、−10%まで行く率<span class="dn">{p_down}%</span>'
        cap.append(f"S&P500は−5%入りの日のVIXが{ev.get('vix')}、−10%まで行く率は{p_down}%。")
    if reg:
        read += f'。先導株の警戒灯は「{_e(rh.reading(reg)[1])}」'
    read += "。"
    # QQQ and the phase over a year
    t1 = (f'<div class="t sp3"><div class="th"><h4>QQQと局面<span class="en">QQQ · Market Phase (1Y)</span></h4>'
          f'<span class="s">▲ 安値から+5%戻した日（数字＝底打ちのしるし・○本物の底／×失敗／?判定待ち）</span>'
          f'<span class="lg"><span><i style="background:{COL["negbg"]}"></i>下げ</span><span><i style="background:{COL["warnbg"]}"></i>上げの初動</span>'
          f'<span><i style="background:{COL["posbg"]}"></i>上げ</span></span></div>{_qqq_chart(st, 1204, 338)}</div>')
    # the phase now
    steps = "".join(f'<span class="{"on" if k == kind else ""}">{t}</span>' for k, t in pc.PHASES)
    if p_bottom is not None:
        r = q[kind]
        word = "かなり期待" if p_bottom >= 80 else "五分五分" if p_bottom >= 40 else "戻りで終わりやすい"
        cw = "pos" if p_bottom >= 80 else "warnc" if p_bottom >= 40 else "neg"
        marks = "".join(f'<span class="{"pos" if v else "neg" if v is False else ""}">{"○" if v else "×" if v is False else "−"} {nm}</span>'
                        for nm, v in zip(("トレンド", "戻りの速さ", "過熱なし", "金融環境"), list(r["signs"]) + [r.get("ease")]))
        core = (f'<div class="k">この戻りが本物の底になる率</div><div class="big"><span class="v {cw}">{p_bottom}</span>'
                f'<span class="u {cw}">%</span><span class="w {cw}">{word}</span></div><div class="sg">{marks}</div>')
    else:
        core = (f'<div class="k">QQQ 高値から</div><div class="big"><span class="v">{_sg(q.get("dd"))}</span><span class="u">%</span></div>'
                '<div class="sub">安値から+5%戻した日に底らしさを判定</div>')
    t2 = (f'<div class="t"><div class="th"><h4>いまの局面<span class="en">Phase Now</span></h4></div>'
          f'<div class="steps">{steps}</div>{core}</div>')
    # picks per day
    last = st["c"][-252:]
    share = round(sum(1 for v in last if v) / max(len(last), 1) * 100)
    zero = 0
    for v in reversed(st["c"]):
        if v:
            break
        zero += 1
    now = f'現在 <b>{zero}</b>日連続ゼロ' if zero else f'今日 <b>{st["c"][-1]}</b>件'
    t3 = (f'<div class="t sp2"><div class="th"><h4>本命候補の数<span class="en">Swing Picks per Day (2Y)</span></h4>'
          f'<span class="s">灰色＝候補ゼロ（地合いが悪く見送り）・過去1年で候補が出た日 <b>{share}%</b>・{now}</span></div>'
          f'{_bars(st, 790, 220)}</div>')
    cap.append(f"本命候補は{zero}日連続ゼロ（地合いが悪い日は出さない）。" if zero else f"本命候補は今日{st['c'][-1]}件。")
    # S&P 500 start of a decline
    if p_down is not None:
        cd = "neg" if p_down >= 40 else "warnc"
        t4core = (f'<div class="k">S&amp;P500が−10%まで下げる率</div><div class="big"><span class="v {cd}">{p_down}</span><span class="u {cd}">%</span></div>'
                  f'<div class="sub">{_md(ev["date"])}に高値から−5%入り（今 <b>{_sg(s.get("dd"))}%</b>）<br>その日のVIX <b>{ev.get("vix")}</b>（{pc.VIX_CUT:.0f}{"以上" if ev["vix"] >= pc.VIX_CUT else "未満"}）'
                  f'<br>同じ条件の過去{n2}回のうち{hit}回</div>')
    else:
        t4core = (f'<div class="k">S&amp;P500 高値から</div><div class="big"><span class="v">{_sg(s.get("dd"))}</span><span class="u">%</span></div>'
                  '<div class="sub">下げの初動の判定なし</div>')
    t4core += _levels(q, kind)
    t4 = f'<div class="t"><div class="th"><h4>下げの初動<span class="en">S&amp;P 500 · −5% Check</span></h4></div>{t4core}</div>'
    # the lamps
    lamps = ""
    if reg:
        for k, name, w_, b_ in rh.LAMPS:
            v = reg[k][-1]
            cv = "neg" if v >= b_ else "warnc" if v >= w_ else "pos"
            a, b = name.split(" ", 1)
            lamps += f'<div class="lamp"><div class="n">{a}<small>{b}</small></div>{_spark(reg[k], 230, 46, w_, b_)}<div class="v {cv}">{v * 100:.0f}%</div></div>'
        lamps += (f'<div class="sub">今の読み方：<b>{_e(rh.reading(reg)[1])}</b><br>'
                  '線の背景：薄黄＝注意・薄赤＝警戒（先導株の崩れ具合）</div>')
        cap.append(f"先導株の警戒灯 F1 {reg['f1'][-1] * 100:.0f}%・F2 {reg['f2'][-1] * 100:.0f}%・F3 {reg['f3'][-1] * 100:.0f}%。")
    t5 = f'<div class="t"><div class="th"><h4>先導株の警戒灯<span class="en">Leader Lamps (1Y)</span></h4></div>{lamps}</div>'
    # what this decline is made of
    like = "・".join(_ym(x["week"]) for x in (dec.get("now_like") or [])[:3])
    if dec.get("active"):
        rows = "".join(f'<tr><td>{_ym(a["peak"])}<small>{_e(a.get("type", "").replace("（資金移動）", ""))}</small></td>'
                       f'<td class="neg">{_sg(a["more"])}%</td><td class="{"pos" if a["r60"] >= 0 else "neg"}">{_sg(a["r60"])}%</td>'
                       f'<td class="{"pos" if a.get("r120", 0) >= 0 else "neg"}">{_sg(a.get("r120"))}%</td></tr>' for a in (dec.get("analogs") or [])[:3])
        t6core = (f'<div class="typ">{_e(dec["type"])}<small>QQQ {_sg(dec.get("dd_now"))}%・{dec.get("days_now")}日目</small></div>'
                  f'<table class="an"><tr><th>タイプと要因が近い過去の下げ</th><th>そこからさらに</th><th>60日後</th><th>120日後</th></tr>{rows}</table>'
                  f'<div class="sub">相場全体が今に近い時期：<b>{like}</b></div>')
        if dec.get("analogs"):
            cap.append(f"今回の下げは「{dec['type']}」。似た過去：" + "・".join(_ym(a["peak"]) for a in dec["analogs"][:3]) + "。")
    else:
        t6core = f'<div class="typ">10%以上の下げではない</div><div class="sub">相場全体が今に近い時期：<b>{like}</b></div>'
    t6 = f'<div class="t sp2"><div class="th"><h4>今回の下げの中身<span class="en">Decline Anatomy</span></h4></div>{t6core}</div>'
    # FTD and sector heat
    frows = ""
    for row in ftd.get("rows", []):
        r = row.get("ftd")
        if r is None:
            txt = "FTDなし"
        elif r.get("broken"):
            txt = f'{_md(r["date"])}のFTDは<span class="neg">騙し</span>（{_md(r["broken"]["date"])}に安値割れ）'
        else:
            p, _ = fc.odds(r)
            txt = f'{_md(r["date"])}にFTD（Day{r["day"]}）' + (f"・騙し率 <b>{p}%</b>" if p is not None else "")
        frows += f'<div class="row">{_e(row["label"])}：{txt}</div>'
    hot = ""
    if heat:
        hot = "".join(f'<span class="{"" if x["hot"] else "c"}">{_e(x["ja"])}</span>' for x in heat["sectors"])
        hot = f'<div class="k" style="margin-top:10px">セクターの勢い（左ほど強い・赤＝過熱）</div><div class="chips">{hot}</div>'
    t7 = f'<div class="t"><div class="th"><h4>FTD・セクター<span class="en">Follow-Through · Heat</span></h4></div>{frows}{hot}</div>'
    # predictions checked against outcomes
    log = pl.load(root)
    sm = pl.summary(log) if log.get("entries") else {"n": 0, "open": 0}
    lrows = ""
    for e in list(reversed(log.get("entries", [])))[:4]:
        res = "結果待ち" if e.get("outcome") is None else ('<span class="pos">○ 起きた</span>' if e["outcome"] else '<span class="neg">× 起きず</span>')
        lrows += f'<div class="row">{_md(e["event"])} {_e(pl.KINDS[e["kind"]])} <b>{e["prob"]}%</b> → {res}</div>'
    t8 = (f'<div class="t"><div class="th"><h4>予測の答え合わせ<span class="en">Live Track</span></h4></div>'
          f'<div class="sub" style="margin:0 0 4px">出した確率は初出の値で記録し、結果を自動で照合（解決 <b>{sm["n"]}</b>件・待ち <b>{sm["open"]}</b>件）</div>{lrows}</div>')
    doc = (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1" name="viewport"/>'
           f'<title>相場の局面</title><style>{CSS}</style></head><body><div class="stage"><div class="scaler" id="scaler"><div class="card">'
           '<div class="hd"><span class="bar"></span><h1>相場の局面 <span style="font-size:13px;font-weight:600;color:var(--mut);letter-spacing:.02em">Market Phase</span></h1>'
           f'<span class="state" style="color:var(--{colk})">{label}</span><span class="stats">{stats}</span>'
           f'<span class="date num">米国 {_e(st["session"])} 終値</span></div><div class="read">{read}</div><div class="grid">'
           f'{t1}{t2}{t3}{t4}{t5}{t6}{t7}{t8}</div>'
           '<div class="foot">確率はQQQ・S&amp;P500の1990〜2026年データでの過去検証による参考値。売買の推奨ではありません。<span>MC57 Dashboard</span></div>'
           f'</div></div></div>{FIT}</body></html>')
    text = f"【米国株 相場の局面 {_md(st['session'])}】\n" + "\n".join(cap) + "\n※過去検証に基づく参考値です。\n#米国株 #ナスダック"
    return doc, text


# ---------------------------------------------------------------- page block
STYLE = (f'<style id="{STYLE_ID}">#post-cards .pq-cap{{margin:6px 0 16px}}#post-cards .pq-cap>summary{{font-size:13px;font-weight:700;cursor:pointer}}'
         '#post-cards .pq-cap textarea{width:100%;min-height:150px;margin-top:6px;font-size:13px;line-height:1.55;padding:8px;border-radius:8px;'
         'border:1px solid var(--ds-line,#dedbd2);background:var(--ds-surface,#fff);color:var(--ds-ink,#1c1b19)}'
         '#post-cards .pq-copy{margin-top:6px;font-size:13px;font-weight:700;padding:8px 14px;border-radius:8px;border:1px solid var(--ds-line,#dedbd2);'
         'background:var(--ds-surface,#fff);color:var(--ds-ink,#1c1b19)}#post-cards .pq-end{display:none}</style>')
COPY = ("<script>(function(){var b=document.querySelector('#post-cards .pq-copy');if(!b)return;b.addEventListener('click',function(){"
        "var t=document.querySelector('#post-cards textarea');(navigator.clipboard?navigator.clipboard.writeText(t.value):Promise.reject())"
        ".then(function(){},function(){t.select();document.execCommand('copy');});b.textContent='コピーしました';"
        "setTimeout(function(){b.textContent='投稿文をコピー';},1500);});})();</script>")
BLOCK_RE = re.compile(rf'<div class="pq-wrap" id="{BLOCK_ID}">.*?<span class="pq-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def block_html(st: dict, page: str, root: Path) -> str:
    doc, text = card_doc(st, page, root)
    raw = json.dumps(st, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div class="pq-wrap" id="{BLOCK_ID}"><div class="msec"><div class="msec-l">相場の局面<span class="msec-en">Market Phase</span></div>'
            '<div class="msec-q">Dailyタブの分析をまとめたSNS用カード</div></div><div class="postwrap"><button class="pfsbtn" onclick="pfs(this,1)">⛶ 全画面表示</button>'
            f'<iframe class="postframe" srcdoc="{html.escape(doc, quote=True)}"></iframe>'
            '<button class="pfsclose" onclick="pfs(this,0)">✕</button></div>'
            f'<details class="pq-cap"><summary>投稿文の下書き</summary><textarea readonly>{_e(text)}</textarea>'
            '<button class="pq-copy" type="button">投稿文をコピー</button></details>'
            f'<script id="{STATE_ID}" type="application/json">{raw}</script>{COPY}<span class="pq-end"></span></div>')


def embedded_state(text: str) -> dict | None:
    m = STATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def _seed(root: Path) -> dict | None:
    try:
        return json.loads((root / SEED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _insert_at(text: str) -> int | None:
    """Right after the original share cards of the Publish tab (or at its top when there are none)."""
    m = re.search(r'<(?:div|section)\b[^>]*\bid="t-post1"[^>]*>', text)
    if not m:
        return None
    end = text.find("</section>", m.end())
    region = text[m.end():end if end > 0 else len(text)]
    last = None
    for w in re.finditer(r'<div class="postwrap">.*?</iframe>\s*(?:<button class="pfsclose"[^>]*>[^<]*</button>\s*)?</div>', region, re.S):
        last = w
    return m.end() + (last.end() if last else 0)


def apply(text: str, root: Path, state: dict | None = None) -> str:
    st = state or embedded_state(text)
    seed = _seed(root)
    if seed and (not st or seed.get("session", "") > st.get("session", "")):
        st = seed
    if not st:
        return text
    out = BLOCK_RE.sub("", text)
    at = _insert_at(out)
    if at is None:
        print("post cards: Publish tab not found; card not inserted", flush=True)
        return text
    out = out[:at] + block_html(st, out, root) + out[at:]
    out = STYLE_RE.sub("", out)
    return out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out


def rerender(text: str, root: Path) -> str:
    return apply(text, root)


def run(text: str, root: Path, session: str) -> str:
    import decline_anatomy as da
    market = da.load_market(root)
    px = da._closes(market) if market else None
    if px is None or da.INDEX not in px:
        print("post cards: market inputs not usable; keeping the stored card", flush=True)
        return apply(text, root)
    st = build_state(px[da.INDEX], root, session)
    try:
        (root / SEED).write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as exc:
        print(f"post cards: seed not written: {exc!r}", flush=True)
    return apply(text, root, st)
