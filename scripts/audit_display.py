"""Display corrections from the 2026-10-05 audit.  Display only, idempotent.

* F05 Weekly: drop the archived Core 12 "保有12の週次" chips (a model, not real
  holdings), drop the archived emergency-brake state from the conclusion, and
  point the account section to where things actually live now.
* F06 Publish: the share cards printed the session DATE converted from UTC
  midnight to JST ("2026-10-02 09:00 JST"), a time that never happened; show
  the US session date instead.
* F04 前回からの変化: the frozen generator's change log never persists its state
  in this pipeline and still talks about the archived Core 12 portfolio.  It is
  replaced by a change log of the new rule built from the public track-record
  ledger (本命 in/out, market regime) and the MC57 history.
* P3: ETF rotation maps explain a 100-centred SPY relative strength (not the
  50-centred RS189 percentile of the theme map); MC57 no longer carries the old
  "credit dropped" renormalisation note; "nan" is shown as 未取得.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ETF_RRG_DESC = ('横=SPYに対する相対力（直近63日平均を100とした比・100が市場並み・右ほど強い）／'
                '縦=その10日の変化率（上ほど相対力が加速）。4象限は 改善（左上）→主導（右上）→弱化（右下）→停滞（左下）の時計回り。')
CHLOG_ID = "rule-changelog"


def fix_weekly(text: str) -> str:
    text = re.sub(r'<div class="mut"[^>]*>保有12の週次 .*?</div><div style="display:flex;flex-wrap:wrap;gap:6px">.*?</div>',
                  "", text, count=1, flags=re.S)
    text = re.sub(r"　・　非常口 <b>[^<]*</b>", "", text, count=1)
    return text.replace("カーブ×21EMA（残高・非常口・資産曲線はPositions）",
                        "資産曲線と記録はPositions（Core 12時代の非常口はアーカイブ）")


def fix_publish_time(text: str, session: str) -> str:
    return text.replace(f"{session} 09:00 JST", f"米国 {session} 終値")


def fix_notes(text: str) -> str:
    text = re.sub(r'<div class="note">注記：データ未取得のため除外し残り指標で100点満点に再正規化 → [^<]*</div>', "", text)
    text = text.replace("RS189 nan", "RS189 未取得")

    def etf_card(m: re.Match) -> str:
        block = m.group(0)
        if "SPYとの相対力" not in block:
            return block
        return re.sub(r'(<div class="msec-g rrg-desc" style="display:none">)横=RS189百分位中央値[^<]*',
                      lambda x: x.group(1) + ETF_RRG_DESC, block)

    return re.sub(r'<div class="sub">GICS11セクター＋スタイル5本をSPYとの相対力で配置.*?rrg-desc" style="display:none">[^<]*'
                  r'|<div class="sub">テーマETF\d*本の温度計.*?rrg-desc" style="display:none">[^<]*',
                  etf_card, text, flags=re.S)


def _regime_word(value: str | None) -> str:
    return {"on": "新規OK", "off": "新規停止", "unknown": "判定不可"}.get(value or "", "不明")


def changelog_html(ledger: dict | None, mc57: dict | None, session: str) -> str:
    e = html.escape
    sessions = sorted((ledger or {}).get("sessions", {}))
    lines: list[str] = []
    ref = None
    if session in sessions and sessions.index(session) > 0:
        ref = sessions[sessions.index(session) - 1]
        today, prev = ledger["sessions"][session], ledger["sessions"][ref]
        now = {r["t"] for r in today.get("best", [])}
        before = {r["t"] for r in prev.get("best", [])}
        if now - before:
            lines.append("本命 IN: <b>" + e(" ".join(sorted(now - before))) + "</b>")
        if before - now:
            lines.append("前日の本命から外れた: " + e(" ".join(sorted(before - now))))
        if today.get("regime") != prev.get("regime"):
            lines.append(f"地合い <b>{_regime_word(prev.get('regime'))}→{_regime_word(today.get('regime'))}</b>")
    hist = [r for r in (mc57 or {}).get("history", []) if isinstance(r, dict) and r.get("date") and r.get("mc57") is not None]
    hist.sort(key=lambda r: r["date"])
    if len(hist) >= 2 and hist[-1]["date"] == session:
        d = float(hist[-1]["mc57"]) - float(hist[-2]["mc57"])
        if abs(d) >= 3:
            lines.append(f"MC57 <b>{float(hist[-2]['mc57']):.0f}→{float(hist[-1]['mc57']):.0f}</b>（{d:+.0f}）")
        ref = ref or hist[-2]["date"]
    if ref is None:
        body = ('<div class="sub">比較できる前日の記録がまだありません（本命の記録は公開成績タブの台帳から作ります）。'
                '記録が2日分そろうと、ここに前日からの変化を出します。</div>')
    elif not lines:
        body = f'<div class="sub">前回（{e(ref)}）から重要な変化なし。</div>'
    else:
        body = ('<ul class="chlog">' + "".join(f"<li>{x}</li>" for x in lines) + "</ul>"
                + f'<div class="note">比較基準: {e(ref)}（新ルールの本命・地合い・MC57）</div>')
    return (f'<div class="card ch-card" id="{CHLOG_ID}"><h2>前回からの変化<span class="h2en">Change Log</span></h2>'
            f'{body}</div>')


def fix_changelog(text: str, root: Path, session: str) -> str:
    try:
        ledger = json.loads((root / "track-record" / "signals.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ledger = None
    try:
        mc57 = json.loads((root / "data" / "mc57.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mc57 = None
    card = changelog_html(ledger, mc57, session)
    pattern = re.compile(rf'<div class="card ch-card"(?: id="{CHLOG_ID}")?><h2>前回からの変化.*?</div>(?:</div>)?(?=<div class="msec">)', re.S)
    m = pattern.search(text)
    if not m:
        return text
    return text[:m.start()] + card + text[m.end():]


def apply(text: str, root: Path, session: str) -> str:
    text = fix_weekly(text)
    text = fix_publish_time(text, session)
    text = fix_notes(text)
    return fix_changelog(text, root, session)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    page.write_text(apply(page.read_text(encoding="utf-8"), root, session), encoding="utf-8")
