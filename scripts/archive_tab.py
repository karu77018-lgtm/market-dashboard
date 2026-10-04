"""Archive tab: Core 12 and the old 30-week-line rule, kept for reference only.

Display only.  Operation is the new swing rule alone (Rules tab).  Core 12 and
the old weekly 30WMA breakout rule are not run in parallel, so their cards are
moved out of Daily / Positions / Setups into one "アーカイブ" tab.  No
calculation, data acquisition, MC57, V38 or publication logic changes: existing
nodes are moved (ids kept, so their scripts keep working) and a few sentences
that still described Core 12 as the live system are reworded.

Idempotent: a page that already has the archive is returned unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ARCHIVE_ID = "t-port"          # the former Core 12 section; id kept for its scripts
INTRO_ID = "archive-intro"
TAB_LABEL = "アーカイブ"

# Cards (h2 prefix) moved out of Setups: the old weekly 30WMA rule.
OLD_RULE_CARDS = ("ブレイク一覧", "運用ルール（確定版）", "定義・グレード・格付け", "状態の凡例",
                  "コホート分析", "入り方", "手仕舞いの目安")
OLD_RULE_MSEC = "W30ブレイク"
# Cards / headers moved out of Positions: Core 12 sizing, rebalance and leverage tools.
CORE_TOOL_CARDS = ("スイング・プランナー", "資金配分・株数計算", "隔週リバランス点検")
CORE_TOOL_MSECS = ("トレード計画・保有記録", "配分計算", "リバランス点検")
CORE_TOOL_TEXT = ("個別枠÷12",)
# Core 12 tab cards that are exact duplicates of Daily cards.
DAILY_DUPLICATES = ("レジーム警戒灯", "転換初動リーダーボード")

INTRO = (
    f'<div class="card" id="{INTRO_ID}">'
    '<div class="chd"><h2>アーカイブ（運用停止）<span class="h2en">Archive</span></h2></div>'
    '<div class="sub" style="color:#467ed6">運用は<b>新ルールだけ</b>（Rulesタブ・Positionsタブ「スイング候補」）。'
    'Core 12と旧ルール（30週線ブレイク）は並行運用しません。振り返り・比較用に表示だけ残しています。売買には使いません。</div>'
    '<details class="cxpl"><summary>停止の根拠（2015〜2026年の再検証）</summary><div class="cxpl-b">'
    '<b>新ルール</b>（最大6銘柄・余剰資金はQQQ切替）：年率42.4%・最大下落−30.3%・シャープ1.26<br/>'
    '<b>Core 12</b>（売買代金上位10%から選定、個別70%＋TQQQ30%）：年率23.1%・最大下落−40.8%・シャープ0.82<br/>'
    '<b>Core 12の個別株部分だけ</b>：年率15.9%・最大下落−42.2%（QQQを持ち続ける18.2%に届かない）。'
    '候補に小さい銘柄まで含めるとさらに悪化（年率7〜12%・最大下落−52〜−63%）<br/>'
    '理由：RS189上位を機械的に選ぶため旬の投機株を高値でつかみやすく（2021年2月のBNGO・OCGN・WKHSなど）、'
    '−25%損切り・高値から−30%の利益確定では崩れたときの損が大きい。成績の多くはTQQQ部分によるもの。<br/>'
    '<span class="mut">注：NQの赤は「QQQが200日線割れ」で代用。指値で待つ入口の注意は未反映。</span>'
    '</div></details></div>'
)


def _msec(title: str, en: str, note: str) -> str:
    return (f'<div class="msec archive-msec"><div class="msec-l">{title}<span class="msec-en">{en}</span></div>'
            f'<div class="msec-q">{note}</div></div>')


INIT_SCRIPT = (
    '<script id="archive-tab-init">(function(){var o=window.tab;if(typeof o!=="function")return;'
    'window.tab=function(id,btn){o(id,btn);if(id==="t-port"){try{swInit();}catch(e){}'
    'try{hldRender();}catch(e){}}};})();</script>'
)


def _h2(node: Tag) -> str:
    h = node.find("h2") if isinstance(node, Tag) else None
    return h.get_text(" ", strip=True) if h else ""


def _msec_title(node: Tag) -> str:
    label = node.select_one(".msec-l") if isinstance(node, Tag) else None
    return label.get_text(" ", strip=True) if label else ""


def _children(section: Tag) -> list[Tag]:
    return [c for c in section.find_all(recursive=False) if isinstance(c, Tag)]


def _replace_text(root: Tag, old: str, new: str) -> None:
    for node in list(root.find_all(string=re.compile(re.escape(old)))):
        if node.parent and node.parent.name in ("script", "style"):
            continue
        node.replace_with(NavigableString(str(node).replace(old, new)))


def _drop_legend_term(details: Tag, term: str) -> None:
    for b in details.find_all("b"):
        if b.get_text(strip=True) == term:
            nxt = b.next_sibling
            if isinstance(nxt, NavigableString):
                nxt.extract()
            b.decompose()


def apply(text: str) -> str:
    if f'id="{INTRO_ID}"' in text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    archive = soup.find("section", id=ARCHIVE_ID)
    if archive is None:
        return text
    daily = soup.find("section", id="t-market")
    alloc = soup.find("section", id="t-alloc")
    setups = soup.find("section", id="t-today")

    # 1) Core 12 tab body: drop cards that already live in Daily.
    daily_titles = {_h2(c) for c in daily.select(".card")} if daily else set()
    for child in _children(archive):
        title = _h2(child)
        if any(title.startswith(k) for k in DAILY_DUPLICATES) and title in daily_titles:
            child.decompose()
    core_body = _children(archive)
    for child in core_body:
        child.extract()

    # 2) Positions: Core 12 sizing / rebalance / leverage tools.
    tools: list[Tag] = []
    if alloc:
        for child in _children(alloc):
            title, msec = _h2(child), _msec_title(child)
            body = child.get_text(" ", strip=True)
            if (any(title.startswith(k) for k in CORE_TOOL_CARDS)
                    or (msec and any(k in msec for k in CORE_TOOL_MSECS))
                    or (not title and not msec and any(k in body for k in CORE_TOOL_TEXT))
                    or "emergency" in child.get("class", [])):
                tools.append(child.extract())
        _replace_text(alloc, "資産曲線・要因分解・非常口ブレーキ", "資産曲線と記録")

    # 3) Setups: the old weekly 30WMA rule.
    old_rule: list[Tag] = []
    if setups:
        for child in _children(setups):
            title, msec = _h2(child), _msec_title(child)
            if msec and OLD_RULE_MSEC in msec:
                child.decompose()
            elif msec.startswith("⑧ リーダー母集団"):
                _replace_text(child, "⑧ リーダー母集団", "⑦ リーダー母集団")
            elif any(title.startswith(k) for k in OLD_RULE_CARDS):
                old_rule.append(child.extract())

    # 4) Assemble the archive tab.
    parts = [INTRO,
             _msec("Core 12（運用停止）", "Core 12 — archived", "RS上位12銘柄の保有ポート。表示のみ")]
    archive.append(BeautifulSoup("".join(parts), "html.parser"))
    for node in core_body:
        archive.append(node)
    if tools:
        archive.append(BeautifulSoup(_msec("Core 12の運用ツール（運用停止）", "Core 12 tools — archived",
                                           "1銘柄8%の計画・個別枠÷12の配分・隔週リバランス・レバ枠の非常口"), "html.parser"))
        for node in tools:
            archive.append(node)
    if old_rule:
        archive.append(BeautifulSoup(_msec("旧ルール：30週線ブレイク（運用停止）", "Old W30 rule — archived",
                                           "週足で30週線上抜け→S/Aを翌週寄りで買う旧ルール。表示のみ"), "html.parser"))
        for node in old_rule:
            archive.append(node)

    # Same overflow containment as the Core 12 tables (dashboard_fixes) for every
    # table now in the archive, so repeated display runs give the same page.
    for table in archive.find_all("table"):
        if "core-table-wrap" not in (table.parent.get("class") or []):
            table.wrap(soup.new_tag("div", attrs={
                "class": "core-table-wrap",
                "style": "max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch"}))

    # 5) Nav: the Core 12 tab becomes the last tab, "アーカイブ".
    nav = soup.find("nav")
    link = nav.find("a", href=f"#{ARCHIVE_ID}") if nav else None
    if link is not None:
        link.string = TAB_LABEL
        link.extract()
        nav.append(link)

    # 6) Wording elsewhere that still described Core 12 as the live system.
    if daily:
        _replace_text(daily, "して裁量スイングの+25%到達玉を⅓利確（Core 12はピーク×0.70トレール維持）",
                      "する（新ルールでは途中利確・建値ストップはしない。手仕舞いは安値21EMA割れ・損切り−8%のまま）")
        _replace_text(daily, "母数の上位24はポート表の継続境界線までと一致。", "")
    rs = soup.find("section", id="t-rs")
    if rs:
        for badge in rs.select(".rsx-badge.sel, .rsx-badge.watch"):
            badge.decompose()
        for details in rs.select("details.cxpl .cxpl-b"):
            _drop_legend_term(details, "採用")
            _drop_legend_term(details, "監視")
        _replace_text(rs, "個別株スリーブの選定順位に使用する。", "")
        _replace_text(rs, "・保有状態と結合", "と結合")
    weekly = soup.find("section", id="t-weekly")
    if weekly:
        for kv in weekly.select(".kv"):
            key = kv.select_one(".k")
            if key and key.get_text(strip=True) == "次回リバランス":
                kv.decompose()

    # 7) Scripts: planner/holdings now live in the archive tab.
    for script in soup.find_all("script"):
        raw = script.string
        if raw and "function tickerGoPosition(t){goTab('t-alloc');" in raw:
            script.string = raw.replace("function tickerGoPosition(t){goTab('t-alloc');",
                                        "function tickerGoPosition(t){goTab('t-port');")
    soup.body.append(BeautifulSoup(INIT_SCRIPT, "html.parser"))
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--html", default="source-mc57.html")
    a = p.parse_args()
    path = Path(a.html)
    path.write_text(apply(path.read_text(encoding="utf-8")), encoding="utf-8")
