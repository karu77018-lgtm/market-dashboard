"""Setups tab, curated to the setups that earned a place (display only).

Local study 2015-2026 (current listings, QQQ above its 200-day line, the rule's
exits: -8% stop, same-amount adds at +10/+20%, close below the 21-EMA of lows):

  any liquid stock, any day                    PF 1.09
  発火前 / PP / 21EMA / VCP / VWAP / 底打ち     PF 1.04-1.22, below 1 since 2021
  leader states ①-⑤ (RS63>=85, 200MA)         PF 0.95-1.18
  the rule's selection (TT, DV top 5%, RS189)  PF 1.57
  IPOベース (listed <2y, first bases)           PF 1.80

Patterns add nothing outside the rule's selection and do not improve it inside
(that is what Positions 「次の候補」 already shows).  So Setups keeps only:

  IPOベース       young listings the rule cannot see (evidence above)
  RSライン先行     leaders outside the selection whose RS line leads the price
                  (PF 2.04, 2.48 with adds; scripts/rsline_lead.py)
  大化け候補       former leaders taking back their high after a 30%+ base
                  (2016-2025 bagger study; scripts/bagger_watch.py)
  オプション配置   candidates with room above / support below in the option walls -
                  no history, validated forward (scripts/option_layout.py)

Everything else (発火前, コンフルエンス, 発火トリガー, セットアップ評価, 底打ち,
リーダー監視) moves unchanged into アーカイブ 「旧セットアップ（参考）」; their
scripts keep working (static HTML, no ids depend on the tab).

Run after archive_tab.  Idempotent; a page curated by an older version is
migrated (remaining non-kept sections move, the intro is replaced).
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

MARK_ID = "setups-archive-msec"
KEEP = ("IPOベース", "RSライン先行", "大化け候補", "オプション配置", "支えへの接触")
NUMS = "①②③④⑤⑥⑦⑧⑨⑩"
INTRO_ID = "setups-intro"
INTRO = (
    f'<div class="card setups-intro" id="{INTRO_ID}"><div class="sub">検証で残ったものだけを表示しています。'
    '旧セットアップ（発火前・ポケットピボット・VCP・21EMAタッチ・VWAP・底打ち・リーダー監視）は、2015〜2026年の検証で'
    'どれも「流動性のある銘柄を適当に買う」と同程度（PF 1.0〜1.2、2021年以降は1未満）だったため、アーカイブタブに移しました。'
    'リーダーは「RSライン先行」と「大化け候補」に絞っています。形の良い候補はPositionsタブ「次の候補」を見てください。</div></div>'
)
RENAME = {"支えへの接触（オプション）": "支えへの接触（オプション・検証中）"}


def _msec_title(node: Tag) -> str:
    label = node.select_one(".msec-l") if isinstance(node, Tag) else None
    return label.get_text(" ", strip=True) if label else ""


def _set_number(msec: Tag, num: str | None) -> None:
    """Replace (or drop) the leading circled number of a section title."""
    label = msec.select_one(".msec-l")
    if label is None:
        return
    for node in label.find_all(string=True, recursive=False):
        text = str(node)
        stripped = text.lstrip()
        if stripped and stripped[0] in NUMS:
            rest = stripped[1:].lstrip()
            node.replace_with(NavigableString(f"{num} {rest}" if num else rest))
            return


def renumber(text: str) -> str:
    """Number the Setups section headers ①②③… in page order (regex, no reparse)."""
    a = text.find('<section id="t-today"')
    if a < 0:
        return text
    b = text.find("</section>", a)
    seg = text[a:b]
    count = iter(NUMS)
    head = re.compile(r'(<div class="msec[^"]*"[^>]*><div class="msec-l">)\s*[①-⑩]?\s*')
    seg = head.sub(lambda m: m.group(1) + next(count, "") + " ", seg)
    return text[:a] + seg + text[b:]


def apply(text: str) -> str:
    soup = BeautifulSoup(text, "html.parser")
    setups = soup.find("section", id="t-today")
    archive = soup.find("section", id="t-port")
    if setups is None or archive is None:
        return text
    groups: list[list[Tag]] = []
    current: list[Tag] | None = None
    kept_msecs: list[Tag] = []
    for child in [c for c in setups.find_all(recursive=False) if isinstance(c, Tag)]:
        if "msec" in (child.get("class") or []):
            title = _msec_title(child)
            if any(k in title for k in KEEP):
                current = None
                kept_msecs.append(child)
            else:
                current = [child]
                groups.append(current)
            continue
        if current is not None:
            current.append(child)
    old_intro = setups.find(id=INTRO_ID)
    intro_ok = old_intro is not None and "大化け候補" in old_intro.get_text()
    liq = setups.select("div.liqstick")
    if not groups and intro_ok and not liq:
        return text
    moved = [node.extract() for group in groups for node in group]
    for node in liq:                              # the liquidity filter has nothing left to filter here
        node.decompose()
    if old_intro is not None:
        old_intro.decompose()
    for msec in kept_msecs:
        label = msec.select_one(".msec-l")
        for old, new in RENAME.items():
            for node in (label.find_all(string=True, recursive=False) if label else []):
                if old in node and new not in node:
                    node.replace_with(NavigableString(str(node).replace(old, new)))
        # the section header and the card below said the same thing twice:
        # keep the header, let the card start with its content
        nxt = msec.find_next_sibling()
        if isinstance(nxt, Tag) and "card" in (nxt.get("class") or []) and "ds-merged" not in nxt.get("class"):
            nxt["class"] = (nxt.get("class") or []) + ["ds-merged"]
            msec["class"] = (msec.get("class") or []) + ["ds-merged-head"]
    anchor = kept_msecs[0] if kept_msecs else None
    if anchor is not None:
        anchor.insert_before(BeautifulSoup(INTRO, "html.parser"))
    else:
        setups.append(BeautifulSoup(INTRO, "html.parser"))
    if archive.find(id=MARK_ID) is None:
        archive.append(BeautifulSoup(
            f'<div class="msec archive-msec" id="{MARK_ID}"><div class="msec-l">旧セットアップ（参考）'
            '<span class="msec-en">Former setups</span></div>'
            '<div class="msec-q">2015〜2026年の検証で優位性が確認できなかったセットアップ。Setupsタブから移しました。表示のみ</div></div>',
            "html.parser"))
    else:
        q = archive.find(id=MARK_ID).select_one(".msec-q")
        if q is not None:
            q.string = "2015〜2026年の検証で優位性が確認できなかったセットアップ。Setupsタブから移しました。表示のみ"
    for node in moved:
        if "msec" in (node.get("class") or []):
            _set_number(node, None)
            classes = [c for c in (node.get("class") or []) if c != "ds-merged-head"]
            node["class"] = classes + (["archive-sub"] if "archive-sub" not in classes else [])
        elif "ds-merged" in (node.get("class") or []):
            node["class"] = [c for c in node.get("class") if c != "ds-merged"]
        archive.append(node)
    return renumber(str(soup).replace('<footer class="disc">', "<footer class='disc'>"))


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    page = Path(ap.parse_args().html)
    page.write_text(apply(page.read_text(encoding="utf-8")), encoding="utf-8")
    print("setups curated", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
