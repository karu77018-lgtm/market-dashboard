"""Notice under the header when an added card did not reach the latest close (display only).

The added cards skip quietly when an input fails and keep their last state, so without this the page would
show an old reading next to new prices.  Each card stores its session in the page; any that is missing or
older than latest-manifest.json is listed here, and the refresh log gets a GitHub warning.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

BLOCK_ID = "display-health"
CHECKS = (  # (label, module, field holding the session)
    ("局面チェック", "phase_check", "session"),
    ("今回の下げの分解", "decline_anatomy", "session"),
    ("FTDの騙しチェック", "ftd_check", "session"),
    ("F1〜F3の推移", "regime_history", "session"),
)
BLOCK_RE = re.compile(rf'<div class="dh-note" id="{BLOCK_ID}"[^>]*>.*?</div>', re.S)


def stale(text: str, session: str | None) -> list[tuple[str, str | None]]:
    out = []
    for label, mod, field in CHECKS:
        try:
            m = __import__(mod)
            st = m.embedded_state(text)
        except Exception:  # a module that cannot load counts as missing
            st = None
        got = (st or {}).get(field)
        if session and (got is None or got < session):
            out.append((label, got))
    return out


def apply(text: str, root: Path) -> str:
    text = BLOCK_RE.sub("", text)
    try:
        session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8")).get("session_date")
    except (OSError, ValueError):
        return text
    bad = stale(text, session)
    if not bad:
        return text
    for label, got in bad:
        print(f"::warning title=display card not updated::{label}: {got or 'missing'} (latest {session})", flush=True)
    items = "、".join(f'{html.escape(label)}（{html.escape(got) + "時点" if got else "表示なし"}）' for label, got in bad)
    note = (f'<div class="dh-note" id="{BLOCK_ID}" style="margin:6px 12px;padding:6px 10px;border-radius:8px;font-size:12px;'
            'line-height:1.5;background:#fff4e5;color:#7a4a00;border:1px solid #f0c27a">'
            f'一部の表示が{html.escape(session)}の終値に更新されていません：{items}。次の更新で直らなければ確認が必要です。</div>')
    i = text.find("</header>")
    return text[:i + 9] + note + text[i + 9:] if i >= 0 else text
