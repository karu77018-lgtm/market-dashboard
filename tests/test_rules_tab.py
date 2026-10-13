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
    assert "成績（単年）" in out and "+141.7%" in out and "−15.4%" in out and "TQQQ枠込" in out and "9. TQQQルール" in out and "①早期再エントリー" in out and "②信用125%（参考・未採用）" in out and "169倍" in out and "最大6銘柄" in out and "+20%でもう一度同額" in out and "好位置リーダー（検討可）" in out and "7. 余剰資金の配分" in out and "2026*" in out
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
    assert rules_tab.RULE_ID == RULE_ID == "swing-v6-max6-cap80-sleeve60"
    assert MAX_NAMES == 6 and abs(INITIAL_WEIGHT - 1 / 6) < 1e-12
    assert soup.select_one("#rules-card")["data-rule"] == RULE_ID
    assert "通常スイング最大6銘柄" in rows["同時保有"]
    assert "テーマ枠は別枠3銘柄、合計最大9" in rows["同時保有"]
    assert "最初は総資産の1/6（約16.7%）" in rows["サイズ"]
    assert "初回のリスクは総資産の1.3%" in rows["サイズ"]
    assert "翌営業日の寄り付き" in rows["買い"]
    assert EFFECTIVE_DATE in html
    assert "通常スイングの6枠に含める" in html
    assert "60%をTQQQルール枠" in rows["余剰資金"] and "100%" in rows["余剰資金"]
    assert "個別株の合計は総資産の80%まで" in rows["株の上限"] and "売って減らしはしない" in rows["株の上限"]
    assert "買値−8%" in rows["損切り"]
    assert "翌営業日の寄りで同額、+20%でもう一度同額" in rows["買い増し"]
    assert "資金の40%" in rows["買い増し"]
    assert "安値21EMA" in rows["手仕舞い"] and "翌営業日の寄りで売り" in rows["手仕舞い"]
    assert "最大6銘柄・初回1/6（約16.7%）のルールでの検証" in html and "旧6銘柄" not in html
    assert "TQQQルール枠（現行）" in html and "年率55.3%" in html and "翌営業日の寄りで売買" in html
    assert "年率57.0%" not in html
    assert rules_tab.YEARLY[0] == (2015, 2.8, 10.6, 1.9, 8.7, -6.4)
    assert rules_tab.YEARLY[-1] == (2026, 76.4, 89.1, 113.7, 16.7, -14.9)
    assert [entry[1:] for entry in rules_tab.TOTALS] == [(27.1, -29.5, 16), (38.6, -32.5, 45), (55.3, -35.8, 169)]


def test_rule_version_rejects_previous_six_name_cards():
    html = rules_tab.rules_html() + '<div id="mc57-swing-screener" data-rule="swing-v3.1-tqqq-sleeve"></div>'
    assert rules_tab.rule_problems(html) == [
        "mc57-swing-screener: rule 'swing-v3.1-tqqq-sleeve' != 'swing-v6-max6-cap80-sleeve60'"]


def test_archive_intro_marks_six_name_results_historical():
    import archive_tab

    assert archive_tab.INTRO_MARK in archive_tab.INTRO
    assert "現行の通常スイングは最大6銘柄・初回は総資産の1/6（約16.7%）" in archive_tab.INTRO
    assert "<b>現行</b>（最大6銘柄×1/6" in archive_tab.INTRO and "年率55.3%" in archive_tab.INTRO
    assert "<b>5銘柄×20%</b>" in archive_tab.INTRO and "年率57.0%" not in archive_tab.INTRO
    assert archive_tab.INTRO_MARK != "年率55.1%"
