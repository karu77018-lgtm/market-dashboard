from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from archive_tab import apply  # noqa: E402


def card(title: str, body: str = "", cls: str = "card") -> str:
    return f'<div class="{cls}"><h2>{title}</h2>{body}</div>'


def msec(title: str) -> str:
    return f'<div class="msec"><div class="msec-l">{title}</div><div class="msec-q">q</div></div>'


PAGE = (
    "<html><head></head><body><div class='wrap'><nav>"
    "<a class='tabx' href='#t-market'>Daily</a><a class='tabx' href='#t-alloc'>Positions</a>"
    "<a class='tabx' href='#t-port'>Core 12</a><a class='tabx' href='#t-today'>Setups</a>"
    "<a class='tabx' href='#t-rules'>Rules</a></nav>"
    '<section id="t-market">'
    + card("レジーム警戒灯 Regime", "<p>F3が60%超なら深い下落を想定して裁量スイングの+25%到達玉を⅓利確（Core 12はピーク×0.70トレール維持）。</p>")
    + card("転換初動リーダーボード")
    + '</section><section id="t-alloc">'
    + '<div class="card" id="mc57-swing-screener"><h2>スイング候補（新ルール）</h2></div>'
    + msec("トレード計画・保有記録") + card("スイング・プランナー（R建て）", "<table><tr><td>x</td></tr></table>")
    + msec("① 配分計算") + card("資金配分・株数計算")
    + msec("② リバランス点検") + card("隔週リバランス点検（月曜）")
    + '<div class="card"><div class="sub">この計算機は各銘柄を<b>個別枠÷12</b>で均等配分</div></div>'
    + '<div class="msec"><div class="msec-l">資産推移・口座</div><div class="msec-q">資産曲線・要因分解・非常口ブレーキ</div></div>'
    + card("エクイティ記録") + card("非常口 判定不可", cls="card emergency")
    + '</section><section id="t-port">'
    + card("レジーム警戒灯 Regime", "<p>dup</p>", cls="card reg-card") + card("転換初動リーダーボード")
    + msec("② 現在の構成") + card("個別株スリーブ Core 12", "<div class='core-table-wrap'><table></table></div>")
    + card("テンバガー・レーダー")
    + '</section><section id="t-today">'
    + card("発火前") + msec("⑦ W30ブレイク（30週線）") + card("ブレイク一覧 Signals")
    + card("運用ルール（確定版） Playbook") + card("手仕舞いの目安 Exits")
    + msec("⑧ リーダー母集団") + card("リーダー監視")
    + '</section><section id="t-rules">' + card("スイングルール（新ルール）") + "</section>"
    + "</div><script>function tickerGoPosition(t){goTab('t-alloc');}</script>"
    + "<footer class=\"disc\">f</footer></body></html>"
)


def titles(soup: BeautifulSoup, sid: str) -> list[str]:
    return [h.get_text(" ", strip=True) for h in soup.find(id=sid).find_all("h2")]


def test_core12_and_old_rule_move_to_archive_tab():
    soup = BeautifulSoup(apply(PAGE), "html.parser")
    assert [a.get_text() for a in soup.find("nav").find_all("a")] == [
        "Daily", "Positions", "Setups", "Rules", "アーカイブ"]
    archive = titles(soup, "t-port")
    assert archive[0].startswith("アーカイブ（運用停止）")
    for name in ("個別株スリーブ Core 12", "テンバガー・レーダー", "スイング・プランナー（R建て）",
                 "資金配分・株数計算", "隔週リバランス点検（月曜）", "非常口 判定不可",
                 "ブレイク一覧 Signals", "運用ルール（確定版） Playbook", "手仕舞いの目安 Exits"):
        assert name in archive
    # Daily duplicates are not repeated in the archive; Daily keeps them.
    assert "レジーム警戒灯 Regime" not in archive
    assert "レジーム警戒灯 Regime" in titles(soup, "t-market")
    assert titles(soup, "t-alloc") == ["スイング候補（新ルール）", "エクイティ記録"]
    assert titles(soup, "t-today") == ["発火前", "リーダー監視"]
    text = str(soup)
    assert "W30ブレイク" not in text.split('id="t-port"')[0]
    assert "⑦ リーダー母集団" in text
    assert "Core 12はピーク" not in text and "⅓利確" not in text
    assert "goTab('t-port')" in text and 'id="archive-tab-init"' in text
    assert all("core-table-wrap" in t.parent.get("class", []) for t in soup.find(id="t-port").find_all("table"))


def test_archive_is_idempotent():
    once = apply(PAGE)
    assert apply(once) == once


def test_missing_core12_section_is_a_noop():
    page = PAGE.replace('<section id="t-port">', '<section id="t-other">')
    assert apply(page) == page
