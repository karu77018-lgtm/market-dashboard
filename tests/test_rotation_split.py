from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rotation_split import apply  # noqa: E402


def card(title: str, attrs: str = "") -> str:
    return f'<div class="card"{attrs}><h2>{title}</h2></div>'


PAGE = (
    "<html><head></head><body><nav><a class='tabx' href='#t-market'>Daily</a>"
    "<a class='tabx' href='#t-rotation'>Rotation</a><a class='tabx' href='#t-movers'>Movers</a></nav>"
    '<section id="t-market"></section><section id="t-rotation">'
    + card("何が指数を支えている？", ' id="market-leadership-summary"')
    + card("サイズ別相対推移 / Market Leadership", ' data-history-key="leadership"')
    + card("GICS11 Rotation Heatmap", ' data-history-key="gics11"')
    + card("Index / Internals Divergence", ' id="index-internals-divergence"')
    + '<div class="msec"><div class="msec-l">① どこに資金が向かっているか</div></div>'
    + card("資金フロー（GICS11＋スタイル）") + card("セクター温度マップ")
    + card("指数と中身の乖離") + card("主導セクター・業種") + card("強い業種の主導株")
    + card("セクターETF強弱") + '<div class="card"><script>var _sg="macro";</script></div>'
    + card("サブテーマ別RS（ユニバース内）") + card("テーマ判定（3条件）", ' id="mc57-theme-gate"')
    + card("テーマETFの温度計（重複あり）") + card("新しいカード")
    + '</section><section id="t-movers"></section><footer class="disc">f</footer></body></html>'
)


def h2s(soup: BeautifulSoup, sid: str) -> list[str]:
    return [h.get_text() for h in soup.find(id=sid).find_all("h2")]


def test_rotation_splits_into_money_flow_and_themes():
    soup = BeautifulSoup(apply(PAGE), "html.parser")
    assert [a.get_text() for a in soup.find("nav").find_all("a")] == ["Daily", "Rotation", "Themes", "Movers"]
    assert h2s(soup, "t-rotation") == [
        "何が指数を支えている？", "サイズ別相対推移 / Market Leadership", "資金フロー（GICS11＋スタイル）",
        "GICS11 Rotation Heatmap", "セクター温度マップ", "指数と中身の乖離", "セクターETF強弱", "新しいカード"]
    assert h2s(soup, "t-themes") == [
        "テーマ判定（3条件）", "主導セクター・業種", "強い業種の主導株",
        "サブテーマ別RS（ユニバース内）", "テーマETFの温度計（重複あり）"]
    rotation = soup.find(id="t-rotation")
    assert rotation.select_one('[data-history-key="gics11"]') is not None
    assert soup.find(id="index-internals-divergence") is None   # Daily keeps its copy
    assert 'var _sg="macro"' in str(rotation)                  # script travels with its table
    assert soup.find(id="t-themes").find_previous_sibling("section")["id"] == "t-rotation"
    assert "① 何が指数を支えているか" in rotation.get_text()


def test_split_is_idempotent_and_noop_without_rotation():
    once = apply(PAGE)
    assert apply(once) == once
    page = PAGE.replace('id="t-rotation"', 'id="t-x"')
    assert apply(page) == page
