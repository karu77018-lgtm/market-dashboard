"""手動更新の案内 (display only).  Under the page header, for the few times a year the daily
refresh does not publish by itself.

* Normally: one folded line 「自動更新が止まったとき」 with the steps inside.
* When the page is behind: the browser compares the page's session with the NYSE closes that
  followed it (computed here, holidays and early closes included, embedded as UTC times) and,
  once a newer session closed more than GRACE ago, shows a warning with a large button that
  opens the refresh workflow in the GitHub app (or the browser) and the steps written out, so
  nothing has to be remembered.

The workflow can only be started by someone with write access to the repository, so the link
carries no secret.  Idempotent.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import market_calendar as mc

BLOCK_ID = "refresh-help"
STYLE_ID = "refresh-help-style"
WORKFLOW_URL = "https://github.com/karu77018-lgtm/market-dashboard/actions/workflows/refresh-source-mc57.yml"
GRACE_HOURS = 4      # close + ~2h for the scheduled refresh to publish, + margin
AHEAD = 30           # trading sessions after the page's session to embed

STYLE = (
    f'<style id="{STYLE_ID}">'
    '#refresh-help{margin:6px 0 10px}'
    '#refresh-help details{font-size:12.5px;color:var(--ds-ink-2,#46443d)}'
    '#refresh-help summary{cursor:pointer;color:var(--ds-muted,#6b685e);font-weight:700;padding:2px 0}'
    '#refresh-help .rh-warn{display:none;background:#f7efd9;border:1px solid #e3d3a0;border-radius:12px;padding:10px 12px;margin:0 0 6px}'
    '#refresh-help.rh-late .rh-warn{display:block}'
    '#refresh-help.rh-late details.rh-quiet{display:none}'
    '#refresh-help .rh-h{font-size:14px;font-weight:800;color:var(--ds-warn,#8a5a12);margin-bottom:6px}'
    '#refresh-help .rh-btn{display:block;text-align:center;background:var(--ds-accent,#2659ab);color:#fff;font-weight:800;'
    'font-size:15px;border-radius:10px;padding:11px 10px;text-decoration:none;margin:6px 0 8px}'
    '#refresh-help ol{margin:4px 0 2px;padding-left:1.3em}'
    '#refresh-help li{font-size:12.5px;line-height:1.6;margin:2px 0}'
    '#refresh-help .rh-note{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55}'
    '</style>'
)


def closes_after(session: str, n: int = AHEAD) -> list[int]:
    """UTC epoch seconds of the next ``n`` NYSE closes after ``session``."""
    day, out = date.fromisoformat(session), []
    for _ in range(n * 2 + 20):
        day += timedelta(days=1)
        if mc.is_trading_day(day):
            out.append(int(mc.session_close_utc(day).timestamp()))
            if len(out) == n:
                break
    return out


def steps_html() -> str:
    return (
        f'<a class="rh-btn" href="{WORKFLOW_URL}" rel="noopener" target="_blank">更新を始める（GitHubが開きます）</a>'
        '<ol><li>開いた画面の「Run workflow」を押す（GitHubアプリでもブラウザでも同じ。ログインを求められたらログイン）</li>'
        '<li>出てきた緑の「Run workflow」をもう一度押す（ブランチは main のまま）</li>'
        '<li>15〜30分たったら、このページを再読み込みする</li></ol>'
        '<div class="rh-note">平日の朝（7:52）には自動チェックが同じことを行い、スマホに通知します。'
        '押せるのはリポジトリの持ち主だけなので、他の人が押しても何も起きません。'
        '同じ更新がすでに動いているときは、終わるのを待ってから順番に実行されます。</div>'
    )


def block_html(session: str) -> str:
    closes = json.dumps(closes_after(session), separators=(",", ":"))
    md = f"{int(session[5:7])}/{int(session[8:10])}"
    return (
        # attributes in alphabetical order: the HTML parser other adapters use writes them so
        f'<div data-closes="{closes}" data-grace="{GRACE_HOURS}" data-session="{session}" id="{BLOCK_ID}">'
        f'<div class="rh-warn"><div class="rh-h">⚠ 自動更新が遅れています（このページは{md}終値の時点）</div>'
        + steps_html() + '</div>'
        '<details class="rh-quiet"><summary>自動更新が止まったときの手動更新</summary>' + steps_html() + '</details>'
        '<script>(function(){var b=document.getElementById("refresh-help");if(!b)return;'
        'var c=JSON.parse(b.getAttribute("data-closes")||"[]"),g=+b.getAttribute("data-grace")*3600,'
        'now=Date.now()/1000;if(c.length&&now>c[0]+g)b.className="rh-late";})();</script>'
        '</div>'
    )


BLOCK_RE = re.compile(rf'<div data-closes="[^"]*" data-grace="[^"]*" data-session="[^"]*" id="{BLOCK_ID}">.*?</script></div>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)
ANCHOR_RE = re.compile(r'(<header>.*?</header>)', re.S)


def page_session(text: str, root: Path | None) -> str | None:
    if root is not None:
        try:
            return json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
        except (OSError, ValueError, KeyError):
            pass
    m = re.search(r'<div class="asof">分析基準日 (\d{4}-\d{2}-\d{2})</div>', text)
    return m.group(1) if m else None


def apply(text: str, root: Path | None = None) -> str:
    session = page_session(text, root)
    if not session:
        return text
    block = block_html(session)
    if BLOCK_RE.search(text):
        out = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        m = ANCHOR_RE.search(text)
        if not m:
            return text
        out = text[:m.end()] + block + text[m.end():]
    out = STYLE_RE.sub("", out)
    return out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out
