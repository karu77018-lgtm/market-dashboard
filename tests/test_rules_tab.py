from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rules_tab  # noqa: E402

PAGE = ('<html><head></head><body><section id="t-post1">x</section>'
        '<section id="t-rules"><div class="card"><h2>Core 12 システムルール（v2・確定）</h2></div></section>'
        '<section id="t-jev">j</section></body></html>')


def test_rules_tab_replaces_core12_with_swing_rules():
    out = rules_tab.apply(PAGE, regime={"on": True, "close": 600.0, "ma": 550.0, "date": "2026-10-02"})
    assert "Core 12 システムルール" not in out
    assert "スイングルール（新ルール）" in out and "週足SARブル" in out
    assert "今日の地合い：新規OK" in out and "QQQ 600.00 / 200日線 550.00" in out
    assert '<section id="t-post1">x</section>' in out and '<section id="t-jev">j</section>' in out
    assert out.count(rules_tab.STYLE) == 1
    assert "成績（単年・旧6銘柄ルールの過去検証）" in out and "+122.2%" in out and "−10.1%" in out and "TQQQ枠込" in out and "9. TQQQルール" in out and "①早期再エントリー" in out and "②信用125%（参考・未採用）" in out and "166倍" in out and "最大5銘柄" in out and "+20%でもう一度同額" in out and "好位置リーダー（検討可）" in out and "7. 余剰資金の配分" in out and "2026*" in out
    assert rules_tab.apply(out, regime={"on": True, "close": 600.0, "ma": 550.0, "date": "2026-10-02"}) == out


def test_rules_tab_regime_off_and_missing():
    off = rules_tab.apply(PAGE, regime={"on": False, "close": 500.0, "ma": 550.0, "date": "d"})
    assert "今日の地合い：新規停止" in off
    assert "今日の地合い：判定不可" in rules_tab.apply(PAGE, regime=None)
    assert rules_tab.rule_problems(rules_tab.apply(PAGE)) == ["mc57-swing-screener: missing"]
    assert rules_tab.apply("<html></html>") == "<html></html>"


def test_active_allocation_uses_shared_constants_and_keeps_historical_research():
    from bs4 import BeautifulSoup
    from swing_allocation import EFFECTIVE_DATE, INITIAL_WEIGHT, MAX_NAMES, RULE_ID

    html = rules_tab.rules_html()
    soup = BeautifulSoup(html, "html.parser")
    trade = soup.find("div", string="4. 売買").find_next_sibling("table")
    rows = {r.select_one("td").get_text(): r.get_text(" ", strip=True)
            for r in trade.select("tr") if r.select_one("td")}
    assert rules_tab.RULE_ID == RULE_ID == "swing-v4-max5-tqqq-sleeve"
    assert MAX_NAMES == 5 and INITIAL_WEIGHT == 0.20
    assert soup.select_one("#rules-card")["data-rule"] == RULE_ID
    assert "通常スイング最大5銘柄" in rows["同時保有"]
    assert "テーマ枠は別枠3銘柄、合計最大8" in rows["同時保有"]
    assert "最初は総資産の20%" in rows["サイズ"]
    assert "初回のリスクは総資産の1.6%" in rows["サイズ"]
    assert "1/6" not in rows["サイズ"] and "16.7%" not in rows["サイズ"]
    assert EFFECTIVE_DATE in html
    assert "通常スイングの5枠に含める" in html
    assert "50%をTQQQルール枠" in rows["余剰資金"] and "100%" in rows["余剰資金"]
    assert "買値−8%" in rows["損切り"]
    assert "+10%で同額、+20%でもう一度同額" in rows["買い増し"]
    assert "資金の40%" in rows["買い増し"]
    assert "安値21EMA" in rows["手仕舞い"]
    assert "旧6銘柄・初回1/6の過去検証" in html
    assert "現行の最大5銘柄・初回20%の成績ではありません" in html
    assert "TQQQルール枠（現行）" not in html
    assert "年率57.0%" not in html
    assert rules_tab.YEARLY[0] == (2015, 2.8, 9.4, 3.1, 8.7, -6.1)
    assert rules_tab.YEARLY[-1] == (2026, 75.8, 79.8, 100.5, 16.7, -19.2)
    assert [entry[1:] for entry in rules_tab.TOTALS] == [(31.0, -31.4, 23), (40.6, -31.6, 53), (55.1, -33.8, 166)]


def test_rule_version_rejects_previous_six_name_cards():
    html = rules_tab.rules_html() + '<div id="mc57-swing-screener" data-rule="swing-v3.1-tqqq-sleeve"></div>'
    assert rules_tab.rule_problems(html) == [
        "mc57-swing-screener: rule 'swing-v3.1-tqqq-sleeve' != 'swing-v4-max5-tqqq-sleeve'"]


def test_archive_intro_marks_six_name_results_historical():
    import archive_tab

    assert archive_tab.INTRO_MARK in archive_tab.INTRO
    assert "現行の通常スイングは最大5銘柄・初回は総資産の20%" in archive_tab.INTRO
    assert "現行5銘柄の成績ではありません" in archive_tab.INTRO
    assert "旧6銘柄ルールの過去検証" in archive_tab.INTRO
    assert "<b>現行</b>（最大6銘柄" not in archive_tab.INTRO
    assert "年率55.1%・最大下落−33.8%" in archive_tab.INTRO
    assert archive_tab.INTRO_MARK != "年率55.1%"
