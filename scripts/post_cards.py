"""SNS用カード「地合いと本命」 (Publish tab, display only), in the frame, style and density of the original share cards.

1680x1080 card in an iframe (full-screen button; fits and rotates like the originals).  It shows the market as the
swing rule sees it and how many 本命 (swing picks) came out, with counts only: no names and no rule details.
- 新規の可否: the entry gate today, its last 60 sessions and how far QQQ is from re-opening it
- 候補の流れ: today's funnel (liquid names -> selected -> each list of the screener)
- ブレイク成功度: are momentum entries paying now (two years)
- 地合いと本命の推移: QQQ over two years on the gate, the market pulse strip and the picks per day
- 本命の出方, 月別, 本命のセクター構成, 地合いの中身 (pulse, breadth, sector strength)

Inputs: the refresh stores QQQ, the gate and the breakout-health line in seed/post-cards-state.json; counts come from
seed/honmei-counts.json (local replay before the gate, gated here) and track-record/signals.json (live record); the
pulse and breadth from data/mc57.json; today's funnel from the swing screener card on the page.
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
SECTOR_MAP = "seed/sector-map.json"
DAYS = 504
CHART = 1260                     # the main chart: five years
HISTORY_QQQ, HISTORY_PULSE = "market-history/indices-10y.json", "market-history/mc57-10y.json"
GATE_MA = 200
WEAK, GOOD = 40.0, 55.0          # the site's own bands for the market pulse (弱い <40, 良好 >=55)
COL = {"ink": "#1B1D1C", "mut": "#727569", "line": "#D5D1C6", "acc": "#17685C", "acc2": "#2A9384", "pos": "#1E7A4D",
       "posbg": "#DBEBDF", "neg": "#B23A2E", "negbg": "#F1DED9", "warn": "#B07A16", "warnbg": "#F0E6CF", "neubg": "#E6E3DB"}
SANS = "-apple-system,'Helvetica Neue',Arial,'Hiragino Sans','Noto Sans JP',sans-serif"
MONO = "ui-monospace,'SF Mono',Menlo,monospace"
JA = {"Technology": "テクノロジー", "Financial Services": "金融", "Healthcare": "ヘルスケア", "Industrials": "資本財",
      "Consumer Cyclical": "一般消費財", "Real Estate": "不動産", "Energy": "エネルギー", "Basic Materials": "素材",
      "Consumer Defensive": "生活必需品", "Communication Services": "通信", "Utilities": "公益"}


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _md(day: str | None) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}" if day else ""


def _sg(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:+.{nd}f}".replace("-", "−")


def band_of(v: float | None) -> str | None:
    return None if v is None else "weak" if v < WEAK else "good" if v >= GOOD else "mixed"


# ---------------------------------------------------------------- refresh-side state
def build_state(q: pd.Series, root: Path, session: str, health: dict | None = None) -> dict:
    q = q[q.index <= pd.Timestamp(session)].dropna()
    gate = (q > q.rolling(GATE_MA, min_periods=GATE_MA).mean()).iloc[-DAYS:]
    q = q.iloc[-DAYS:]
    bh = [[str(d)[:10], None if v is None else round(float(v), 5)] for d, v, *_ in (health or {}).get("chart") or []]
    return {"session": session, "q_dates": [str(d.date()) for d in q.index], "q": [round(float(v), 2) for v in q],
            "gate": [bool(g) for g in gate], "bh": bh}


# ---------------------------------------------------------------- inputs on both paths
def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _history(root: Path, rel: str, key: str) -> pd.Series | None:
    h = _json(root / rel)
    vals, dates = (h.get("series") or {}).get(key), h.get("dates")
    if not vals or not dates or len(vals) != len(dates):
        return None
    return pd.Series(pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(), index=pd.to_datetime(dates)).dropna()


def five_years(st: dict, root: Path) -> tuple[list[str], list[float], list[bool]]:
    """QQQ and the gate over five years from the site's own index history, joined to the state for later sessions."""
    q = _history(root, HISTORY_QQQ, "QQQ")
    if q is None or len(q) < GATE_MA + 10:
        return st["q_dates"], st["q"], st["gate"]
    q = q[q.index <= pd.Timestamp(st["session"])]
    gate = (q > q.rolling(GATE_MA, min_periods=GATE_MA).mean())
    d = [str(x.date()) for x in q.index]
    qv, gv = [round(float(v), 2) for v in q], [bool(g) for g in gate]
    last = d[-1]
    for day, v, g in zip(st["q_dates"], st["q"], st["gate"]):
        if day > last:
            d.append(day), qv.append(v), gv.append(g)
    return d[-CHART:], qv[-CHART:], gv[-CHART:]


def series(st: dict, root: Path) -> dict:
    """Everything on five years of QQQ sessions: gate, pulse, breadth, picks (gated), picks by sector."""
    d, qv, gv = five_years(st, root)
    seed = _json(root / COUNTS)
    raw, raw_sec = seed.get("counts", {}), seed.get("sectors", {})
    live = (_json(root / "track-record" / "signals.json").get("sessions") or {})
    smap = (_json(root / SECTOR_MAP).get("sectors") or {})
    pulse = {}
    ph = _history(root, HISTORY_PULSE, "MC57")
    if ph is not None:
        pulse = {str(k.date()): (float(v), None, None) for k, v in ph.items()}
    for r in _json(root / "data" / "mc57.json").get("history") or []:
        m = r.get("metrics") or {}
        pulse[str(r.get("date"))[:10]] = (r.get("mc57"), m.get("close_gt_sma50"), m.get("close_gt_sma200"))
    gate, c, sec = [], [], []
    for day, g in zip(d, gv):
        if day in live:
            s = live[day]
            on = s.get("regime", "on" if g else "off") == "on"
            names = [x.get("t") if isinstance(x, dict) else x for x in (s.get("best") or [])]
            by: dict[str, int] = {}
            for n in names:
                k = smap.get(n, "?")
                by[k] = by.get(k, 0) + 1
            gate.append(on), c.append(len(names)), sec.append(by)
        elif day in raw:
            gate.append(g), c.append(raw[day] if g else 0), sec.append(raw_sec.get(day, {}) if g else {})
        else:
            gate.append(g), c.append(None), sec.append({})
    pv = [pulse.get(x, (None, None, None)) for x in d]
    bh = {a: b for a, b in st.get("bh") or []}
    return {"d": d, "q": qv, "gate": gate, "c": c, "sec": sec, "pulse": [p[0] for p in pv], "a50": [p[1] for p in pv],
            "a200": [p[2] for p in pv], "band": [band_of(p[0]) for p in pv], "bh": [bh.get(x) for x in d]}


def screener_today(page: str) -> dict:
    """Today's counts and gate line from the swing screener card (display text; no names)."""
    out: dict = {}
    i = page.find('id="mc57-swing-screener"')
    seg = page[i:i + 8000] if i >= 0 else ""
    m = re.search(r"流動性あり(\d+)銘柄から選定(\d+)銘柄", seg)
    if m:
        out["liquid"], out["selected"] = int(m.group(1)), int(m.group(2))
    for name, n in re.findall(r'<span class="[^"]*">([^<]+)<b>(\d+)</b></span>', seg[:3000]):
        out.setdefault("lists", {})[name] = int(n)
    m = re.search(r"QQQ \$([\d,.]+) が200日線 \$([\d,.]+)", seg)
    if m:
        qv, ma = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        out["to_gate"] = (ma / qv - 1) * 100
    m = re.search(r"ブレイク成功度 <b>([−\-+\d.]+)%</b>（([^）]+)）", seg)
    if m:
        out["bh_now"], out["bh_word"] = float(m.group(1).replace("−", "-")), m.group(2)
    j = page.find('id="mc57-breakout-health"')
    bseg = page[j:j + 20000] if j >= 0 else ""
    m = re.search(r"数えた本命<b>(\d+)件</b>", bseg)
    if m:
        out["bh_n"] = int(m.group(1))
    m = re.search(r"が続いて<b>(\d+)営業日</b>(\d+/\d+)から", bseg)
    if m:
        out["bh_days"], out["bh_since"] = int(m.group(1)), m.group(2)
    return out


def universe(page: str) -> dict:
    """対象 / 適格 / 監視上位 from the original market card's header."""
    m = re.search(r"対象 <b>(\d+)</b>銘柄 ・ 適格 <b>(\d+)</b> ・ 監視上位 <b>(\d+)</b>", html.unescape(page))
    return {"all": int(m.group(1)), "ok": int(m.group(2)), "top": int(m.group(3))} if m else {}


# ---------------------------------------------------------------- drawing helpers
def _main_chart(s: dict, w: int, h: int) -> str:
    """QQQ on the entry gate (top), the market pulse strip and the picks per day (bottom), one time axis."""
    q, d, n = s["q"], s["d"], len(s["q"])
    pl, pr = 44, 56
    top_h, strip_y, strip_h, bars_y, bar_h = 222, 234, 40, 284, 104
    step = (w - pl - pr) / max(n - 1, 1)
    X = lambda i: pl + step * i  # noqa: E731
    lo, hi = min(q) * 0.97, max(q) * 1.02
    Y = lambda v: 4 + (top_h - 4) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']

    def runs(vals):
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[j + 1] == vals[i]:
                j += 1
            yield i, j, vals[i]
            i = j + 1
    for i, j, g in runs(s["gate"]):
        x0, x1 = max(X(i) - step / 2, pl), min(X(j) + step / 2, w - pr)
        f = COL["posbg"] if g else COL["negbg"]
        for y0, hh in ((4, top_h - 4), (strip_y, strip_h), (bars_y, bar_h)):   # every panel on the same gate colours
            out.append(f'<rect x="{x0:.1f}" y="{y0}" width="{x1 - x0:.1f}" height="{hh}" fill="{f}"/>')
    # the market pulse as a line (0-100) with its two cut-offs, so its colour never competes with the gate
    PY = lambda v: strip_y + 2 + (strip_h - 4) * (1 - min(max(v, 0), 100) / 100)  # noqa: E731
    for cut in (WEAK, GOOD):
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{PY(cut):.1f}" y2="{PY(cut):.1f}" stroke="{COL["mut"]}" stroke-width=".8" stroke-dasharray="2 3"/>')
    seg, segs = [], []
    for i, v in enumerate(s["pulse"]):
        if v is None:
            if seg:
                segs.append(seg)
            seg = []
        else:
            seg.append(f"{X(i):.1f},{PY(v):.1f}")
    segs.append(seg)
    for sg in segs:
        if len(sg) > 1:
            out.append(f'<polyline points="{" ".join(sg)}" fill="none" stroke="{COL["acc"]}" stroke-width="1.3" stroke-linejoin="round"/>')
    for cut in (GOOD, WEAK):
        out.append(f'<text x="{pl - 5}" y="{PY(cut) + 3.5:.1f}" font-family="{MONO}" font-size="9.5" fill="{COL["mut"]}" text-anchor="end">{cut:.0f}</text>')
    for k in range(4):
        v = lo + (hi - lo) * (k + .5) / 4
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{COL["line"]}" stroke-dasharray="2 3"/>'
                   f'<text x="{pl - 5}" y="{Y(v) + 4:.1f}" font-family="{MONO}" font-size="10.5" fill="{COL["mut"]}" text-anchor="end">{v:.0f}</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(q))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{COL["ink"]}" stroke-width="1.8" stroke-linejoin="round"/>')
    x, y = X(n - 1), Y(q[-1])
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COL["ink"]}" stroke="#fff" stroke-width="2"/>'
               f'<text x="{x + 7:.1f}" y="{y + 4:.1f}" font-family="{MONO}" font-size="11.5" font-weight="800" fill="{COL["ink"]}">{q[-1]:.0f}</text>')
    lab = lambda x0, y0, t: f'<text x="{x0}" y="{y0}" font-family="{SANS}" font-size="11" font-weight="800" fill="{COL["ink"]}">{t}</text>'  # noqa: E731
    out.append(lab(pl + 6, 18, "QQQ"))
    pv = next((v for v in reversed(s["pulse"]) if v is not None), None)
    if pv is not None:
        out.append(f'<text x="{X(n - 1) + 7:.1f}" y="{PY(pv) + 4:.1f}" font-family="{MONO}" font-size="11" font-weight="800" fill="{COL["acc"]}">{pv:.0f}</text>')
    out.append(lab(pl + 6, strip_y + 12, "地合いスコア"))
    c = [v or 0 for v in s["c"]]
    cmax = max(max(c), 1)
    base = bars_y + bar_h
    for k in sorted({0, cmax}):
        yy = base - bar_h * k / cmax
        out.append(f'<text x="{pl - 5}" y="{yy + 4:.1f}" font-family="{MONO}" font-size="10.5" fill="{COL["mut"]}" text-anchor="end">{k}</text>')
    bw = max(step - .45, .8)
    for i, v in enumerate(c):
        if v:
            bh = bar_h * v / cmax
            out.append(f'<rect x="{X(i) - bw / 2:.2f}" y="{base - bh:.1f}" width="{bw:.2f}" height="{bh:.1f}" fill="{COL["acc"]}"/>')
    out.append(lab(pl + 6, bars_y + 14, "本命の数"))
    for i, day in enumerate(d):
        if i and day[:7] != d[i - 1][:7] and int(day[5:7]) in ((1, 7) if n > 600 else (1, 4, 7, 10)):
            t = f"{day[:4]}年" if day[5:7] == "01" else f"{int(day[5:7])}月"
            out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{base}" y2="{base + 4}" stroke="{COL["mut"]}"/>'
                       f'<text x="{X(i):.1f}" y="{h - 3}" font-family="{SANS}" font-size="10.5" fill="{COL["mut"]}" text-anchor="middle">{t}</text>')
    out.append("</svg>")
    return "".join(out)


def _line(vals: list, w: int, h: int, col: str, zero: bool = False, lo: float | None = None, hi: float | None = None) -> str:
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}"></svg>'
    vs = [v for _, v in pts]
    lo = min(vs) if lo is None else lo
    hi = max(vs) if hi is None else hi
    if zero:
        lo, hi = min(lo, -abs(hi) * .2), max(hi, abs(lo) * .2)
    pad = (hi - lo) * .08 or 1
    lo, hi = lo - pad, hi + pad
    n = len(vals)
    X = lambda i: 2 + (w - 4) * i / max(n - 1, 1)  # noqa: E731
    Y = lambda v: 2 + (h - 4) * (hi - v) / (hi - lo)  # noqa: E731
    out = f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
    if zero:
        z = Y(0)
        out += (f'<rect x="0" y="0" width="{w}" height="{z:.1f}" fill="{COL["posbg"]}" opacity=".7"/>'
                f'<rect x="0" y="{z:.1f}" width="{w}" height="{h - z:.1f}" fill="{COL["negbg"]}" opacity=".7"/>'
                f'<line x1="0" x2="{w}" y1="{z:.1f}" y2="{z:.1f}" stroke="{COL["mut"]}" stroke-dasharray="3 3"/>')
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    x, y = X(pts[-1][0]), Y(pts[-1][1])
    return out + (f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.8" stroke-linejoin="round"/>'
                  f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/></svg>')


CSS = """
*{box-sizing:border-box;margin:0;padding:0}html{-webkit-text-size-adjust:100%;height:100%}
body{background:#E9E7DF;font-family:-apple-system,'Helvetica Neue',Arial,'Hiragino Sans','Noto Sans JP',sans-serif;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#1B1D1C}
.stage{width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}.scaler{transform-origin:center center;flex:none}
.card{width:1680px;height:1080px;background:#E9E7DF;color:#1B1D1C;padding:20px 26px 12px;display:flex;flex-direction:column;
--ink:#1B1D1C;--mut:#727569;--line:#D5D1C6;--card:#F6F4EE;--accent:#17685C;--pos:#1E7A4D;--posbg:#DBEBDF;--neg:#B23A2E;--negbg:#F1DED9;
--warn:#B07A16;--warnbg:#F0E6CF;--neubg:#E6E3DB;--fnum:ui-monospace,'SF Mono',Menlo,monospace;font-size:13px}
.num{font-family:var(--fnum);font-variant-numeric:tabular-nums;letter-spacing:-.01em}.pos{color:var(--pos)}.neg{color:var(--neg)}.mut{color:var(--mut)}.wrn{color:var(--warn)}
.hd{display:flex;align-items:center;gap:12px;margin-bottom:8px}.hd .bar{width:5px;height:24px;background:var(--accent);border-radius:3px}
.hd h1{font-size:24px;font-weight:800;letter-spacing:-.02em}.hd h1 small{font-size:13px;font-weight:600;color:var(--mut);letter-spacing:.02em;margin-left:4px}
.hd .state{font-size:13px;font-weight:800;border:1.5px solid;border-radius:8px;padding:3px 12px}
.hd .stats{font-size:12.5px;color:var(--mut);font-weight:700}.hd .stats b{color:var(--ink);font-family:var(--fnum)}.hd .date{margin-left:auto;font-size:14px;color:var(--mut);font-weight:700}
.grid{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:212px 1fr 318px;gap:10px;flex:1;min-height:0}.sp2{grid-column:span 2}.sp3{grid-column:span 3}
.t{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px;min-height:0;overflow:hidden;display:flex;flex-direction:column}
.th{display:flex;align-items:baseline;gap:6px;margin-bottom:7px;white-space:nowrap}.th h4{font-size:13.5px;font-weight:800;letter-spacing:-.01em}
.th h4 .en{font-size:9px;font-weight:600;color:var(--mut);margin-left:5px;letter-spacing:.02em}.th .s{font-size:10.5px;color:var(--mut);font-weight:700;overflow:hidden;text-overflow:ellipsis}
.th .g{margin-left:auto;color:var(--mut);opacity:.5;font-size:11px}
.lg{display:flex;gap:9px;font-size:10.5px;color:var(--mut);font-weight:700;margin-left:auto}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:3px;vertical-align:-1px}
.big{display:flex;align-items:baseline;gap:6px}.big .v{font-size:34px;font-weight:800;line-height:1;letter-spacing:-.02em}.big .u{font-size:15px;font-weight:800;color:var(--mut)}
.big .tag{font-size:11.5px;font-weight:800;border:1.5px solid;border-radius:6px;padding:1px 7px;margin-left:4px}
.k{font-size:11.5px;color:var(--mut);font-weight:700}.k b{color:var(--ink);font-family:var(--fnum)}
.strip{display:grid;grid-template-columns:repeat(60,1fr);gap:2px;margin:10px 0 6px}.strip i{height:16px;border-radius:2px}
.foot2{margin-top:auto;padding-top:7px;border-top:1px solid var(--line);font-size:11.5px;font-weight:700;color:var(--mut)}.foot2 b{color:var(--ink);font-family:var(--fnum)}
.fun{display:flex;align-items:stretch;gap:0;margin:2px 0 8px}.fun div{flex:1;text-align:center;padding:8px 2px 7px;background:var(--neubg);position:relative;
clip-path:polygon(0 0,calc(100% - 12px) 0,100% 50%,calc(100% - 12px) 100%,0 100%,12px 50%)}.fun div:first-child{clip-path:polygon(0 0,calc(100% - 12px) 0,100% 50%,calc(100% - 12px) 100%,0 100%)}
.fun div b{display:block;font-family:var(--fnum);font-size:24px;font-weight:800;line-height:1.05}.fun div span{font-size:10.5px;font-weight:800;color:var(--mut)}
.fun div.z b{color:var(--mut)}.fun div.hit{background:var(--posbg)}.fun div.hit b{color:var(--pos)}
.lists{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}.lists div{background:#fff;border:1px solid var(--line);border-radius:7px;padding:5px 7px}
.lists div span{display:block;font-size:10.5px;font-weight:800;color:var(--mut)}.lists div b{font-family:var(--fnum);font-size:19px;font-weight:800}.lists div.on{border-color:var(--accent)}.lists div.on b{color:var(--accent)}
.kv{display:grid;grid-template-columns:1fr auto;gap:0 10px;font-size:12px;font-weight:700}.kv div{padding:5px 0;border-bottom:1px solid var(--line)}
.kv div:nth-child(even){text-align:right;font-family:var(--fnum);font-weight:800}.kv div:nth-last-child(-n+2){border-bottom:0}.kv small{color:var(--mut);font-weight:700;font-size:10.5px}
.bnd{display:grid;grid-template-columns:40px 1fr 40px;gap:6px;align-items:center;margin:5px 0;font-size:12px;font-weight:800}
.bnd .b{height:14px;border-radius:4px;background:var(--neubg);overflow:hidden}.bnd .b i{display:block;height:100%}.bnd .p{text-align:right;font-family:var(--fnum)}
table.mt{width:100%;border-collapse:collapse;font-size:11.5px}table.mt th{font-size:10.5px;color:var(--mut);font-weight:700;text-align:right;padding:3px 6px;border-bottom:1.5px solid var(--line);white-space:nowrap}
table.mt td{padding:1.5px 6px;text-align:right;border-bottom:1px solid var(--line);font-family:var(--fnum);font-weight:700;white-space:nowrap}
table.mt th:first-child,table.mt td:first-child{text-align:left}table.mt td.l{text-align:left;font-family:-apple-system,'Hiragino Sans',sans-serif}
table.mt td .hb{display:inline-block;height:9px;border-radius:2px;background:var(--accent);vertical-align:0;margin-right:5px}
table.mt td.c{padding:2px 4px}table.mt td.c span{display:block;border-radius:4px;padding:1px 0;text-align:center}
.sec{display:grid;grid-template-columns:76px 1fr 38px 26px;gap:6px;align-items:center;margin:2.2px 0;font-size:12px;font-weight:800}.sec .r{text-align:center;font-family:var(--fnum);font-size:11px;border-radius:4px;background:var(--neubg);color:var(--mut);padding:1px 0}.sec .r.h{background:var(--posbg);color:var(--pos)}.sec .r.l{background:var(--negbg);color:var(--neg)}
.sec .b{height:13px;border-radius:3px;background:var(--neubg);overflow:hidden}.sec .b i{display:block;height:100%;background:var(--accent)}
.sec .p{text-align:right;font-family:var(--fnum);font-size:11.5px}
.gauge{position:relative;height:10px;border-radius:5px;margin:7px 0 3px;background:linear-gradient(90deg,var(--negbg) 0 40%,var(--neubg) 40% 55%,var(--posbg) 55% 100%)}
.gauge i{position:absolute;top:-4px;width:4px;height:18px;border-radius:2px;background:var(--ink);transform:translateX(-2px)}
.chips{display:flex;flex-wrap:wrap;gap:4px}.chips span{font-size:11px;font-weight:800;padding:3px 7px;border-radius:6px;background:var(--neubg);color:var(--mut)}
.chips span.h{background:var(--posbg);color:var(--pos)}.chips span.l{background:var(--negbg);color:var(--neg)}
.foot{font-size:10.5px;color:var(--mut);font-weight:700;margin-top:6px;display:flex}.foot span{margin-left:auto;color:var(--accent);font-weight:800}
"""
FIT = ("<script>function fit(){var s=document.getElementById('scaler');var W=window.innerWidth,H=window.innerHeight,cw=1680,ch=1080;"
       "if(H>W){var sc=Math.min(W/ch,H/cw);s.style.transform='rotate(90deg) scale('+sc+')';}else{var sc=Math.min(W/cw,H/ch);"
       "s.style.transform='scale('+sc+')';}s.style.width=cw+'px';s.style.height=ch+'px';}fit();window.addEventListener('resize',fit);</script>")


def _streak(vals: list, pred) -> int:
    k = 0
    for v in reversed(vals):
        if not pred(v):
            break
        k += 1
    return k


def _longest(vals: list, pred) -> tuple[int, int]:
    best, cur, end = 0, 0, 0
    for i, v in enumerate(vals):
        cur = cur + 1 if pred(v) else 0
        if cur > best:
            best, end = cur, i
    return best, end


def stats(s: dict) -> dict:
    d, c, g = s["d"], s["c"], s["gate"]
    known = [(day, v, gg) for day, v, gg in zip(d, c, g) if v is not None]
    y1 = known[-252:]
    picked = [v for _, v, _ in y1 if v]
    on_days = [v for _, v, gg in y1 if gg]
    lz, end = _longest([v for _, v, _ in y1], lambda v: v == 0)
    mx = max(known, key=lambda x: x[1]) if known else (None, 0, None)
    out = {"share": round(len(picked) / max(len(y1), 1) * 100), "total": sum(picked), "per": (sum(picked) / len(picked)) if picked else 0,
           "max": mx[1], "max_day": mx[0], "longest": lz, "longest_end": y1[end][0] if y1 else None,
           "zero": _streak([v for _, v, _ in known], lambda v: v == 0), "on_share": round(len(on_days) / max(len(y1), 1) * 100),
           "hit_on": round(sum(1 for v in on_days if v) / max(len(on_days), 1) * 100),
           "gate_now": g[-1], "gate_days": _streak(g, lambda x: x == g[-1])}
    rows = []
    for k, name, col in (("good", "良好", COL["pos"]), ("mixed", "混在", "#8F8B7E"), ("weak", "弱い", COL["neg"])):
        days = [v for v, b in zip(c, s["band"]) if b == k and v is not None]
        rows.append((name, col, round(sum(1 for v in days if v) / len(days) * 100) if days else None))
    out["bands"] = rows
    return out


def monthly(s: dict, months: int = 12) -> list[dict]:
    df = pd.DataFrame({"d": pd.to_datetime(s["d"]), "q": s["q"], "c": s["c"], "g": s["gate"], "p": s["pulse"]})
    df["m"] = df.d.dt.strftime("%Y-%m")
    out = []
    prev = None
    for m, g in df.groupby("m"):
        known = g.c.dropna()
        secs: dict[str, int] = {}
        for i in g.index:
            for k, v in s["sec"][i].items():
                secs[k] = secs.get(k, 0) + v
        top = max(secs.items(), key=lambda x: x[1])[0] if secs else None
        ret = None if prev is None else (g.q.iloc[-1] / prev - 1) * 100
        prev = g.q.iloc[-1]
        p = g.p.dropna()
        out.append({"m": m, "n": len(g), "on": int(g.g.sum()), "days": int((known > 0).sum()), "total": int(known.sum()),
                    "top": top, "qqq": ret, "pulse": None if p.empty else float(p.mean()), "partial": len(known) < len(g)})
    return out[-months:]


def sectors_1y(s: dict) -> list[tuple[str, int]]:
    tot: dict[str, int] = {}
    for by in s["sec"][-252:]:
        for k, v in by.items():
            tot[k] = tot.get(k, 0) + v
    return sorted(((k, v) for k, v in tot.items() if k in JA), key=lambda x: -x[1])


def card_doc(st: dict, page: str, root: Path) -> tuple[str, str]:
    import phase_check as pc
    import sector_heat as sh
    s = series(st, root)
    sc = screener_today(page)
    un = universe(page)
    ph = pc.embedded_state(page) or {}
    heat = sh.embedded_state(page)
    a = stats(s)
    kind = pc.phase_of(ph) if ph else None
    pulse = next((v for v in reversed(s["pulse"]) if v is not None), None)
    band = band_of(pulse)
    bname = {"good": "良好", "mixed": "混在", "weak": "弱い"}.get(band, "—")
    on = a["gate_now"]
    today = s["c"][-1] or 0
    cap = []
    # ---- header
    stats_html = (f'本命 <b>{today}</b>件 ・ 過去1年で本命が出た日 <b>{a["share"]}%</b> ・ 地合いスコア <b>{pulse:.0f}</b>/100'
                  if pulse is not None else f'本命 <b>{today}</b>件')
    # ---- 新規の可否
    last60 = s["gate"][-60:]
    stops, run_ = [], 0
    for g in s["gate"] + [True]:
        if not g:
            run_ += 1
        elif run_:
            stops.append(run_)
            run_ = 0
    strip = "".join(f'<i style="background:{COL["pos"] if g else COL["neg"]};opacity:{.85 if g else .75}"></i>' for g in last60)
    gword = "新規OK" if on else "新規停止"
    gcol = "pos" if on else "neg"
    to_gate = sc.get("to_gate")
    gate_txt = (f'再開まで QQQ <b>{_sg(to_gate)}%</b>' if (not on and to_gate is not None and to_gate > 0)
                else f'停止まで QQQ <b>{_sg(-abs(to_gate))}%</b>' if (on and to_gate is not None) else "")
    t1 = (f'<div class="t"><div class="th"><h4>新規の可否<span class="en">Entry Gate</span></h4><span class="s">サイトの地合いルール</span><span class="g">⚙</span></div>'
          f'<div class="big"><span class="v {gcol}">{gword}</span><span class="tag {gcol}">{a["gate_days"]}日目</span></div>'
          f'<div class="strip">{strip}</div>'
          f'<div class="k">直近60日：新規OK <b>{sum(last60)}</b> / 停止 <b>{60 - sum(last60)}</b></div>'
          f'<div class="k" style="margin-top:5px">過去5年の停止 <b>{len(stops)}</b>回・平均 <b>{(sum(stops) / len(stops)) if stops else 0:.0f}</b>日・最長 <b>{max(stops) if stops else 0}</b>日</div>'
          f'<div class="foot2">{gate_txt}{" ・ " if gate_txt else ""}過去1年の新規OK <b>{a["on_share"]}%</b></div></div>')
    cap.append(f"新規の可否：{gword}（{a['gate_days']}日目）。" + (f"再開までQQQ {_sg(to_gate)}%。" if not on and to_gate else ""))
    # ---- 候補の流れ
    li = sc.get("lists", {})
    steps = []
    if un:
        steps += [("対象", un["all"]), ("適格", un["ok"])]
    if "liquid" in sc:
        steps += [("流動性あり", sc["liquid"]), ("選定", sc["selected"])]
    steps.append(("本命", li.get("本命", today)))
    fun = "".join(f'<div class="{"hit" if (k == "本命" and v) else "z" if not v else ""}"><b>{v:,}</b><span>{k}</span></div>' for k, v in steps)
    lst = "".join(f'<div class="{"on" if v else ""}"><span>{_e(k)}</span><b>{v}</b></div>' for k, v in li.items())
    t2 = (f'<div class="t sp2"><div class="th"><h4>候補の流れ<span class="en">Pick Funnel · Today</span></h4>'
          f'<span class="s">米国株全体から毎日しぼり込み（条件は非公開）</span><span class="g">⚙</span></div><div class="fun">{fun}</div>'
          f'<div class="lists">{lst}</div></div>')
    # ---- ブレイク成功度
    bh_now = sc.get("bh_now")
    bh_word = sc.get("bh_word", "")
    bcol = "pos" if bh_word == "好調" else "neg" if bh_word == "不調" else "mut"
    t3 = (f'<div class="t"><div class="th"><h4>ブレイク成功度<span class="en">Breakout Health</span></h4><span class="s">勢い株は報われているか</span></div>'
          f'<div class="big"><span class="v num {bcol}">{_sg(bh_now)}</span><span class="u">%</span><span class="tag {bcol}">{_e(bh_word or "—")}</span>'
          f'<span class="k" style="margin-left:auto">{sc.get("bh_days", "—")}営業日目</span></div>'
          f'{_line([None if v is None else v * 100 for v in s["bh"][-DAYS:]], 372, 76, COL["ink"], zero=True)}'
          f'<div class="foot2">候補の10日後の平均 ・ 直近63日 <b>{sc.get("bh_n", "—")}</b>件</div></div>')
    if bh_now is not None:
        cap.append(f"ブレイク成功度 {_sg(bh_now)}%（{bh_word}）。")
    # ---- main chart
    lg = (f'<span><i style="background:{COL["posbg"]}"></i>新規OK</span><span><i style="background:{COL["negbg"]}"></i>新規停止</span>'
          f'<span><i style="background:{COL["acc"]};height:3px;vertical-align:3px"></i>地合いスコア（点線＝40・55）</span>')
    t4 = (f'<div class="t sp3"><div class="th"><h4>地合いと本命の推移<span class="en">Gate · Market Pulse · Picks (5Y)</span></h4>'
          f'<span class="lg">{lg}</span></div>{_main_chart(s, 1204, 408)}</div>')
    # ---- 本命の出方
    bands = "".join(f'<div class="bnd"><span style="color:{col}">{n}</span><div class="b"><i style="width:{p or 0}%;background:{col}"></i></div>'
                    f'<span class="p">{"—" if p is None else f"{p}%"}</span></div>' for n, col, p in a["bands"])
    t5 = (f'<div class="t"><div class="th"><h4>本命の出方<span class="en">Pick Stats</span></h4><span class="s">過去1年</span></div><div class="kv">'
          f'<div>本命が出た日</div><div>{a["share"]}%</div>'
          f'<div>新規OKの日のうち出た日</div><div>{a["hit_on"]}%</div>'
          f'<div>延べ件数<small>（出た日の平均）</small></div><div>{a["total"]}件<small>（{a["per"]:.1f}）</small></div>'
          f'<div>1日の最多<small>（{_md(a["max_day"])}）</small></div><div>{a["max"]}件</div>'
          f'<div>最長の連続ゼロ<small>（〜{_md(a["longest_end"])}）</small></div><div>{a["longest"]}日</div>'
          f'<div>いまの連続ゼロ</div><div class="{"neg" if a["zero"] else ""}">{a["zero"]}日</div></div>'
          f'<div class="k" style="margin:9px 0 2px">市場内部別：本命が出た日（5年）</div>{bands}</div>')
    if a["zero"]:
        cap.append(f"本命は{a['zero']}日連続ゼロ。過去1年で本命が出たのは{a['share']}%の日だけ。")
    else:
        cap.append(f"本命は今日{today}件。過去1年で本命が出たのは{a['share']}%の日。")
    # ---- monthly
    rows = monthly(s)
    mx_total = max([r["total"] for r in rows] + [1])
    trs = ""
    for r in rows:
        pcol = {"good": COL["posbg"], "mixed": COL["neubg"], "weak": COL["negbg"]}.get(band_of(r["pulse"]), "transparent")
        qcol = "" if r["qqq"] is None else ("pos" if r["qqq"] >= 0 else "neg")
        trs += (f'<tr><td>{r["m"][:4]}/{r["m"][5:]}{"*" if r["m"] == rows[-1]["m"] else ""}</td><td>{r["on"]}/{r["n"]}</td><td>{r["days"]}</td>'
                f'<td class="l"><span class="hb" style="width:{70 * r["total"] / mx_total:.0f}px"></span>{r["total"]}</td>'
                f'<td class="l">{_e(JA.get(r["top"], "—"))}</td><td class="{qcol}">{_sg(r["qqq"])}%</td>'
                f'<td class="c"><span style="background:{pcol}">{"—" if r["pulse"] is None else round(r["pulse"])}</span></td></tr>')
    t6 = (f'<div class="t sp2"><div class="th"><h4>月別の本命<span class="en">Monthly</span></h4><span class="s">過去12か月・*は今月（途中）</span><span class="g">⚙</span></div>'
          f'<table class="mt"><tr><th>月</th><th>新規OK日</th><th>出た日</th><th>延べ件数</th><th>最多セクター</th><th>QQQ</th><th>パルス平均</th></tr>{trs}</table></div>')
    # ---- sectors of picks
    secs = sectors_1y(s)
    tot = sum(v for _, v in secs) or 1
    rank = {x["name"]: i + 1 for i, x in enumerate(heat["sectors"])} if heat else {}
    share = dict(secs)
    order = sorted(JA, key=lambda k: (-share.get(k, 0), rank.get(k, 99)))
    top = max(share.values()) if share else 1
    sb = "".join(f'<div class="sec"><span>{_e(JA[k])}</span><div class="b"><i style="width:{share.get(k, 0) / top * 100:.0f}%"></i></div>'
                 f'<span class="p">{share.get(k, 0) / tot * 100:.0f}%</span>'
                 f'<span class="r {"h" if rank.get(k, 99) <= 3 else "l" if rank.get(k, 0) >= 9 else ""}">{rank.get(k, "—")}</span></div>' for k in order)
    t7 = (f'<div class="t"><div class="th"><h4>本命のセクター構成<span class="en">Picks by Sector</span></h4><span class="s">過去1年{tot}件・右＝今の勢い順位</span></div>{sb}</div>')
    if secs:
        cap.append("過去1年の本命はセクター別に " + "・".join(f"{JA[k]}{v / tot * 100:.0f}%" for k, v in secs[:3]) + "。")
    # ---- market inside
    a50 = next((v for v in reversed(s["a50"]) if v is not None), None)
    a200 = next((v for v in reversed(s["a200"]) if v is not None), None)
    p5 = s["pulse"][-6] if len(s["pulse"]) > 6 else None
    chips = ""
    if heat:
        sl = heat["sectors"]
        chips = "".join(f'<span class="{"h" if i < 3 else "l" if i >= len(sl) - 3 else ""}">{_e(x["ja"])}</span>' for i, x in enumerate(sl))
    pcls = {"good": "pos", "mixed": "mut", "weak": "neg"}.get(band, "mut")
    phase = dict(pc.PHASES).get(kind, "—") if kind else "—"
    t8 = (f'<div class="t"><div class="th"><h4>地合いの中身<span class="en">Market Inside</span></h4></div>'
          f'<div class="big"><span class="v num {pcls}">{"—" if pulse is None else f"{pulse:.0f}"}</span><span class="u">/100</span>'
          f'<span class="tag {pcls}">内部{bname}</span><span class="k" style="margin-left:auto">5日 <b>{_sg(None if p5 is None or pulse is None else pulse - p5)}</b></span></div>'
          f'<div class="gauge"><i style="left:{min(max(pulse or 0, 0), 100):.0f}%"></i></div>'
          f'{_line(s["pulse"][-252:], 372, 40, COL["ink"], lo=0, hi=100)}'
          f'<div class="kv" style="margin-top:4px"><div>50日線より上<small>（主要銘柄）</small></div><div>{"—" if a50 is None else f"{a50:.0f}%"}</div>'
          f'<div>200日線より上</div><div>{"—" if a200 is None else f"{a200:.0f}%"}</div>'
          f'<div>QQQの局面</div><div style="font-family:inherit">{_e(phase)}</div></div>'
          f'<div class="k" style="margin:6px 0 4px">セクターの勢い（左ほど強い）</div><div class="chips">{chips}</div></div>')
    cap.append(f"市場内部は{bname}（地合いスコア{pulse:.0f}/100）。" if pulse is not None else "")
    st_col = "pos" if on else "neg"
    doc = (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"/><meta content="width=device-width,initial-scale=1" name="viewport"/>'
           f'<title>地合いと本命</title><style>{CSS}</style></head><body><div class="stage"><div class="scaler" id="scaler"><div class="card">'
           f'<div class="hd"><span class="bar"></span><h1>地合いと本命<small>Market &amp; Picks</small></h1>'
           f'<span class="state" style="color:var(--{st_col})">{gword}</span><span class="stats">{stats_html}</span>'
           f'<span class="date num">米国 {_e(st["session"])} 終値</span></div><div class="grid">'
           f'{t1}{t2}{t3}{t4}{t5}{t6}{t7}{t8}</div>'
           '<div class="foot">本命＝毎日しぼり込むスイング候補（銘柄・条件は非公開）。2026年10月より前は同じルールで再計算した値。売買の推奨ではありません。</div>'
           f'</div></div></div>{FIT}</body></html>')
    text = f"【米国株 地合いと本命 {_md(st['session'])}】\n" + "\n".join(x for x in cap if x) + "\n#米国株 #ナスダック"
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
    doc, text = scrub(doc), scrub(text)
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


# Words that point at the site or its system, removed from every share card (the card images go to SNS).
SCRUB = ((re.compile(r"補助リスク（MC57外）"), "補助リスク（スコア外）"), (re.compile(r"MC57\s*(\d+)"), r"地合いスコア \1"),
         (re.compile(r"MC57 Dashboard"), ""), (re.compile(r"主要57銘柄"), "主要銘柄"), (re.compile(r"MC57"), ""))
FRAME_RE = re.compile(r'(<iframe class="postframe" srcdoc=")([^"]*)(")')


def scrub(doc: str) -> str:
    for pat, rep in SCRUB:
        doc = pat.sub(rep, doc)
    return doc


def scrub_cards(text: str) -> str:
    """Remove the identifying words from the original share cards of the Publish tab (display only)."""
    m = re.search(r'<(?:div|section)\b[^>]*\bid="t-post1"[^>]*>', text)
    if not m:
        return text
    end = text.find("</section>", m.end())
    end = len(text) if end < 0 else end
    region = FRAME_RE.sub(lambda f: f.group(1) + html.escape(scrub(html.unescape(f.group(2))), quote=True) + f.group(3),
                          text[m.end():end])
    return text[:m.end()] + region + text[end:]


def apply(text: str, root: Path, state: dict | None = None) -> str:
    st = state or embedded_state(text)
    seed = _seed(root)
    if seed and (not st or seed.get("session", "") >= st.get("session", "")):
        st = seed
    text = scrub_cards(text)
    if not st or "gate" not in st:
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


def run(text: str, root: Path, session: str, health: dict | None = None) -> str:
    import decline_anatomy as da
    market = da.load_market(root)
    px = da._closes(market) if market else None
    if px is None or da.INDEX not in px:
        print("post cards: market inputs not usable; keeping the stored card", flush=True)
        return apply(text, root)
    st = build_state(px[da.INDEX], root, session, health)
    try:
        (root / SEED).write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as exc:
        print(f"post cards: seed not written: {exc!r}", flush=True)
    return apply(text, root, st)
