"""SNS用カード「地合いと本命」 (Publish tab, display only), in the same frame and style as the original share cards.

A 1680x1080 card in an iframe (full-screen button; fits and rotates like the originals): QQQ over two years on the
market pulse's bands with the number of 本命 (swing picks) per day under it, the market now, how often picks appeared
by market band, the last 60 sessions, breadth and sector strength.  Counts only: no names, no rule details.
QQQ comes from the refresh (seed/post-cards-state.json); the pulse from data/mc57.json; counts from
seed/honmei-counts.json (local replay of the production rule) and track-record/signals.json.
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
DAYS = 504
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


# ---------------------------------------------------------------- state
WEAK, GOOD = 40.0, 55.0          # the site's own bands for the market pulse (market_internals_ui: 弱い <40, 良好 >=55)
BANDS = (("good", "良好", COL["posbg"], COL["pos"]), ("mixed", "混在", COL["neubg"], COL["mut"]), ("weak", "弱い", COL["negbg"], COL["neg"]))


def band_of(v: float | None) -> str | None:
    return None if v is None else "weak" if v < WEAK else "good" if v >= GOOD else "mixed"


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


def load_pulse(root: Path) -> dict[str, dict]:
    """date -> {pulse, a50, a200} from data/mc57.json (the market pulse and its breadth, two years)."""
    try:
        hist = json.loads((root / "data" / "mc57.json").read_text(encoding="utf-8")).get("history") or []
    except (OSError, ValueError):
        return {}
    out = {}
    for r in hist:
        m = r.get("metrics") or {}
        out[str(r.get("date"))[:10]] = {"pulse": r.get("mc57"), "a50": m.get("close_gt_sma50"), "a200": m.get("close_gt_sma200"),
                                         "a20": m.get("close_gt_sma20")}
    return out


def build_state(q: pd.Series, root: Path, session: str) -> dict:
    q = q[q.index <= pd.Timestamp(session)].dropna().iloc[-DAYS:]
    return {"session": session, "q_dates": [str(d.date()) for d in q.index], "q": [round(float(v), 2) for v in q]}


def series(st: dict, root: Path) -> dict:
    """QQQ, the pulse, its breadth and the pick counts on the QQQ sessions."""
    pulse = load_pulse(root)
    counts = load_counts(root, st["session"])
    d = st["q_dates"]
    pv = [(pulse.get(x) or {}).get("pulse") for x in d]
    return {"d": d, "q": st["q"], "pulse": pv, "band": [band_of(v) for v in pv],
            "a50": [(pulse.get(x) or {}).get("a50") for x in d], "a200": [(pulse.get(x) or {}).get("a200") for x in d],
            "c": [counts.get(x) for x in d]}


# ---------------------------------------------------------------- drawing
def _months(d: list[str], X, y: float) -> str:
    out = ""
    for i, day in enumerate(d):
        if i and day[:7] != d[i - 1][:7] and int(day[5:7]) in (1, 4, 7, 10):
            lab = f"{day[:4]}年" if day[5:7] == "01" else f"{int(day[5:7])}月"
            out += f'<text x="{X(i):.1f}" y="{y}" font-family="{SANS}" font-size="11" fill="{COL["mut"]}" text-anchor="middle">{lab}</text>'
    return out


def _main_chart(s: dict, w: int, h: int) -> str:
    """QQQ on the market pulse's bands (top) and the picks per day (bottom), one time axis."""
    q, d, n = s["q"], s["d"], len(s["q"])
    pl, pr = 46, 64
    top_h, gap, bar_h, axis = 370, 34, 186, 22
    step = (w - pl - pr) / max(n - 1, 1)
    X = lambda i: pl + step * i  # noqa: E731
    lo, hi = min(q) * 0.97, max(q) * 1.02
    Y = lambda v: 6 + (top_h - 6) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    fill = {k: f for k, _, f, _ in BANDS}
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    i = 0
    while i < n:
        j = i
        while j + 1 < n and s["band"][j + 1] == s["band"][i]:
            j += 1
        if s["band"][i]:
            x0, x1 = max(X(i) - step / 2, pl), min(X(j) + step / 2, w - pr)
            for y0, hh in ((6, top_h - 6), (top_h + gap, bar_h)):
                out.append(f'<rect x="{x0:.1f}" y="{y0}" width="{x1 - x0:.1f}" height="{hh}" fill="{fill[s["band"][i]]}"/>')
        i = j + 1
    for k in range(4):
        v = lo + (hi - lo) * (k + .5) / 4
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{COL["line"]}" stroke-dasharray="2 3"/>'
                   f'<text x="{pl - 6}" y="{Y(v) + 4:.1f}" font-family="{MONO}" font-size="11" fill="{COL["mut"]}" text-anchor="end">{v:.0f}</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(q))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{COL["ink"]}" stroke-width="2" stroke-linejoin="round"/>')
    x, y = X(n - 1), Y(q[-1])
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{COL["ink"]}" stroke="#fff" stroke-width="2"/>'
               f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" font-family="{MONO}" font-size="12" font-weight="800" fill="{COL["ink"]}">{q[-1]:.0f}</text>')
    out.append(f'<text x="{pl + 6}" y="22" font-family="{SANS}" font-size="12" font-weight="800" fill="{COL["ink"]}">QQQ</text>')
    # picks per day
    c = [v or 0 for v in s["c"]]
    cmax = max(max(c), 1)
    base = top_h + gap + bar_h
    for k in sorted({0, cmax}):
        yy = base - bar_h * k / cmax
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{COL["line"]}" stroke-dasharray="2 3"/>'
                   f'<text x="{pl - 6}" y="{yy + 4:.1f}" font-family="{MONO}" font-size="11" fill="{COL["mut"]}" text-anchor="end">{k}</text>')
    bw = max(step - .5, .8)
    for i, v in enumerate(c):
        if v:
            bh = bar_h * v / cmax
            out.append(f'<rect x="{X(i) - bw / 2:.2f}" y="{base - bh:.1f}" width="{bw:.2f}" height="{bh:.1f}" fill="{COL["acc"]}"/>')
    out.append(f'<text x="{pl + 6}" y="{top_h + gap + 16}" font-family="{SANS}" font-size="12" font-weight="800" fill="{COL["ink"]}">本命の数（日ごと）</text>')
    out.append(_months(d, X, h - 4))
    out.append("</svg>")
    return "".join(out)


def _spark(vals: list, w: int, h: int, col: str) -> str:
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    n = len(vals)
    X = lambda i: w * i / max(n - 1, 1)  # noqa: E731
    Y = lambda v: 2 + (h - 4) * (1 - v / 100)  # noqa: E731
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}"><line x1="0" x2="{w}" y1="{Y(50):.1f}" y2="{Y(50):.1f}" '
            f'stroke="{COL["line"]}" stroke-dasharray="2 3"/><polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.8"/></svg>')


CSS = """
*{box-sizing:border-box;margin:0;padding:0}html{-webkit-text-size-adjust:100%;height:100%}
body{background:#E9E7DF;font-family:-apple-system,'Helvetica Neue',Arial,'Hiragino Sans','Noto Sans JP',sans-serif;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#1B1D1C}
.stage{width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}.scaler{transform-origin:center center;flex:none}
.card{width:1680px;height:1080px;background:#E9E7DF;color:#1B1D1C;padding:22px 26px 14px;display:flex;flex-direction:column;
--ink:#1B1D1C;--mut:#727569;--line:#D5D1C6;--card:#F6F4EE;--accent:#17685C;--pos:#1E7A4D;--posbg:#DBEBDF;--neg:#B23A2E;--negbg:#F1DED9;
--warn:#B07A16;--warnbg:#F0E6CF;--neubg:#E6E3DB;--fnum:ui-monospace,'SF Mono',Menlo,monospace}
.num{font-family:var(--fnum);font-variant-numeric:tabular-nums;letter-spacing:-.01em}.pos{color:var(--pos)}.neg{color:var(--neg)}.mut{color:var(--mut)}
.hd{display:flex;align-items:center;gap:12px;margin-bottom:8px}.hd .bar{width:5px;height:24px;background:var(--accent);border-radius:3px}
.hd h1{font-size:24px;font-weight:800;letter-spacing:-.02em}.hd .state{font-size:13px;font-weight:800;border:1.5px solid;border-radius:8px;padding:3px 12px}
.hd .stats{font-size:12.5px;color:var(--mut);font-weight:700}.hd .stats b{color:var(--ink)}.hd .date{margin-left:auto;font-size:14px;color:var(--mut);font-weight:700}
.read{font-size:15px;font-weight:700;color:#33352E;margin-bottom:10px;line-height:1.4;padding:9px 12px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px}
.read b{color:var(--accent)}.read .dn{color:var(--neg)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:1fr 262px;gap:10px;flex:1;min-height:0}.sp3{grid-column:span 3}
.t{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px;min-height:0;overflow:hidden;display:flex;flex-direction:column}
.th{display:flex;align-items:center;gap:6px;margin-bottom:6px;white-space:nowrap}.th h4{font-size:13.5px;font-weight:800;letter-spacing:-.01em}
.th h4 .en{font-size:9px;font-weight:600;color:var(--mut);margin-left:5px;letter-spacing:.02em}.th .s{font-size:10.5px;color:var(--mut);font-weight:700}
.lg{display:flex;gap:10px;font-size:11px;color:var(--mut);font-weight:700;margin-left:auto}.lg i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.k{font-size:12px;color:var(--mut);font-weight:700;margin-bottom:3px}.big{display:flex;align-items:baseline;gap:4px}
.big .v{font-size:64px;font-weight:800;line-height:1;font-family:var(--fnum);letter-spacing:-.03em}.big .u{font-size:20px;font-weight:800;color:var(--mut)}
.big .w{font-size:16px;font-weight:800;margin-left:8px}.gauge{position:relative;height:12px;border-radius:6px;margin:10px 0 4px;
background:linear-gradient(90deg,var(--negbg) 0 40%,var(--neubg) 40% 55%,var(--posbg) 55% 100%)}
.gauge i{position:absolute;top:-5px;width:4px;height:22px;border-radius:2px;background:var(--ink);transform:translateX(-2px)}
.gl{display:flex;justify-content:space-between;font-size:10.5px;color:var(--mut);font-weight:700}
.sep{border-top:1px solid var(--line);margin:12px 0 10px}
.steps{display:flex;gap:3px;margin-top:4px}.steps span{flex:1;text-align:center;font-size:11.5px;font-weight:800;padding:6px 0;border-radius:6px;background:var(--neubg);color:var(--mut)}
.steps span.on{background:var(--ink);color:#fff}
.rate{display:grid;grid-template-columns:44px 1fr 52px;align-items:center;gap:8px;margin:9px 0}.rate .n{font-size:13px;font-weight:800}
.rate .b{height:22px;border-radius:5px;background:var(--neubg);overflow:hidden}.rate .b i{display:block;height:100%;border-radius:5px}
.rate .p{font-family:var(--fnum);font-weight:800;font-size:17px;text-align:right}
.sub{font-size:11.5px;color:var(--mut);font-weight:700;line-height:1.5;margin-top:auto}.sub b{color:var(--ink)}
.cal{display:grid;grid-template-columns:repeat(15,1fr);gap:4px;margin-top:4px}.cal span{height:30px;border-radius:5px;display:flex;align-items:center;justify-content:center;
font-family:var(--fnum);font-size:12px;font-weight:800;color:var(--acc2,#17685C)}.cal span.z{color:transparent}
.br{display:grid;grid-template-columns:96px 1fr 50px;align-items:center;gap:8px;margin:8px 0}.br .n{font-size:12.5px;font-weight:800;line-height:1.15}
.br .n small{display:block;font-size:10px;color:var(--mut)}.br .v{font-family:var(--fnum);font-weight:800;font-size:17px;text-align:right}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}.chips span{font-size:14px;font-weight:800;padding:6px 11px;border-radius:7px;background:var(--neubg);color:var(--mut)}
.chips span.h{background:var(--posbg);color:var(--pos)}.chips span.l{background:var(--negbg);color:var(--neg)}
.foot{font-size:10.5px;color:var(--mut);font-weight:700;margin-top:7px;display:flex}.foot span{margin-left:auto;color:var(--accent);font-weight:800}
"""
FIT = ("<script>function fit(){var s=document.getElementById('scaler');var W=window.innerWidth,H=window.innerHeight,cw=1680,ch=1080;"
       "if(H>W){var sc=Math.min(W/ch,H/cw);s.style.transform='rotate(90deg) scale('+sc+')';}else{var sc=Math.min(W/cw,H/ch);"
       "s.style.transform='scale('+sc+')';}s.style.width=cw+'px';s.style.height=ch+'px';}fit();window.addEventListener('resize',fit);</script>")


def card_doc(st: dict, page: str, root: Path) -> tuple[str, str]:
    import phase_check as pc
    import sector_heat as sh
    s = series(st, root)
    ph = pc.embedded_state(page) or {}
    heat = sh.embedded_state(page)
    q = ph.get("qqq") or {}
    kind = pc.phase_of(ph) if ph else None
    pulse = next((v for v in reversed(s["pulse"]) if v is not None), None)
    i5 = max(len(s["pulse"]) - 6, 0)
    p5 = s["pulse"][i5]
    band = band_of(pulse)
    bname = {k: n for k, n, _, _ in BANDS}.get(band, "—")
    bcol = {"good": "pos", "mixed": "mut", "weak": "neg"}.get(band, "mut")
    c = [v for v in s["c"] if v is not None]
    today = c[-1] if c else 0
    zero = 0
    for v in reversed(c):
        if v:
            break
        zero += 1
    last = c[-252:]
    share = round(sum(1 for v in last if v) / max(len(last), 1) * 100)
    # how often picks appeared, by band (the same two years)
    rows = []
    for k, name, _, col in BANDS:
        days = [cv for cv, b in zip(s["c"], s["band"]) if b == k and cv is not None]
        rows.append((k, name, col, len(days), round(sum(1 for v in days if v) / len(days) * 100) if days else None))
    good_p = next((r[4] for r in rows if r[0] == "good"), None)
    weak_p = next((r[4] for r in rows if r[0] == "weak"), None)
    cap = []
    # header and reading
    stats = f'マーケットパルス <b class="num">{pulse:.0f}</b>/100' if pulse is not None else ""
    stats += f' ・ 本命 <b class="num">{today}</b>件'
    if q.get("dd") is not None:
        stats += f' ・ QQQ 高値から <b class="num">{_sg(q["dd"])}%</b>'
    if zero:
        read = (f'市場内部は<span class="{"dn" if band == "weak" else ""}">{bname}</span>（マーケットパルス{pulse:.0f}）。'
                f'本命は<b>{zero}日連続ゼロ</b>、地合いが整うまで新規は待ち。')
        cap.append(f"市場内部は{bname}（マーケットパルス{pulse:.0f}/100）。本命は{zero}日連続ゼロ、待ちの局面。")
    else:
        read = f'市場内部は<b>{bname}</b>（マーケットパルス{pulse:.0f}）。本命は今日<b>{today}件</b>。'
        cap.append(f"市場内部は{bname}（マーケットパルス{pulse:.0f}/100）。本命は今日{today}件。")
    if kind:
        read += f'QQQは「{dict(pc.PHASES)[kind]}」。'
    if good_p is not None and weak_p is not None:
        cap.append(f"過去2年、内部が良好な日は{good_p}%の日で本命が出たのに対し、弱い日は{weak_p}%。")
    # main chart
    lg = "".join(f'<span><i style="background:{f}"></i>内部{n}</span>' for _, n, f, _ in BANDS)
    t1 = (f'<div class="t sp3"><div class="th"><h4>地合いと本命の推移<span class="en">Market Pulse × Swing Picks (2Y)</span></h4>'
          f'<span class="s">背景＝その日の市場内部（マーケットパルス）</span><span class="lg">{lg}</span></div>{_main_chart(s, 1204, 636)}</div>')
    # now
    steps = "".join(f'<span class="{"on" if k == kind else ""}">{t}</span>' for k, t in pc.PHASES) if kind else ""
    pos = min(max(pulse or 0, 0), 100)
    t2 = (f'<div class="t"><div class="th"><h4>いまの地合い<span class="en">Now</span></h4></div>'
          f'<div class="k">マーケットパルス（市場内部・0〜100）</div><div class="big"><span class="v {bcol}">{pulse:.0f}</span>'
          f'<span class="u">/100</span><span class="w {bcol}">内部{bname}</span></div>'
          f'<div class="gauge"><i style="left:{pos:.1f}%"></i></div><div class="gl"><span>弱い</span><span>混在</span><span>良好</span></div>'
          f'<div class="k" style="margin-top:6px">5日前から <b class="num" style="color:var(--ink)">{_sg(pulse - p5 if p5 is not None else None)}</b></div>'
          '<div class="sep"></div><div class="k">本命（今日）</div>'
          f'<div class="big"><span class="v">{today}</span><span class="u">件</span>'
          + (f'<span class="w neg">{zero}日連続ゼロ</span>' if zero else "") + '</div>'
          + f'<div class="k" style="margin-top:8px">過去1年で本命が出た日 <b class="num" style="color:var(--ink)">{share}%</b></div>'
          + (f'<div class="sep"></div><div class="k">QQQの局面</div><div class="steps">{steps}</div>' if steps else "")
          + '</div>')
    # picks by band
    rr = "".join(f'<div class="rate"><div class="n" style="color:{col}">{name}</div><div class="b"><i style="width:{p or 0}%;background:{col}"></i></div>'
                 f'<div class="p">{"—" if p is None else f"{p}%"}</div></div>' for _, name, col, n, p in rows)
    t3 = (f'<div class="t"><div class="th"><h4>本命が出た日の割合<span class="en">Picks by Market</span></h4><span class="s">市場内部別・過去2年</span></div>'
          f'{rr}<div class="sub">地合いが悪いほど本命は出にくい。<b>数を追わず、出る日だけ動く</b>。</div></div>')
    # last 60 sessions
    cells = ""
    fill = {k: f for k, _, f, _ in BANDS}
    for cv, b, d in list(zip(s["c"], s["band"], s["d"]))[-60:]:
        cells += f'<span class="{"" if cv else "z"}" style="background:{fill.get(b, COL["neubg"])}" title="{d}">{cv or 0}</span>'
    t4 = (f'<div class="t"><div class="th"><h4>直近60日<span class="en">Last 60 Sessions</span></h4><span class="s">色＝市場内部・数字＝本命の数</span></div>'
          f'<div class="cal">{cells}</div><div class="sub">{_md(s["d"][-60])}〜{_md(s["d"][-1])}・左上から古い順</div></div>')
    # breadth
    br = ""
    for key, name, sub in (("a50", "50日線より上", "中期の広がり"), ("a200", "200日線より上", "長期の広がり")):
        v = next((x for x in reversed(s[key]) if x is not None), None)
        col = COL["neg"] if v is not None and v < 40 else COL["pos"] if v is not None and v >= 60 else COL["warn"]
        br += (f'<div class="br"><div class="n">{name}<small>{sub}</small></div>{_spark(s[key][-252:], 190, 40, col)}'
               f'<div class="v" style="color:{col}">{"—" if v is None else f"{v:.0f}%"}</div></div>')
    t5 = (f'<div class="t"><div class="th"><h4>広がり<span class="en">Breadth (1Y)</span></h4><span class="s">主要57銘柄のうち線より上の割合</span></div>{br}</div>')
    # sector strength
    chips = ""
    if heat:
        secs = heat["sectors"]
        chips = "".join(f'<span class="{"h" if i < 3 else "l" if i >= len(secs) - 3 else ""}">{_e(x["ja"])}</span>' for i, x in enumerate(secs))
        cap.append("資金が向かうセクター：" + "・".join(x["ja"] for x in secs[:3]) + "。")
    t6 = (f'<div class="t"><div class="th"><h4>資金の向き先<span class="en">Sector Strength</span></h4><span class="s">左ほど強い</span></div>'
          f'<div class="chips">{chips}</div></div>')
    stc = {"good": "pos", "mixed": "mut", "weak": "neg"}.get(band, "mut")
    doc = (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1" name="viewport"/>'
           f'<title>地合いと本命</title><style>{CSS}</style></head><body><div class="stage"><div class="scaler" id="scaler"><div class="card">'
           '<div class="hd"><span class="bar"></span><h1>地合いと本命 <span style="font-size:13px;font-weight:600;color:var(--mut);letter-spacing:.02em">Market &amp; Picks</span></h1>'
           f'<span class="state" style="color:var(--{stc})">内部{bname}</span><span class="stats">{stats}</span>'
           f'<span class="date num">米国 {_e(st["session"])} 終値</span></div><div class="read">{read}</div><div class="grid">'
           f'{t1}{t2}{t3}{t4}{t5}{t6}</div>'
           '<div class="foot">本命＝MC57 Dashboardのルールで毎日選ぶスイング候補（銘柄とルールは非公開）。売買の推奨ではありません。<span>MC57 Dashboard</span></div>'
           f'</div></div></div>{FIT}</body></html>')
    text = f"【米国株 地合いと本命 {_md(st['session'])}】\n" + "\n".join(cap) + "\n#米国株 #ナスダック"
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
    return (f'<div class="pq-wrap" id="{BLOCK_ID}"><div class="msec"><div class="msec-l">地合いと本命<span class="msec-en">Market &amp; Picks</span></div>'
            '<div class="msec-q">SNS共有用カード</div></div><div class="postwrap"><button class="pfsbtn" onclick="pfs(this,1)">⛶ 全画面表示</button>'
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
