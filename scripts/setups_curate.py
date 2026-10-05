"""Setups tab, curated: keep what feeds or tests the swing rule, archive the rest.

Display only.  The Setups tab had grown to seven sections and eleven lists, most
of them older setups that the current rule (Rules tab) was never validated on.
It now keeps three, in this order:

  ① 発火前           bases that are quiet and tight - the rule's 形 conditions forming
  ② 支えへの接触      option put-wall touches - under weekly validation
  ③ リーダー監視      RS>=85 above the 200-day line - the pool the next 本命 come from

The other sections (コンフルエンス, 発火トリガー, セットアップ評価, 底打ち) are
moved unchanged into the アーカイブ tab under 「旧セットアップ（参考）」, so nothing
is lost and their scripts keep working (static HTML, no ids depend on the tab).

Run after archive_tab.  Idempotent: an already curated page is returned unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

MARK_ID = "setups-archive-msec"
KEEP = ("発火前", "支えへの接触", "リーダー母集団")
NUMS = "①②③④⑤⑥⑦⑧⑨⑩"
INTRO_ID = "setups-intro"
INTRO = (
    f'<div class="card setups-intro" id="{INTRO_ID}"><div class="sub">新ルールの次の買い候補につながる3つに絞っています。'
    'ほかの旧セットアップはアーカイブタブにあります。</div></div>'
)
RENAME = {"リーダー母集団": "リーダー監視（RS≥85・200MA上）"}


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


def apply(text: str) -> str:
    if f'id="{MARK_ID}"' in text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    setups = soup.find("section", id="t-today")
    archive = soup.find("section", id="t-port")
    if setups is None or archive is None:
        return text
    groups: list[list[Tag]] = []
    current: list[Tag] | None = None
    moved: list[Tag] = []
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
    if not groups:
        return text
    for group in groups:
        for node in group:
            moved.append(node.extract())
    for n, msec in enumerate(kept_msecs):
        _set_number(msec, NUMS[n])
        label = msec.select_one(".msec-l")
        for old, new in RENAME.items():
            for node in (label.find_all(string=True, recursive=False) if label else []):
                if old in node:
                    node.replace_with(NavigableString(str(node).replace(old, new)))
        # the section header and the card below said the same thing twice:
        # keep the header, let the card start with its content
        nxt = msec.find_next_sibling()
        if isinstance(nxt, Tag) and "card" in (nxt.get("class") or []):
            nxt["class"] = (nxt.get("class") or []) + ["ds-merged"]
            msec["class"] = (msec.get("class") or []) + ["ds-merged-head"]
    first = kept_msecs[0] if kept_msecs else None
    if first is not None:
        first.insert_before(BeautifulSoup(INTRO, "html.parser"))
    archive.append(BeautifulSoup(
        f'<div class="msec archive-msec" id="{MARK_ID}"><div class="msec-l">旧セットアップ（参考）'
        '<span class="msec-en">Former setups</span></div>'
        '<div class="msec-q">新ルールでは検証していないセットアップ。Setupsタブから移しました。表示のみ</div></div>',
        "html.parser"))
    for node in moved:
        if "msec" in (node.get("class") or []):
            _set_number(node, None)
            classes = node.get("class") or []
            node["class"] = classes + ["archive-sub"]
        archive.append(node)
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


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
