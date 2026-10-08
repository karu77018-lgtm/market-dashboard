"""Move the NQ trend signal and leverage (SOXL) cards into the archive tab.

Display only.  Since October 2026 TQQQ is run by the TQQQ rule (Rules tab 9,
tqqq_rule.py) as the place for the swing rule's idle money, and new entries use
the QQQ 200-day line, so the NQ-SAR signal card, the Daily NQ pill, the Weekly
NQ regime band and the SOXL leverage card are no longer part of operation.  They
are moved (ids kept, so their scripts keep working) under one header in the
archive tab, and the sentences that still pointed at them are reworded.

Every step checks its own state, so a page that was already converted is
returned unchanged apart from the re-rendered weekly stance line.

  python scripts/legacy_archive.py [--root .] [--html source-mc57.html]
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parent))

import archive_tab  # noqa: E402
import tqqq_rule  # noqa: E402

ARCHIVE_ID = archive_tab.ARCHIVE_ID
MSEC_ID = "legacy-nq-msec"
STANCE_ID = "weekly-stance"
LEGACY_ATTR = "data-legacy"
MSEC = (f'<div class="msec archive-msec" id="{MSEC_ID}"><div class="msec-l">旧ルール：NQトレンド信号・レバ枠（運用停止）'
        '<span class="msec-en">NQ signal &amp; leverage — archived</span></div>'
        '<div class="msec-q">TQQQはRulesタブ9のTQQQルール（余剰資金の置き先）に移行。'
        'NQ-SARの色・目標露出・SOXL投入帯・レジームの帯は表示のみ</div></div>')
WEEKLY_CARDS = ("NQレジームの帯", "レバレッジ・コンディション")
TEXT_FIXES = (
    # Weekly section headers / guidance
    ("NQレジームの帯で1週間を振り返る（詳細な推移はDaily）", "週次騰落ボードで1週間を振り返る（詳細な推移はDaily）"),
    ("広がり・データ品質・レバ環境", "広がり・データ品質"),
    ("③でブレッドスとレバ環境", "③でブレッドスとデータ品質"),
    # Daily reversal leaderboard
    ('個別が確認できるまでは TQQQ/SOXL の投入帯（50MA上0〜3%）で"面"を取る→旧リーダー確認で個別へ（段階論）。',
     "個別が確認できるまでは余剰資金のTQQQルール枠（Rulesタブ9）が指数側を受け持つ→旧リーダー確認で個別へ（段階論）。"),
)


def _h2(node: Tag) -> str:
    h = node.find("h2")
    return h.get_text(" ", strip=True) if h else ""


def _replace_text(root: Tag, old: str, new: str) -> None:
    for node in list(root.find_all(string=lambda s: s and old in s)):
        if node.parent and node.parent.name in ("script", "style"):
            continue
        node.replace_with(NavigableString(str(node).replace(old, new)))


def _regime_text(soup: BeautifulSoup) -> tuple[str, str]:
    reg = soup.select_one("#rules-card .rreg")
    if reg is None:
        return "判定不可", "#747166"
    t = reg.get_text(" ", strip=True)
    if "新規OK" in t:
        return "新規OK", "#18813d"
    if "新規停止" in t:
        return "新規停止", "#c62828"
    return "判定不可", "#747166"


def stance_html(soup: BeautifulSoup, ledger: dict | None) -> str:
    word, color = _regime_text(soup)
    day, rec = tqqq_rule.latest(ledger)
    if rec:
        mode, _ = tqqq_rule.summary_words(rec)
        tq = f'TQQQ <b>{tqqq_rule._pct(float(rec.get("target") or 0))}</b>（{html.escape(mode)}）'
    else:
        tq = "判定不可"
    return (f'<div id="{STANCE_ID}" style="font-size:13px;line-height:1.7"><b>来週の姿勢</b>（地合い＝QQQの200日線）：'
            f'<b style="color:{color}">{word}</b>／TQQQルール：{tq}</div>')


def apply(text: str, ledger: dict | None) -> str:
    soup = BeautifulSoup(text, "html.parser")
    archive = soup.find("section", id=ARCHIVE_ID)
    if archive is None:
        return text
    daily = soup.find("section", id="t-market")
    weekly = soup.find("section", id="t-weekly")

    # 1) archive header right after the intro, then the legacy cards in order
    msec = archive.find(id=MSEC_ID)
    if msec is None:
        msec = BeautifulSoup(MSEC, "html.parser").find("div")
        intro = archive.find(id=archive_tab.INTRO_ID)
        if intro is not None:
            intro.insert_after(msec)
        else:
            archive.insert(0, msec)
    moving: list[Tag] = []
    for cid in ("taCard", "sarPill"):
        node = soup.find(id=cid)
        if node is not None and archive not in node.parents:
            moving.append(node)
    if weekly is not None:
        for child in [c for c in weekly.find_all(recursive=False) if isinstance(c, Tag)]:
            if any(_h2(child).startswith(k) for k in WEEKLY_CARDS):
                moving.append(child)
    last = msec
    for node in archive.find_all(attrs={LEGACY_ATTR: "nq"}, recursive=False):
        last = node
    for node in moving:
        node.extract()
        node[LEGACY_ATTR] = "nq"
        last.insert_after(node)
        last = node

    # 2) wording that still pointed at the NQ signal / leverage sleeve
    for scope in (s for s in (daily, weekly) if s is not None):
        for old, new in TEXT_FIXES:
            _replace_text(scope, old, new)

    # Daily summary "リスク" row: the leverage emergency brake is archived
    if daily is not None:
        for node in list(daily.select(".mkt20-deep b")):
            for t in list(node.find_all(string=lambda x: x and "非常口" in x)):
                t.replace_with(NavigableString(re.sub(r"・?非常口[^・]*", "", str(t)).strip("・")))

    # 3) weekly stance: QQQ 200-day regime + TQQQ rule (re-rendered every run)
    if weekly is not None:
        new = BeautifulSoup(stance_html(soup, ledger), "html.parser").find("div")
        cur = weekly.find(id=STANCE_ID)
        if cur is None:
            for div in weekly.find_all("div"):
                b = div.find("b", recursive=False)
                if b and b.get_text(strip=True) == "ゲート基準の来週姿勢":
                    cur = div
                    break
        if cur is not None:
            cur.replace_with(new)

    # 4) the archive intro (fixed once by archive_tab on fresh builds)
    intro = archive.find(id=archive_tab.INTRO_ID)
    if intro is not None and "TQQQルール" not in intro.get_text():
        intro.replace_with(BeautifulSoup(archive_tab.INTRO, "html.parser").find("div"))
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


def run(text: str, root: Path) -> str:
    return apply(text, tqqq_rule.load(root / tqqq_rule.LEDGER))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    page.write_text(run(page.read_text(encoding="utf-8"), root), encoding="utf-8")
