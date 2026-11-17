"""F1〜F3（レジーム警戒灯）の推移グラフ, inside the レジーム警戒灯 card. Display only.

The series are the card's own definitions (build_dashboard_4.compute_regime_history, same
constants), recomputed on the refresh's OHLCV panel (about two years, so roughly the last year
can be drawn after the 200-day and 189-day warm-up).  The computed state is embedded in the
block so the display-only workflow can re-render it.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

BLOCK_ID = "reg-history"
STATE_ID = "reg-history-state"
STYLE_ID = "reg-history-style"
STATE_SEED = "seed/reg-history-state.json"
SESSIONS = 252

# build_dashboard_4 constants (names kept)
DVOL_FLOOR = 10e6
LEADER_BREADTH_BASE_N = 24
LEADER_BREADTH_DROP_RANK = 36
LEADER_RS = 85
F1_COV_MIN = 0.70
LAMPS = (  # key, name, 注意, 警戒
    ("f1", "F1 リーダー脱落率", 0.20, 0.30),
    ("f2", "F2 勢い細り率", 0.25, 0.40),
    ("f3", "F3 キュー崩れ", 0.40, 0.60),
)


def panel(ohlcv_csv: Path, session: str | None = None) -> dict[str, pd.DataFrame]:
    df = pd.read_csv(ohlcv_csv)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df = df[df["date"].notna()]
    if session:
        df = df[df["date"] <= pd.Timestamp(session)]
    if "is_complete" in df.columns:
        df = df[df["is_complete"].map(lambda v: str(v).strip().lower() in ("true", "1", "1.0", "yes", "y"))]
    out = {}
    for raw, key in (("high", "High"), ("close", "Close"), ("volume", "Volume")):
        df[raw] = pd.to_numeric(df[raw], errors="coerce")
        out[key] = df.pivot_table(index="date", columns="ticker", values=raw, aggfunc="last").sort_index()
    return out


def series(W: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """F1/F2/F3 per session, as in compute_regime_history."""
    C, H, V = W["Close"], W["High"], W["Volume"]
    C = C.where(C > 0)
    ma50 = C.rolling(50, min_periods=45).mean()
    ma200 = C.rolling(200, min_periods=180).mean()
    dv = (C * V).rolling(20, min_periods=15).mean()
    split_bad = (C.pct_change(fill_method=None).abs() > 1.5).rolling(189).max().fillna(0).astype(bool)
    pool = (ma50 > ma200) & (C >= 5) & (dv >= DVOL_FLOOR) & ~split_bad
    r189 = C.pct_change(189, fill_method=None).where(pool)
    rk = r189.rank(axis=1, ascending=False)
    rs189p = r189.rank(axis=1, pct=True) * 100
    rs63 = C.pct_change(63, fill_method=None).where(pool).rank(axis=1, pct=True) * 100
    ret20 = C.pct_change(20, fill_method=None)
    d52 = C / H.rolling(252).max() - 1
    observable = C.notna() & ma200.notna() & ma50.notna() & dv.notna() & C.shift(189).notna() & ~split_bad
    was24 = rk.shift(20) <= LEADER_BREADTH_BASE_N
    dropped = (was24 & observable & pool & (rk > LEADER_BREADTH_DROP_RANK)) | (was24 & observable & ~pool)
    den_all = was24.sum(axis=1).replace(0, np.nan)
    den_obs = (was24 & observable).sum(axis=1).replace(0, np.nan)
    f1 = (dropped.sum(axis=1) / den_obs).where(den_obs / den_all >= F1_COV_MIN)
    top24 = rk <= LEADER_BREADTH_BASE_N
    obs63 = top24 & rs63.notna()
    f2 = ((rs63 < LEADER_RS) & obs63).sum(axis=1) / obs63.sum(axis=1).replace(0, np.nan)
    qual = (rs189p >= LEADER_RS) & (C > ma200) & pool
    f3 = (qual & ((ret20 <= 0) | (d52 < -0.15))).sum(axis=1) / qual.sum(axis=1).replace(0, np.nan)
    return pd.DataFrame({"f1": f1, "f2": f2, "f3": f3})


def build_state(W: dict[str, pd.DataFrame], market: dict | None = None, n: int = SESSIONS) -> dict | None:
    s = series(W).dropna(how="all")
    s = s[s.notna().sum(axis=1) == 3].tail(n)
    if len(s) < 20:
        return None
    out = {"session": str(s.index[-1].date()), "dates": [str(d.date()) for d in s.index]}
    for k in ("f1", "f2", "f3"):
        out[k] = [round(float(x), 3) for x in s[k]]
    rows = ((market or {}).get("series") or {}).get("QQQ") or []
    if rows:
        q = pd.Series({str(r.get("date"))[:10]: r.get("close") for r in rows if r.get("close") is not None}, dtype=float)
        out["qqq"] = [round(float(q[d]), 2) if d in q.index else None for d in out["dates"]]
    return out


# ---------------------------------------------------------------- rendering
W_, PH, PAD_L, PAD_R = 340, 78, 30, 30

STYLE = (
    f'<style id="{STYLE_ID}">'
    '.rgh{margin:12px 0 4px;padding-top:10px;border-top:1px dashed var(--ds-line,#dedbd2);position:relative}'
    '.rgh .rgh-h{font-size:13px;font-weight:800;color:var(--ds-ink,#1c1b19);margin-bottom:2px}'
    '.rgh .rgh-s{font-size:11.5px;color:var(--ds-muted,#6b685e);margin-bottom:6px;line-height:1.5}'
    '.rgh svg{display:block;width:100%;height:auto;touch-action:pan-y}'
    '.rgh .rgh-t{font-size:10px;fill:var(--ds-muted,#6b685e)}'
    '.rgh .rgh-k{font-size:11px;font-weight:700;fill:var(--ds-ink-2,#46443d)}'
    '.rgh .rgh-v{font-size:11px;font-weight:800;fill:var(--ds-ink,#1c1b19)}'
    '.rgh .rgh-line{fill:none;stroke:var(--ds-ink,#1c1b19);stroke-width:1.3;stroke-linejoin:round}'
    '.rgh .rgh-q{fill:none;stroke:var(--ds-muted,#6b685e);stroke-width:1.4}'
    '.rgh .rgh-warn{fill:var(--ds-warn,#8a5a12);opacity:.10}.rgh .rgh-bad{fill:var(--ds-down,#b3362c);opacity:.12}'
    '.rgh .rgh-th{stroke:var(--ds-line,#dedbd2);stroke-width:1;stroke-dasharray:3 3}'
    '.rgh .rgh-x{stroke:var(--ds-muted,#6b685e);stroke-width:1;opacity:0}'
    '.rgh .rgh-tip{position:absolute;pointer-events:none;display:none;background:var(--ds-surface,#fff);'
    'border:1px solid var(--ds-line,#dedbd2);border-radius:6px;padding:5px 7px;font-size:11.5px;line-height:1.5;'
    'color:var(--ds-ink,#1c1b19);box-shadow:0 2px 6px rgba(0,0,0,.12);white-space:nowrap;z-index:3}'
    '.rgh .rgh-end{display:none}'
    '</style>'
)


def _pts(vals, lo, hi, top):
    n = len(vals)
    xs = [PAD_L + (W_ - PAD_L - PAD_R) * i / max(n - 1, 1) for i in range(n)]
    out, seg = [], []
    for x, v in zip(xs, vals):
        if v is None:
            if seg:
                out.append(seg)
            seg = []
            continue
        y = top + PH - (min(max(v, lo), hi) - lo) / (hi - lo) * PH
        seg.append(f"{x:.1f},{y:.1f}")
    if seg:
        out.append(seg)
    return out


def _hi(state: dict) -> float:
    """Shared top of the three panels: 70% or the next 10% above the highest value."""
    top_v = max([v for k, *_ in LAMPS for v in state[k] if v is not None] + [0.6])
    return float(min(1.0, np.ceil(top_v * 10 + 0.5) / 10))


def chart_svg(state: dict) -> str:
    dates = state["dates"]
    n = len(dates)
    gap = 18
    panels = [(k, name, w, b) for k, name, w, b in LAMPS] + ([("qqq", "QQQ（参考）", None, None)] if state.get("qqq") else [])
    height = len(panels) * (PH + gap) + 16
    parts = [f'<svg viewBox="0 0 {W_} {height}" role="img" aria-label="F1〜F3の推移">']
    x0, x1 = PAD_L, W_ - PAD_R
    for j, (k, name, warn, bad) in enumerate(panels):
        top = j * (PH + gap) + 14
        vals = state[k]
        parts.append(f'<text class="rgh-k" x="{x0}" y="{top - 4}">{html.escape(name)}</text>')
        if k == "qqq":
            q = [v for v in vals if v is not None]
            lo, hi = min(q) * 0.98, max(q) * 1.02
            last = q[-1]
            parts.append(f'<text class="rgh-v" x="{x1 + 2}" y="{top + 10}">{last:.0f}</text>')
            parts.append(f'<line class="rgh-th" x1="{x0}" x2="{x1}" y1="{top + PH}" y2="{top + PH}"/>')
            for seg in _pts(vals, lo, hi, top):
                parts.append(f'<polyline class="rgh-q" points="{" ".join(seg)}"/>')
            continue
        lo, hi = 0.0, _hi(state)

        def y_of(v, top=top, hi=hi):
            return top + PH - (min(v, hi) - lo) / (hi - lo) * PH
        yb, yw = y_of(bad), y_of(warn)
        parts.append(f'<rect class="rgh-bad" x="{x0}" y="{top}" width="{x1 - x0}" height="{yb - top:.1f}"/>')
        parts.append(f'<rect class="rgh-warn" x="{x0}" y="{yb:.1f}" width="{x1 - x0}" height="{yw - yb:.1f}"/>')
        for lv, y, dy in ((warn, yw, 9), (bad, yb, -1)):   # 注意 below its line, 警戒 above
            parts.append(f'<line class="rgh-th" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>')
            parts.append(f'<text class="rgh-t" x="{x0 - 3}" y="{y + dy:.1f}" text-anchor="end">{lv * 100:.0f}%</text>')
        parts.append(f'<line class="rgh-th" x1="{x0}" x2="{x1}" y1="{top + PH}" y2="{top + PH}"/>')
        for seg in _pts(vals, lo, hi, top):
            parts.append(f'<polyline class="rgh-line" points="{" ".join(seg)}"/>')
        last = vals[-1]
        lab = "警戒" if last >= bad else "注意" if last >= warn else ""
        ly = min(max(y_of(last) + 4, top + 9), top + PH - 8)
        parts.append(f'<text class="rgh-v" x="{x1 + 2}" y="{ly:.1f}">{last * 100:.0f}%</text>')
        if lab:
            parts.append(f'<text class="rgh-t" x="{x1 + 2}" y="{ly + 11:.1f}">{lab}</text>')
    # month ticks
    yb = len(panels) * (PH + gap) + 6
    seen = None
    for i, d in enumerate(dates):
        m = d[:7]
        if m != seen and i > 0 and int(d[5:7]) % 2 == 1:
            x = x0 + (x1 - x0) * i / max(n - 1, 1)
            parts.append(f'<text class="rgh-t" x="{x:.1f}" y="{yb}" text-anchor="middle">{int(d[5:7])}月</text>')
        seen = m
    parts.append(f'<line class="rgh-x" x1="0" x2="0" y1="10" y2="{yb - 8}"/>')
    parts.append(f'<rect x="{x0}" y="0" width="{x1 - x0}" height="{height}" fill="transparent" class="rgh-hit"/>')
    parts.append("</svg>")
    return "".join(parts)


SCRIPT = (
    "<script>(function(){var b=document.getElementById('reg-history');if(!b)return;"
    "var s=JSON.parse(document.getElementById('reg-history-state').textContent);"
    "var svg=b.querySelector('svg'),ln=b.querySelector('.rgh-x'),tip=b.querySelector('.rgh-tip');"
    "var n=s.dates.length,x0=30,x1=310,W=340;"
    "function pc(v){return v==null?'—':Math.round(v*100)+'%';}"
    "function show(ev){var r=svg.getBoundingClientRect(),p=(ev.touches?ev.touches[0]:ev);"
    "var x=(p.clientX-r.left)/r.width*W;var i=Math.round((x-x0)/(x1-x0)*(n-1));if(i<0)i=0;if(i>n-1)i=n-1;"
    "var gx=x0+(x1-x0)*i/(n-1);ln.setAttribute('x1',gx);ln.setAttribute('x2',gx);ln.style.opacity=1;"
    "var q=s.qqq?s.qqq[i]:null;tip.innerHTML='<b>'+s.dates[i]+'</b><br>F1 '+pc(s.f1[i])+'・F2 '+pc(s.f2[i])+'・F3 '+pc(s.f3[i])"
    "+(q!=null?'<br>QQQ '+q.toFixed(0):'');tip.style.display='block';"
    "var bx=b.getBoundingClientRect(),left=p.clientX-bx.left+10;if(left>bx.width-150)left=p.clientX-bx.left-160;"
    "tip.style.left=Math.max(0,left)+'px';tip.style.top=(p.clientY-bx.top-50)+'px';}"
    "function hide(){tip.style.display='none';ln.style.opacity=0;}"
    "svg.addEventListener('mousemove',show);svg.addEventListener('touchstart',show,{passive:true});"
    "svg.addEventListener('touchmove',show,{passive:true});svg.addEventListener('mouseleave',hide);"
    "svg.addEventListener('touchend',function(){setTimeout(hide,1500);});})();</script>"
)


def block_html(state: dict) -> str:
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    first, last = state["dates"][0], state["dates"][-1]
    return (f'<div class="rgh" id="{BLOCK_ID}"><div class="rgh-h">F1〜F3の推移</div>'
            f'<div class="rgh-s">{first}〜{last}（約1年）。薄い黄＝注意、薄い赤＝警戒の水準。'
            f'縦軸は3つとも0〜{_hi(state) * 100:.0f}%。下段はQQQ（参考）。タップで日付と値。</div>'
            f'{chart_svg(state)}<div class="rgh-tip"></div>'
            f'<script id="{STATE_ID}" type="application/json">{raw}</script>{SCRIPT}<span class="rgh-end"></span></div>')


BLOCK_RE = re.compile(rf'<div class="rgh" id="{BLOCK_ID}">.*?<span class="rgh-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def _insert_at(text: str) -> int | None:
    """Just after the lamps grid of the レジーム警戒灯 card (before its notes)."""
    h = text.find('<div class="card reg-card')
    if h < 0:
        return None
    note = text.find('<div class="note">', h)
    nxt = text.find('<div class="card', h + 10)
    if note < 0 or (0 < nxt < note):
        return None
    return note


def apply(text: str, state: dict | None) -> str:
    if not state:
        return text
    block = block_html(state)
    if BLOCK_RE.search(text):
        out = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        at = _insert_at(text)
        if at is None:
            print("regime history: card not found; block not inserted", flush=True)
            return text
        out = text[:at] + block + text[at:]
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


def run(text: str, root: Path, ohlcv_csv: Path, session: str) -> str:
    import decline_anatomy
    try:
        state = build_state(panel(ohlcv_csv, session), decline_anatomy.load_market(root))
    except (OSError, ValueError, KeyError) as exc:
        print(f"regime history: inputs not usable ({exc!r}); keeping the page as is", flush=True)
        return rerender(text, root)
    if state is None or state["session"] != session:
        print(f"regime history: series ends {state and state['session']} not {session}; keeping the page", flush=True)
        return rerender(text, root)
    print(f"regime history: {len(state['dates'])} sessions, last F1 {state['f1'][-1]} F2 {state['f2'][-1]} F3 {state['f3'][-1]}", flush=True)
    return apply(text, state)
