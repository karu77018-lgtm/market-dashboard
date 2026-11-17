"""Folding for the blocks added on top of the original dashboard (display only).

Each block renders as <details class="fold" data-fold="..."> whose summary keeps the title and a one-line
result, so the page stays short and the key reading is still visible.  Closed by default; a tap opens it,
and the choice is remembered on that device (localStorage, wrapped in try/catch).
"""
from __future__ import annotations

import re

STYLE_ID = "fold-style"
SCRIPT_ID = "fold-script"

STYLE = (
    f'<style id="{STYLE_ID}">'
    'details.fold>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;flex-wrap:wrap}'
    'details.fold>summary::-webkit-details-marker{display:none}'
    'details.fold>summary::after{content:"開く";margin-left:auto;font-size:11px;font-weight:700;padding:2px 8px;'
    'border-radius:10px;border:1px solid var(--ds-line,#dedbd2);color:var(--ds-accent,#2659ab);white-space:nowrap}'
    'details.fold[open]>summary::after{content:"たたむ"}'
    'details.fold>summary>*{order:0}details.fold>summary::after{order:1}'
    'details.fold>summary .fold-k{order:2;flex-basis:100%;font-size:12.5px;font-weight:700;line-height:1.5;color:var(--ds-ink-2,#46443d)}'
    'details.fold>summary .fold-k:empty{display:none}'
    'details.fold[open]>summary .fold-k{display:none}'
    'details.fold>summary h2{margin:0}'
    '.fold-sub>summary{padding:6px 0}'
    '.fold-sub>summary .fold-t{font-size:13px;font-weight:800;color:var(--ds-ink,#1c1b19)}'
    '</style>'
)
SCRIPT = (
    f'<script id="{SCRIPT_ID}">(function(){{function init(){{'
    'document.querySelectorAll("details.fold[data-fold]").forEach(function(d){'
    'if(d.dataset.foldInit)return;d.dataset.foldInit="1";var k="fold:"+d.dataset.fold;'
    'try{var v=localStorage.getItem(k);if(v==="1")d.open=true;}catch(e){}'
    'd.addEventListener("toggle",function(){try{localStorage.setItem(k,d.open?"1":"0");}catch(e){}});});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();})();</script>'
)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)
SCRIPT_RE = re.compile(rf'<script id="{SCRIPT_ID}">.*?</script>', re.S)


def card(fold_id: str, title_html: str, key_html: str, body: str) -> str:
    """A card's header as the summary (title + one-line result), the rest as the body."""
    return (f'<details class="fold" data-fold="{fold_id}"><summary class="chd">{title_html}'
            f'<span class="fold-k">{key_html}</span></summary>{body}</details>')


def sub(fold_id: str, title: str, key_html: str, body: str) -> str:
    """A block inside an existing card."""
    return (f'<details class="fold fold-sub" data-fold="{fold_id}"><summary><span class="fold-t">{title}</span>'
            f'<span class="fold-k">{key_html}</span></summary>{body}</details>')


def ensure(text: str) -> str:
    """Add the shared style and script once."""
    text = STYLE_RE.sub("", text)
    text = SCRIPT_RE.sub("", text)
    if "</head>" in text:
        text = text.replace("</head>", STYLE + "</head>", 1)
    if "</body>" in text:
        i = text.rfind("</body>")
        text = text[:i] + SCRIPT + text[i:]
    return text
