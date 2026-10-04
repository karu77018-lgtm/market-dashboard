"""Split the Rotation tab into two tabs by content.  Display only.

Rotation (資金の流れ)  : ETF/index based — what supports the index, which
                        sectors money is moving to, and whether it is broad.
Themes   (業種・テーマ): own-universe stock based — theme gate, leading groups,
                        leaders in strong groups, sub-theme RS, theme ETFs.

Existing nodes are moved (ids and data attributes kept, so their scripts and
the long-history loader keep working).  The Rotation copy of "Index /
Internals Divergence" is dropped because Daily shows the same card.
Idempotent: a page that already has the Themes tab is returned unchanged.
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag

THEMES_ID = "t-themes"
THEMES_LABEL = "Themes"

# Rotation: (section header, English, note, card h2 prefixes in display order)
ROTATION_GROUPS = (
    ("① 何が指数を支えているか", "Market Leadership", "サイズ別・時価総額加重と等ウェイトの差",
     ("何が指数を支えている", "サイズ別相対推移", "Cap Weight vs Equal Weight", "時価総額加重 / 等ウェイト")),
    ("② どこに資金が向かっているか", "Where the Money Is", "GICS11＋スタイルの資金フローとセクター順位",
     ("資金フロー", "GICS11 Rotation Heatmap", "セクター温度マップ")),
    ("③ その資金は広いか、数銘柄か", "Index vs Breadth", "指数（時価総額加重）と中身（等加重）の乖離",
     ("指数と中身の乖離",)),
    ("④ セクター一覧", "Sector ETF Strength", "見出しタップで並べ替え",
     ("セクターETF強弱",)),
)
THEME_GROUPS = (
    ("① 今のテーマ", "Theme Gate", "着火・広がり・過熱でないの3条件",
     ("テーマ判定",)),
    ("② 自ユニバースで主導しているのは誰か", "Leading Groups", "セクター→業種→細目テーマ→銘柄。タップで降りる",
     ("主導セクター・業種",)),
    ("③ その中で買える銘柄はどれか", "Leaders in Strong Groups", "強いグループ×個別も強い＝順張りの一等地",
     ("強い業種の主導株",)),
    ("④ サブテーマ一覧", "Sub-Theme RS", "見出しタップで並べ替え・行タップで構成銘柄",
     ("サブテーマ別RS",)),
    ("⑤ テーマETF（参考）", "Theme ETFs", "相互に重複するためローテーションの測定には使わない",
     ("テーマETFの温度計",)),
)
DROP = ("Index / Internals Divergence",)

INTRO = {
    "t-rotation": "ETF・指数で見る<b>資金の流れ</b>。何が指数を支え、どのセクターへ向かい、それが広いか。"
                  "買う業種・テーマ・銘柄は <b>Themes</b> タブ。",
    THEMES_ID: "自ユニバースの構成銘柄で見る<b>業種・テーマ</b>。テーマ判定→主導業種→その中の主導株の順。"
               "セクター全体の資金の流れは <b>Rotation</b> タブ。",
}

STYLE = ('<style id="themes-tab-style">'
         f'body:has(#{THEMES_ID}:target) nav a.tabx{{background:#ebeae5;color:#5a5850;border-color:#575342}}'
         f'body:has(#{THEMES_ID}:target) nav a[href="#{THEMES_ID}"]{{background:#3774d3;color:#f1f0ef;border-color:#eef3fb}}'
         '</style>')


def _msec(title: str, en: str, note: str) -> str:
    return (f'<div class="msec"><div class="msec-l">{title}<span class="msec-en">{en}</span></div>'
            f'<div class="msec-q">{note}</div></div>')


def _intro(section_id: str) -> str:
    return f'<div class="sub tab-intro" id="{section_id}-intro" style="margin:2px 0 8px">{INTRO[section_id]}</div>'


def _h2(node: Tag) -> str:
    h = node.find("h2")
    return h.get_text(" ", strip=True) if h else ""


def apply(text: str) -> str:
    if f'id="{THEMES_ID}"' in text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    rotation = soup.find("section", id="t-rotation")
    nav = soup.find("nav")
    if rotation is None or nav is None:
        return text

    # Collect cards by title; an untitled block (e.g. the sector table script)
    # travels with the card before it.  Old section headers are discarded.
    cards: list[tuple[str, list[Tag]]] = []
    for child in [c for c in rotation.find_all(recursive=False) if isinstance(c, Tag)]:
        child.extract()
        if "msec" in (child.get("class") or []):
            continue
        title = _h2(child)
        if title or not cards:
            cards.append((title, [child]))
        else:
            cards[-1][1].append(child)

    def take(prefix: str) -> list[Tag]:
        for i, (title, nodes) in enumerate(cards):
            if title.startswith(prefix):
                cards.pop(i)
                return nodes
        return []

    for prefix in DROP:
        take(prefix)

    def fill(section: Tag, groups) -> None:
        section.append(BeautifulSoup(_intro(section["id"]), "html.parser"))
        for title, en, note, prefixes in groups:
            nodes = [n for p in prefixes for n in take(p)]
            if not nodes:
                continue
            section.append(BeautifulSoup(_msec(title, en, note), "html.parser"))
            for node in nodes:
                section.append(node)

    themes = soup.new_tag("section", id=THEMES_ID)
    rotation.insert_after(themes)
    fill(rotation, ROTATION_GROUPS)
    fill(themes, THEME_GROUPS)
    for _, nodes in cards:          # anything unrecognised stays on Rotation
        for node in nodes:
            rotation.append(node)

    link = nav.find("a", href="#t-rotation")
    if link is not None:
        new = soup.new_tag("a", attrs={"class": "tabx", "href": f"#{THEMES_ID}",
                                       "onclick": f"tab('{THEMES_ID}',this);return false;"})
        new.string = THEMES_LABEL
        link.insert_after(new)
    soup.head.append(BeautifulSoup(STYLE, "html.parser"))
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--html", default="source-mc57.html")
    a = p.parse_args()
    path = Path(a.html)
    path.write_text(apply(path.read_text(encoding="utf-8")), encoding="utf-8")
