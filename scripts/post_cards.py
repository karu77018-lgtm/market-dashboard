"""SNS用の画像カード (Publish tab, display only).

Two 1600x900 cards drawn as SVG from the states the Daily-tab cards store in the page:
- 「いまの局面」: 局面チェック (phase, chance of a real bottom, the S&P 500 -10% check, QQQ's key levels)
- 「今回の下げの中身」: 今回の下げの分解 (type, similar past declines) + the lamps (F1-F3) + the FTD check
Each card has a button that turns it into a PNG on the phone (long-press to save, or share), and a draft post
text with a copy button.  Fonts are the device's (Hiragino on iPhone), so nothing is downloaded.
"""
from __future__ import annotations

import html
import json
import re

W, H = 1600, 900
BLOCK_ID = "post-cards"
STYLE_ID = "post-cards-style"
C = {"bg": "#E9E7DF", "card": "#F6F4EE", "ink": "#1B1D1C", "mut": "#727569", "line": "#D5D1C6", "acc": "#17685C",
     "pos": "#1E7A4D", "neg": "#B23A2E", "warn": "#B07A16", "warnbg": "#F0E6CF", "negbg": "#F1DED9", "posbg": "#DBEBDF"}
FONT = "'Hiragino Sans','Hiragino Kaku Gothic ProN','Noto Sans JP','Yu Gothic',sans-serif"
NUM = "'SF Pro Display','Helvetica Neue',Arial,sans-serif"
NOTE = "1990〜2026年の指数データでの過去検証に基づく参考値です。売買の推奨ではありません。"


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _md(day: str | None) -> str:
    if not day:
        return ""
    y, m, d = day[:10].split("-")
    return f"{int(m)}/{int(d)}"


def _ym(day: str) -> str:
    return f"{day[:4]}年{int(day[5:7])}月"


def _sg(v: float, nd: int = 1) -> str:
    return f"{v:+.{nd}f}".replace("-", "−")


def _t(x, y, s, size=28, color="ink", weight=400, anchor="start", family=FONT) -> str:
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{C.get(color, color)}" text-anchor="{anchor}">{_e(s)}</text>')


def _rect(x, y, w, h, fill="card", r=18, stroke=None) -> str:
    st = f' stroke="{C.get(stroke, stroke)}" stroke-width="2"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{C.get(fill, fill)}"{st}/>'


def _frame(title: str, session: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            + _rect(0, 0, W, H, "bg", 0)
            + f'<rect x="60" y="44" width="9" height="46" rx="4" fill="{C["acc"]}"/>'
            + _t(88, 84, title, 46, weight=800)
            + _t(W - 60, 82, f"米国 {session} 終値", 26, "mut", 700, "end")
            + body
            + f'<line x1="60" y1="{H - 62}" x2="{W - 60}" y2="{H - 62}" stroke="{C["line"]}" stroke-width="2"/>'
            + _t(60, H - 26, NOTE, 21, "mut")
            + _t(W - 60, H - 26, "MC57 Dashboard", 21, "acc", 800, "end")
            + "</svg>")


def _word(p: int) -> tuple[str, str]:
    return ("かなり期待できる", "pos") if p >= 80 else ("五分五分", "warn") if p >= 40 else ("一時的な戻りで終わりやすい", "neg")


# ---------------------------------------------------------------- card 1: いまの局面
def phase_card(ph: dict) -> tuple[str, str] | None:
    import phase_check as pc
    q, s = ph["qqq"], ph.get("spy") or {}
    kind = pc.phase_of(ph)
    steps = [(k, t) for k, t in pc.PHASES]
    sw = (W - 120 - 4 * 14) / 5
    body = ""
    for i, (k, t) in enumerate(steps):
        x = 60 + i * (sw + 14)
        on = k == kind
        body += _rect(x, 118, sw, 66, "ink" if on else "card", 14)
        body += _t(x + sw / 2, 162, t, 30, "#FFFFFF" if on else "mut", 800, "middle")
    # left: the main number
    body += _rect(60, 214, 940, 400, "card")
    cap = []
    if kind in ("up5", "up10"):
        r = q[kind]
        n, ok, basis = pc.rate_of(r, kind)
        p = pc._pct(n, ok)
        word, col = _word(p)
        rise = "+5%" if kind == "up5" else "+10%"
        body += _t(100, 278, f"QQQのこの戻りが本物の底になる率", 32, "mut", 700)
        body += _t(100, 486, f"{p}", 210, col, 800, family=NUM)
        body += _t(100 + 125 * len(str(p)) + 20, 486, "%", 90, col, 800, family=NUM)
        body += _t(560, 420, word, 46, col, 800)
        body += _t(100, 548, f"{_md(r['date'])}に安値から{rise}戻した日の判定（{basis}）", 27, "ink", 700)
        body += _t(100, 588, f"過去に同じ条件だった{n}回のうち{ok}回が本物の底", 25, "mut")
        cap += [f"QQQは{_md(q['low'])}の安値から{rise}戻した「{dict(pc.PHASES)[kind]}」。",
                f"この戻りが本物の底になる率は過去検証で{p}%（{basis}、{n}回中{ok}回）。"]
    elif kind == "down":
        body += _t(100, 278, "QQQは10%以上の下げの途中", 32, "mut", 700)
        body += _t(100, 486, _sg(q["dd"]), 190, "neg", 800, family=NUM)
        body += _t(100, 548, f"高値から（{_md(q['low'])}の安値から{_sg(q['from_low'])}%）", 27, "ink", 700)
        body += _t(100, 588, f"安値から+5%（{q['low_close'] * 1.05:.2f}）で引けた日に本物の底らしさを判定", 25, "mut")
        cap += [f"QQQは高値から{_sg(q['dd'])}%の下げの途中。安値から+5%戻した日に底らしさを判定します。"]
    else:
        body += _t(100, 278, "QQQ", 32, "mut", 700)
        body += _t(100, 486, _sg(q["dd"]), 190, "ink", 800, family=NUM)
        body += _t(100, 548, "高値から。10%以上の下げの途中ではない", 27, "ink", 700)
        cap += [f"QQQは高値から{_sg(q['dd'])}%。特別な局面ではありません。"]
    # right: S&P 500 start of a decline
    body += _rect(1030, 214, 510, 400, "card")
    ev = s.get("event") or {}
    if ev.get("status") == "open":
        k = "hi" if ev.get("vix") is not None and ev["vix"] >= pc.VIX_CUT else "lo"
        n, hit = pc.REF_DOWN[k][:2]
        p = pc._pct(n, hit)
        col = "neg" if p >= 40 else "warn" if p >= 20 else "pos"
        body += _t(1070, 278, "S&P500が−10%まで下げる率", 30, "mut", 700)
        body += _t(1070, 450, f"{p}", 170, col, 800, family=NUM)
        body += _t(1070 + 100 * len(str(p)) + 16, 450, "%", 72, col, 800, family=NUM)
        body += _t(1070, 520, f"{_md(ev['date'])}に高値から−5%（今{_sg(s['dd'])}%）", 26, "ink", 700)
        body += _t(1070, 558, f"その日のVIX {ev.get('vix')}（{pc.VIX_CUT:.0f}{'以上' if k == 'hi' else '未満'}）", 23, "mut")
        body += _t(1070, 592, f"同じ条件の過去{n}回のうち{hit}回", 23, "mut")
        cap += [f"S&P500は{_md(ev['date'])}に−5%入り。その日のVIXが{ev.get('vix')}で、−10%まで行く率は{p}%。"]
    else:
        body += _t(1070, 278, "S&P500", 30, "mut", 700)
        body += _t(1070, 450, _sg(s.get("dd", 0)), 150, "ink", 800, family=NUM)
        body += _t(1070, 528, "高値から。下げの初動の判定なし", 26, "ink", 700)
    # bottom: QQQ levels
    if kind in ("up5", "up10") and q.get("high") and q.get("close"):
        lo, top, now = q["low_close"], q["high"] * 0.98, q["close"]
        nxt = lo * 1.10 if kind == "up5" else None
        x0, x1, y = 130, W - 130, 762
        X = lambda v: x0 + (x1 - x0) * (min(max(v, lo), top) - lo) / (top - lo)  # noqa: E731
        body += _t(60, 664, "ここを見る（QQQ）", 28, "ink", 800)
        body += f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{C["line"]}" stroke-width="10" stroke-linecap="round"/>'
        body += f'<circle cx="{x0}" cy="{y}" r="11" fill="{C["neg"]}"/><circle cx="{x1}" cy="{y}" r="11" fill="{C["pos"]}"/>'
        body += _t(x0 - 20, y + 48, f"失敗 {lo:.2f}", 25, "neg", 700, "start")
        body += _t(x1 + 20, y + 48, f"本物の底 {top:.2f}", 25, "pos", 700, "end")
        if nxt and lo < nxt < top:
            body += f'<line x1="{X(nxt):.1f}" y1="{y - 18}" x2="{X(nxt):.1f}" y2="{y + 18}" stroke="{C["mut"]}" stroke-width="4"/>'
            body += _t(X(nxt), y + 48, f"再判定 {nxt:.2f}", 25, "mut", 700, "middle")
        body += f'<path d="M{X(now):.1f},{y - 16} l-14,-24 h28 z" fill="{C["ink"]}"/>'
        body += _t(X(now), y - 48, f"今 {now:.2f}", 27, "ink", 800, "middle")
        cap += [f"安値{lo:.2f}を終値で割ると失敗、{top:.2f}まで戻れば本物の底。"]
    svg = _frame("米国株 いまの局面", ph["session"], body)
    text = f"【米国株 いまの局面 {_md(ph['session'])}】\n" + "\n".join(cap) + "\n※過去検証に基づく参考値です。\n#米国株 #ナスダック"
    return svg, text


# ---------------------------------------------------------------- card 2: 今回の下げの中身
def anatomy_card(dec: dict, reg: dict | None, ftd: dict | None) -> tuple[str, str] | None:
    import regime_history as rh
    body, cap = "", []
    if dec.get("active") and dec.get("type"):
        body += _rect(60, 118, W - 120, 150, "card")
        body += _t(100, 170, "下げのタイプ", 28, "mut", 700)
        body += _t(100, 240, dec["type"], 56, "ink", 800)
        body += _t(W - 100, 170, "高値から", 28, "mut", 700, "end")
        body += _t(W - 100, 240, f"{_sg(dec['dd_now'])}%", 64, "neg", 800, "end", NUM)
        cap += [f"今回の下げは「{dec['type']}」、高値から{_sg(dec['dd_now'])}%（{dec.get('days_now')}日目）。"]
        # analogs
        body += _rect(60, 292, 780, 470, "card")
        body += _t(100, 346, "タイプと要因が近い過去の下げ", 30, "ink", 800)
        body += _t(100, 392, "高値の時期", 22, "mut")
        body += _t(640, 392, "さらに下げた幅", 22, "mut", 400, "end")
        body += _t(800, 392, "60日後", 22, "mut", 400, "end")
        for i, a in enumerate((dec.get("analogs") or [])[:3]):
            y = 462 + i * 100
            body += _t(100, y, _ym(a["peak"]), 36, "ink", 800)
            body += _t(100, y + 32, a.get("type", "").split("・")[0].replace("（資金移動）", ""), 21, "mut", 700)
            body += _t(640, y, f"{_sg(a['more'])}%", 36, "neg", 800, "end", NUM)
            body += _t(800, y, f"{_sg(a['r60'])}%", 36, "pos" if a["r60"] >= 0 else "neg", 800, "end", NUM)
            if i < 2:
                body += f'<line x1="100" y1="{y + 52}" x2="800" y2="{y + 52}" stroke="{C["line"]}" stroke-width="2"/>'
        if dec.get("analogs"):
            cap += ["似ている過去の下げ：" + "・".join(_ym(a["peak"]) for a in dec["analogs"][:3]) + "。"]
    else:
        body += _rect(60, 118, W - 120, 150, "card")
        body += _t(100, 170, "相場", 28, "mut", 700)
        body += _t(100, 240, "10%以上の下げの途中ではありません", 48, "ink", 800)
    # lamps
    body += _rect(870, 292, 670, 470, "card")
    body += _t(910, 346, "先導株の警戒灯", 30, "ink", 800)
    if reg:
        _, head, _ = rh.reading(reg)
        body += _t(910, 384, f"今の読み方：{head}", 22, "mut", 700)
        for i, (k, name, warn, bad) in enumerate(rh.LAMPS):
            v = reg[k][-1]
            y = 452 + i * 100
            x0, x1 = 1110, 1390
            body += _t(910, y + 10, name.split(" ")[0], 32, "ink", 800)
            body += _t(910, y + 42, name.split(" ")[1], 20, "mut", 700)
            body += _rect(x0, y - 14, x1 - x0, 30, "line", 8)
            body += f'<rect x="{x0 + (x1 - x0) * warn:.1f}" y="{y - 14}" width="{(x1 - x0) * (bad - warn):.1f}" height="30" fill="{C["warnbg"]}"/>'
            body += f'<rect x="{x0 + (x1 - x0) * bad:.1f}" y="{y - 14}" width="{(x1 - x0) * (1 - bad):.1f}" height="30" rx="8" fill="{C["negbg"]}"/>'
            col = "neg" if v >= bad else "warn" if v >= warn else "pos"
            body += f'<rect x="{x0}" y="{y - 6}" width="{(x1 - x0) * min(v, 1):.1f}" height="14" rx="7" fill="{C[col]}"/>'
            body += _t(1500, y + 12, f"{v * 100:.0f}%", 34, col, 800, "end", NUM)
        cap += [f"先導株の警戒灯 F1 {reg['f1'][-1] * 100:.0f}%・F2 {reg['f2'][-1] * 100:.0f}%・F3 {reg['f3'][-1] * 100:.0f}%（{head}）。"]
    # FTD
    ft = []
    for row in (ftd or {}).get("rows", []):
        r = row.get("ftd")
        if r is None:
            ft.append(f"{row['label']} FTDなし")
        elif r.get("broken"):
            ft.append(f"{row['label']} {_md(r['date'])}のFTDは騙し（{_md(r['broken']['date'])}に安値割れ）")
        else:
            ft.append(f"{row['label']} {_md(r['date'])}にFTD（Day{r['day']}）")
    if ft:
        body += _t(60, 808, "FTD：" + "／".join(ft), 25, "ink", 700)
        cap += ["FTD：" + "／".join(ft) + "。"]
    svg = _frame("今回の下げの中身", dec.get("session") or (reg or {}).get("session", ""), body)
    text = f"【米国株 今回の下げの中身 {_md(dec.get('session'))}】\n" + "\n".join(cap) + "\n※過去検証に基づく参考値です。\n#米国株"
    return svg, text


# ---------------------------------------------------------------- page block
SCRIPT = (
    "<script>(function(){function png(it,cb){if(it._png)return cb(it._png);var svg=it.querySelector('svg');"
    "var s=new XMLSerializer().serializeToString(svg);var img=new Image();img.onload=function(){var c=document.createElement('canvas');"
    "c.width=1600;c.height=900;c.getContext('2d').drawImage(img,0,0,1600,900);c.toBlob(function(b){it._png=b;cb(b);},'image/png');};"
    "img.onerror=function(){alert('画像にできませんでした');};"
    "img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(s);}"
    "document.querySelectorAll('#post-cards .pq-item').forEach(function(it){var name=it.dataset.name+'.png';"
    "it.querySelector('.pq-make').addEventListener('click',function(){png(it,function(b){var u=URL.createObjectURL(b);"
    "var box=it.querySelector('.pq-img');box.innerHTML='<img alt=\"\" src=\"'+u+'\"><div class=\"pq-hint\">画像を長押しで「写真に保存」。</div>';"
    "it.querySelector('.pq-share').style.display='';});});"
    "it.querySelector('.pq-share').addEventListener('click',function(){png(it,function(b){var f=new File([b],name,{type:'image/png'});"
    "if(navigator.canShare&&navigator.canShare({files:[f]})){navigator.share({files:[f]}).catch(function(){});}"
    "else{var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();}});});"
    "it.querySelector('.pq-copy').addEventListener('click',function(){var t=it.querySelector('textarea');"
    "(navigator.clipboard?navigator.clipboard.writeText(t.value):Promise.reject()).then(function(){},function(){t.select();document.execCommand('copy');});"
    "this.textContent='コピーしました';var me=this;setTimeout(function(){me.textContent='投稿文をコピー';},1500);});});})();</script>"
)
STYLE = (
    f'<style id="{STYLE_ID}">'
    '#post-cards .pq-item{margin:0 0 18px}'
    '#post-cards .pq-prev svg,#post-cards .pq-img img{display:block;width:100%;height:auto;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.12)}'
    '#post-cards .pq-btns{display:flex;gap:6px;margin:8px 0}'
    '#post-cards .pq-btns button{flex:1;font-size:13px;font-weight:700;padding:9px 4px;border-radius:8px;border:1px solid var(--ds-line,#dedbd2);'
    'background:var(--ds-surface,#fff);color:var(--ds-ink,#1c1b19)}'
    '#post-cards .pq-btns .pq-make{background:var(--ds-ink,#1c1b19);color:var(--ds-surface,#fff);border-color:var(--ds-ink,#1c1b19)}'
    '#post-cards textarea{width:100%;min-height:150px;font-size:13px;line-height:1.55;padding:8px;border-radius:8px;'
    'border:1px solid var(--ds-line,#dedbd2);background:var(--ds-surface,#fff);color:var(--ds-ink,#1c1b19)}'
    '#post-cards .pq-hint{font-size:12px;color:var(--ds-muted,#6b685e);margin-top:4px}'
    '#post-cards .pq-end{display:none}'
    '</style>'
)
BLOCK_RE = re.compile(rf'<div class="pq-wrap" id="{BLOCK_ID}">.*?<span class="pq-end"></span></div>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def cards(text: str) -> list[tuple[str, str, str, str]]:
    """(name, title, svg, post text) for each card the page has data for."""
    import phase_check as pc
    import decline_anatomy as da
    import regime_history as rh
    import ftd_check as fc
    out = []
    ph = pc.embedded_state(text)
    if ph:
        r = phase_card(ph)
        if r:
            out.append((f"phase-{ph['session']}", "いまの局面", *r))
    dec = da.embedded_state(text)
    if dec:
        r = anatomy_card(dec, rh.embedded_state(text), fc.embedded_state(text))
        if r:
            out.append((f"anatomy-{dec.get('session')}", "今回の下げの中身", *r))
    return out


def block_html(items: list[tuple[str, str, str, str]]) -> str:
    parts = []
    for name, title, svg, text in items:
        parts.append(f'<div class="pq-item" data-name="{_e(name)}"><div class="msec-q">{_e(title)}</div>'
                     f'<div class="pq-prev pq-img">{svg}</div>'
                     '<div class="pq-btns"><button class="pq-make" type="button">画像にする</button>'
                     '<button class="pq-share" style="display:none" type="button">共有・保存</button>'
                     '<button class="pq-copy" type="button">投稿文をコピー</button></div>'
                     f'<textarea readonly>{_e(text)}</textarea></div>')
    return (f'<div class="pq-wrap" id="{BLOCK_ID}"><div class="msec"><div class="msec-l">相場の局面（画像）'
            '<span class="msec-en">Daily → Post</span></div><div class="msec-q">Dailyタブの分析からSNS用の画像と投稿文</div></div>'
            + "".join(parts) + SCRIPT + '<span class="pq-end"></span></div>')


def apply(text: str) -> str:
    items = cards(text)
    if not items:
        return text
    block = block_html(items)
    if BLOCK_RE.search(text):
        out = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        m = re.search(r'<div[^>]*\bid="t-post1"[^>]*>', text)
        if not m:
            print("post cards: Publish tab not found; cards not inserted", flush=True)
            return text
        out = text[:m.end()] + block + text[m.end():]
    out = STYLE_RE.sub("", out)
    return out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out
