"""Fold the explanations and internal notes on every tab and the cards above the tabs (display only), so any part of the page screenshots clean.

At load, notes (method, caveats, data source lines) are moved into <details class="xfold"> whose summary is a small
"説明" line, closed.  Two kinds are picked:
- known note classes of the dashboard (NOTE_CLASSES)
- any other block of prose (not on the Rules tab, whose sentences are the rules): a div/p whose own text is a sentence (has "。", 45+ characters) and that holds no
  table, chart, image, control or nested block.  Reading lines (the one-line verdicts) are kept visible.
Adjacent notes share one fold.  Nothing inside an existing <details>, a table, a header or the share-card iframes
is touched (the share cards fold their own notes).
"""
from __future__ import annotations

import json
import re

STYLE_ID = "xfold-style"
SCRIPT_ID = "xfold-script"
NOTE_CLASSES = ("note", "rnote", "tr-note", "mbnote", "mh-history-note", "pfoot", "foot", "em-foot", "sn-note", "cmt-note",
                "lbnote", "rrg-desc", "sw-hint", "pw-note", "fc-note", "rk-note", "tr-why", "bh-why", "postnote")
KEEP_CLASSES = ("read", "mkt20-read", "mbread", "da-lead", "bh-q", "pc-sub", "msec-q", "msec-l", "fold-k", "pq-cap",
                "rgr-head", "pl-sum", "jev-asof", "ccrow", "bh-next", "sw-reg", "rwarn")
PROSE_OFF = ("t-rules",)       # the Rules tab's sentences are the rules themselves: only its note classes fold

STYLE = (
    f'<style id="{STYLE_ID}">'
    'details.xfold{margin:4px 0}'
    'details.xfold>summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:4px;font-size:11px;'
    'font-weight:700;color:var(--ds-muted,#84887c);opacity:.75;user-select:none;padding:1px 0}'
    'details.xfold>summary::-webkit-details-marker{display:none}'
    'details.xfold>summary::before{content:"\\25B8";font-size:9px}'
    'details.xfold[open]>summary::before{content:"\\25BE"}'
    'details.xfold[open]>summary{margin-bottom:4px}'
    '</style>'
)
SCRIPT = (
    f'<script id="{SCRIPT_ID}">(function(){{'
    f'var NOTE={json.dumps(list(NOTE_CLASSES))},KEEP={json.dumps(list(KEEP_CLASSES))},OFF={json.dumps(list(PROSE_OFF))};'
    'var INLINE=/^(B|STRONG|SPAN|EM|SMALL|A|BR|I|CODE|SUP|SUB|MARK|U|S)$/;'
    'function has(el,list){for(var i=0;i<list.length;i++){if(el.classList.contains(list[i]))return true;}return false;}'
    'function own(el){var t="";el.childNodes.forEach(function(n){if(n.nodeType===3||(n.nodeType===1&&INLINE.test(n.tagName)))t+=n.textContent;});return t.trim();}'
    'function prose(el){if(el.querySelector("table,svg,canvas,img,button,input,select,textarea,details,iframe,div,p,ul,ol,section"))return false;'
    'var t=own(el);return t.length>=45&&t.indexOf("\\u3002")>=0;}'
    'function skip(el){return has(el,KEEP)||!!el.closest("details,summary,button,table,.xfold,.hd,.msec,.pq-cap,header,nav,[data-noxfold]");}'
    'function wrap(el){var p=el.previousSibling;while(p&&p.nodeType===3&&!p.textContent.trim())p=p.previousSibling;'
    'if(p&&p.nodeType===1&&p.classList.contains("xfold")){p.appendChild(el);return;}'
    'var d=document.createElement("details");d.className="xfold";var s=document.createElement("summary");s.textContent="\\u8aac\\u660e";'
    'el.parentNode.insertBefore(d,el);d.appendChild(s);d.appendChild(el);}'
    'function run(){var found=[];document.querySelectorAll("body div,body p").forEach(function(el){'
    'if(skip(el))return;var sec=el.closest("section");if(has(el,NOTE)||(OFF.indexOf(sec&&sec.id)<0&&prose(el)))found.push(el);});'
    'found.forEach(function(el){if(!el.closest(".xfold")&&el.parentNode)wrap(el);});}'
    'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",run);else run();})();</script>'
)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)
SCRIPT_RE = re.compile(rf'<script id="{SCRIPT_ID}">.*?</script>', re.S)


def apply(text: str) -> str:
    out = SCRIPT_RE.sub("", STYLE_RE.sub("", text))
    if "</head>" not in out or "</body>" not in out:
        return text
    out = out.replace("</head>", STYLE + "</head>", 1)
    i = out.rfind("</body>")
    return out[:i] + SCRIPT + out[i:]
