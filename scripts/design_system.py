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
a:focus-visible,button:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--ds-accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
[style*="font-size:8px"]:not(svg *),[style*="font-size: 8px"]:not(svg *),
[style*="font-size:8.5px"]:not(svg *),[style*="font-size:9px"]:not(svg *),
[style*="font-size: 9px"]:not(svg *),[style*="font-size:9.5px"]:not(svg *){font-size:10px!important}
"""


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


def apply(text: str) -> str:
    text = STYLE_RE.sub("", text)
    if "</head>" not in text:
        return text
    i = text.rfind("</head>")
    return text[:i] + stylesheet(text) + text[i:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    page = Path(ap.parse_args().html)
    page.write_text(apply(page.read_text(encoding="utf-8")), encoding="utf-8")
    print("design system applied", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
