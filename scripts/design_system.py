"""One visual system for the whole dashboard (display only, CSS only).

The page is assembled from a frozen generator plus many adapters, each with its
own colours and sizes (35 font sizes, ~400 colours, dark-theme badges left over
from the old dark layout).  This adapter adds ONE stylesheet, last in <head>,
that sets shared tokens and normalises the recurring roles:

* page / card / line colours, one card shape and spacing;
* type scale: section 18 / card title 15.5 / body 14 / sub 12 / note 11.5,
  no text below 10px outside charts, headline values 24px tabular figures;
* the English duplicate labels next to Japanese titles are hidden;
* up / down / warn / info colours as tokens, low-contrast light greens fixed;
* every dark-theme badge (dark background + light text) is converted to the
  matching light tint of its own hue, generated from the page's own CSS so
  new badges are covered without listing them by hand.

No text, numbers, order or logic change.  The block is excluded from the Jev
page hash (render_jev_ranking.source_hash), so styling never makes the Jev
ranking look stale.  Idempotent.

  python scripts/design_system.py [--html source-mc57.html]
"""
from __future__ import annotations

import argparse
import colorsys
import re
from pathlib import Path

STYLE_ID = "ds-style"
SCRIPT_ID = "ds-script"
SCRIPT_RE = re.compile(rf'<script id="{SCRIPT_ID}">.*?</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)

TOKENS = {
    "--ds-paper": "#ebe9e3",      # page
    "--ds-card": "#f7f6f2",       # cards sit one step above the page
    "--ds-inset": "#efede7",      # boxes inside cards
    "--ds-line": "#dedbd2",
    "--ds-line-strong": "#cfcbc0",
    "--ds-ink": "#1c1b19",
    "--ds-ink-2": "#46443d",
    "--ds-muted": "#6b685e",
    "--ds-accent": "#2659ab",
    "--ds-up": "#17703f",
    "--ds-down": "#b3362c",
    "--ds-warn": "#8a5a12",
}

# light tints per hue family: (background, text, border)
FAMILIES = {
    "green": ("#e2f0e6", "#17683f", "#b5d8c1"),
    "teal": ("#ddefec", "#146457", "#b0d8d1"),
    "blue": ("#e3eaf6", "#23508f", "#b8c9e6"),
    "purple": ("#ece5f6", "#5b3a96", "#cfc0e8"),
    "red": ("#f6e1de", "#a3322a", "#e8b8b1"),
    "amber": ("#f4ead2", "#7a5512", "#e0c98f"),
    "neutral": ("#e4e2db", "#35332e", "#cfccc2"),
}

BASE_CSS = """
:root{%(tokens)s}
body{background:var(--ds-paper);color:var(--ds-ink);line-height:1.5;
 font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Helvetica Neue",sans-serif}
nav{background:rgba(235,233,227,.92)}
header h1{letter-spacing:.01em}
.card{background:var(--ds-card);border:1px solid var(--ds-line);border-radius:14px}
.card h2{font-size:15.5px;font-weight:800;letter-spacing:.01em;color:var(--ds-ink);font-feature-settings:"palt" 1;line-height:1.35}
.h2en,.msec-en,.cchd-en,.lab-en{display:none!important}
.card h2,.msec-l,.chd h2{text-wrap:balance;word-break:auto-phrase}
.msec{margin:28px 0 10px;padding-top:16px;border-top:1px solid var(--ds-line-strong)}
section>.msec:first-child{border-top:none;padding-top:4px;margin-top:8px}
.msec-l{font-size:18px;font-weight:800;letter-spacing:.01em;color:var(--ds-ink);font-feature-settings:"palt" 1;line-height:1.35}
.msec-q{font-size:12px;color:var(--ds-muted);margin-top:3px;line-height:1.5}
.card .sub{font-size:12px;color:var(--ds-ink-2);line-height:1.65}
.note,.lbnote,.cxpl-b,#t-rules .rnote,.tr-note,.jev-asof{font-size:11.5px;color:var(--ds-muted);line-height:1.65}
.cxpl>summary,.calcfold>summary{font-size:11px;color:var(--ds-accent)}
.disc{font-size:11px;color:var(--ds-muted)}
.chd{align-items:flex-start}
.chd-now b{font-size:24px;font-weight:800;letter-spacing:-.01em;font-variant-numeric:tabular-nums;line-height:1.05}
.vixcy .chd-now b{font-size:16px}
.chd-now span{font-size:10.5px;color:var(--ds-muted);font-weight:600}
.chd-now[style*="#7ff0a8"],.chd-now[style*="#20a751"],.chd-now[style*="#23824d"]{color:var(--ds-up)!important}
.chd-now[style*="#d95b5b"]{color:var(--ds-down)!important}
.chd-now[style*="#806819"]{color:var(--ds-warn)!important}
.pos,.up,.rsd.up{color:var(--ds-up)}
.neg,.dn,.rsd.dn{color:var(--ds-down)}
.rh{color:var(--ds-accent)}
.sar-blue,.sar-green,.sar-yellow,.sar-red{color:#fff}
.sar-blue .lab,.sar-green .lab,.sar-yellow .lab,.sar-red .lab,.sar-blue .lot,.sar-green .lot,.sar-yellow .lot,.sar-red .lot{color:rgba(255,255,255,.82)}
.lqf-b.active .lqf-tag{color:#dff3e6}
.kv{border-bottom-color:var(--ds-line)}
.card table th{font-size:11px;font-weight:700;color:var(--ds-muted)}
.card table td{border-color:var(--ds-line)}
.dax,.mc57-breadth-axis{font-size:10px;font-weight:500;color:var(--ds-muted)}
.dax,.mc57-breadth-axis{display:flex;justify-content:space-between;border-top:1px solid var(--ds-line);margin-top:2px;padding:6px 2px 0;line-height:1;font-variant-numeric:tabular-nums}
.rsx-hflow>div{grid-template-columns:52px minmax(0,1fr) auto;align-items:start}
.rsx-hflow>div>strong{grid-column:1;grid-row:1}
.rsx-hflow>div>.chips{grid-column:2;grid-row:1;display:flex;flex-wrap:wrap;gap:4px}
.rsx-hflow>div>.cp{grid-column:3;grid-row:1;width:auto;white-space:nowrap}
.rsx-hflow .chip{margin:0}
.mh-legend{display:flex;flex-wrap:wrap;gap:5px 6px;align-items:center;margin:2px 0 6px}
.mh-legend button,.mh-legend>span:not(.mh-unit){display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:700;color:var(--ds-ink-2);background:var(--ds-inset);border:1px solid var(--ds-line);border-radius:999px;padding:3px 9px;cursor:pointer;font-variant-numeric:tabular-nums}
.mh-legend>span:not(.mh-unit){cursor:default}
.mh-legend button b{font-weight:800;color:var(--ds-ink)}
.mh-legend button[aria-pressed="false"]{opacity:.42;background:transparent}
.mh-legend i{display:inline-block;width:12px;height:3px;border-radius:2px}
.mh-unit{font-size:10.5px;color:var(--ds-muted);margin-left:2px}
.ds-merged>.chd>h2,.ds-merged>.hdr>h2,.ds-merged-head>.msec-q{display:none}
.ds-merged>.chd:not(:has(button,.cp,.chd-now)),.ds-merged>.hdr:not(:has(button,.cp,.chd-now)){display:none}
.ds-merged>.chd,.ds-merged>.hdr{justify-content:flex-end}
.setups-intro{background:transparent;border:1px dashed var(--ds-line-strong)}
.setups-intro .sub{margin:0}
.pretail{white-space:normal;overflow:visible;text-overflow:clip;line-height:1.5}
.prenums div i{color:var(--ds-muted)}
.chip{padding:5px 10px;border-radius:8px;font-size:12px}
.chip.s-shape{border-color:var(--ds-line-strong);background:var(--ds-inset)}
a:focus-visible,button:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--ds-accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
[style*="font-size:8px"]:not(svg *),[style*="font-size: 8px"]:not(svg *),
[style*="font-size:8.5px"]:not(svg *),[style*="font-size:9px"]:not(svg *),
[style*="font-size: 9px"]:not(svg *),[style*="font-size:9.5px"]:not(svg *){font-size:10px!important}
"""


# One chart format at runtime (also for charts drawn later by JS): history charts are
# SVGs stretched with preserveAspectRatio="none", which squashes their value labels
# and turns end dots into ellipses.  Counter-scale labels to 10px with a paper halo,
# keep strokes 1-2px (non-scaling), draw the end dot round, and give every
# single-series history chart the same ink line (the market-history charts keep
# their own score colours).  DOM order is untouched.
CHART_JS = r"""(function(){
var INK='#1f4b8f',GRID='#e2dfd7',REF='#a9a598',LAB='#7a776c',HALO='#f7f6f2';
function stroked(e){var s=e.getAttribute('stroke');return s&&s!=='none'}
function prep(svg){
 if(svg.__ds)return true;
 if((svg.getAttribute('preserveAspectRatio')||'')!=='none')return false;
 var vb=svg.viewBox&&svg.viewBox.baseVal;if(!vb||!vb.width||!vb.height)return false;
 svg.__ds={w:vb.width,h:vb.height};
 var spark=svg.classList.contains('spark');
 svg.querySelectorAll('polyline,path,line,rect').forEach(function(e){if(stroked(e))e.setAttribute('vector-effect','non-scaling-stroke')});
 svg.querySelectorAll('line').forEach(function(l){if(l.getAttribute('stroke-dasharray'))l.setAttribute('stroke',REF);else if(!spark)l.setAttribute('stroke',GRID)});
 svg.querySelectorAll('text').forEach(function(t){t.setAttribute('fill',LAB);t.setAttribute('font-weight','600');
  t.setAttribute('stroke',HALO);t.setAttribute('paint-order','stroke');t.setAttribute('stroke-linejoin','round');
  t.__x=+(t.getAttribute('x')||0);t.__y=+(t.getAttribute('y')||0)});
 var series=[].filter.call(svg.querySelectorAll('polyline,path'),function(e){var f=e.getAttribute('fill');return stroked(e)&&(!f||f==='none')});
 if(series.length===1&&!spark&&!svg.closest('.mc57-candle,.mh-plot')){var col=series[0].getAttribute('stroke');series[0].setAttribute('stroke',INK);series[0].setAttribute('stroke-width','2');
  svg.querySelectorAll('stop').forEach(function(st){if(st.getAttribute('stop-color')===col)st.setAttribute('stop-color',INK)});
  svg.querySelectorAll('circle').forEach(function(c){if(c.getAttribute('fill')===col)c.setAttribute('fill',INK)})}
 svg.querySelectorAll('circle').forEach(function(c){var e=document.createElementNS('http://www.w3.org/2000/svg','ellipse');
  ['cx','cy','fill','stroke','class'].forEach(function(a){if(c.hasAttribute(a))e.setAttribute(a,c.getAttribute(a))});
  e.__r=+(c.getAttribute('r')||3);c.replaceWith(e)});
 var w=vb.width,right=[].filter.call(svg.querySelectorAll('text'),function(t){return t.__x>=w*0.9});
 if(right.length&&!spark&&!svg.closest('.mc57-candle')){
  // value labels get their own gutter on the right instead of sitting on the line
  var g=document.createElementNS('http://www.w3.org/2000/svg','g');
  [].slice.call(svg.childNodes).forEach(function(n){if(n.nodeName.toLowerCase()!=='defs'&&right.indexOf(n)<0)g.appendChild(n)});
  svg.insertBefore(g,right[0]);right.forEach(function(t){t.__x=w-1;t.setAttribute('x',w-1);t.setAttribute('text-anchor','end')});
  svg.__ds.g=g}
 return true}
function fit(svg){if(!prep(svg))return;var r=svg.getBoundingClientRect();if(!r.width||!r.height)return;
 var sx=r.width/svg.__ds.w,sy=r.height/svg.__ds.h;
 svg.querySelectorAll('text').forEach(function(t){var x=t.__x,y=t.__y;t.setAttribute('font-size',(10/sy).toFixed(2));
  t.setAttribute('stroke-width',(3/sy).toFixed(2));
  t.setAttribute('transform','translate('+x+' '+y+') scale('+(sy/sx).toFixed(4)+' 1) translate('+(-x)+' '+(-y)+')')});
 var k=1,g=svg.__ds.g;if(g){k=Math.max(.6,(svg.__ds.w-38/sx)/svg.__ds.w);g.setAttribute('transform','scale('+k.toFixed(4)+' 1)');var ax=svg.nextElementSibling;if(ax&&ax.classList.contains('dax'))ax.style.paddingRight=Math.round(svg.__ds.w*(1-k)*sx)+'px'}
 svg.querySelectorAll('ellipse').forEach(function(e){if(e.__r){var kk=g&&g.contains(e)?k:1;e.setAttribute('rx',(e.__r/(sx*kk)).toFixed(2));e.setAttribute('ry',(e.__r/sy).toFixed(2))}})}
var ro=window.ResizeObserver?new ResizeObserver(function(es){es.forEach(function(e){fit(e.target)})}):null;
function scan(root){(root.querySelectorAll?root.querySelectorAll('svg'):[]).forEach(function(svg){if(prep(svg)){if(ro)ro.observe(svg);fit(svg)}})}
function start(){scan(document);new MutationObserver(function(ms){ms.forEach(function(m){m.addedNodes.forEach(function(n){if(n.nodeType!==1)return;if(n.tagName&&n.tagName.toLowerCase()==='svg'){if(prep(n)){if(ro)ro.observe(n);fit(n)}}else scan(n)})})}).observe(document.body,{childList:true,subtree:true});
 if(!ro)window.addEventListener('resize',function(){scan(document);document.querySelectorAll('svg').forEach(fit)})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();"""


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(c: str) -> float:
    r, g, b = _hex(c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def family(fg: str) -> str:
    h, l, s = colorsys.rgb_to_hls(*_hex(fg))
    if s < 0.18:
        return "neutral"
    deg = h * 360
    if deg < 18 or deg >= 330:
        return "red"
    if deg < 70:
        return "amber"
    if deg < 160:
        return "green"
    if deg < 200:
        return "teal"
    if deg < 255:
        return "blue"
    return "purple"


RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}")
BG_RE = re.compile(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b")
FG_RE = re.compile(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b")
SHADOW_RE = re.compile(r"box-shadow\s*:[^;]*rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*([\d.]+)\)")
MONO_RE = re.compile(r"font-family\s*:[^;]*mono", re.I)
FLOOR_SKIP = {".liqsub"}  # caption under a one-line sticky filter; 10px would wrap the buttons
FS_RE = re.compile(r"font-size\s*:\s*([\d.]+)px")


def page_css(text: str) -> str:
    css = "".join(m.group(1) for m in re.finditer(r"<style(?![^>]*\bid=\"%s\")[^>]*>(.*?)</style>" % STYLE_ID, text, re.S))
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def generated_rules(css: str) -> list[str]:
    """Light versions of dark-theme badges, and a 10px floor for tiny HTML text."""
    out: list[str] = []
    seen: set[str] = set()
    for sel, body in RULE_RE.findall(css):
        sel = " ".join(sel.split())
        if not sel or sel in seen or "::" in sel or ":before" in sel or ":after" in sel:
            continue
        bg, fg = BG_RE.search(body), FG_RE.search(body)
        if bg and fg and luminance(bg.group(1)) < 0.25 and luminance(fg.group(1)) > luminance(bg.group(1)):
            b, f, line = FAMILIES[family(fg.group(1))]
            border = f";border-color:{line}" if "border" in body else ""
            out.append(f"{sel}{{background:{b};color:{f}{border};box-shadow:none}}")
            seen.add(sel)
        sh = SHADOW_RE.search(body)
        if sh and float(sh.group(1)) >= 0.3:          # dark-theme glow -> soft lift
            out.append(f"{sel}{{box-shadow:0 4px 12px rgba(28,27,25,.12)}}")
            seen.add(sel)
        if MONO_RE.search(body):                       # one family; numbers stay aligned
            out.append(f"{sel}{{font-family:inherit;font-variant-numeric:tabular-nums}}")
            seen.add(sel)
        fs = FS_RE.search(body)
        if fs and float(fs.group(1)) < 10 and sel not in FLOOR_SKIP and not re.search(r"\b(svg|text|tspan)\b", sel):
            out.append(f"{sel}{{font-size:10px}}")
            seen.add(sel)
    return out


def stylesheet(text: str) -> str:
    tokens = ";".join(f"{k}:{v}" for k, v in TOKENS.items())
    css = BASE_CSS % {"tokens": tokens} + "\n".join(generated_rules(page_css(text)))
    css = "\n".join(line.strip() for line in css.strip().splitlines() if line.strip())
    return f'<style id="{STYLE_ID}">{css}</style>'


ASSET_RE = re.compile(r"assets/market-history\.(js|css)\?v=[0-9a-f]+")


def bump_asset_revision(text: str, root: Path | None) -> str:
    """Point the page at the current market-history assets (same hash rule as
    market_internals_ui), so a display-only publish never serves a stale cached script."""
    if root is None:
        return text
    assets = [root / "assets/market-history.js", root / "assets/market-history.css"]
    if not all(p.is_file() for p in assets):
        return text
    import hashlib
    rev = hashlib.sha256(b"".join(p.read_bytes() for p in assets)).hexdigest()[:12]
    return ASSET_RE.sub(lambda m: f"assets/market-history.{m.group(1)}?v={rev}", text)


def apply(text: str, root: Path | None = None) -> str:
    text = bump_asset_revision(text, root)
    text = SCRIPT_RE.sub("", STYLE_RE.sub("", text))
    if "</head>" not in text:
        return text
    i = text.rfind("</head>")
    text = text[:i] + stylesheet(text) + text[i:]
    j = text.rfind("</body>")
    return text if j < 0 else text[:j] + f'<script id="{SCRIPT_ID}">{CHART_JS}</script>' + text[j:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    page = Path(ap.parse_args().html)
    page.write_text(apply(page.read_text(encoding="utf-8"), page.resolve().parent), encoding="utf-8")
    print("design system applied", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
