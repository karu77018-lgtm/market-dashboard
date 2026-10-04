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
    assert "成績（単年）" in out and "+145.2%" in out and "−17.4%" in out and "最大6銘柄" in out and "+20%でもう一度同額" in out and "好位置リーダー（検討可）" in out and "7. 余剰資金の配分" in out and "2026*" in out
    assert rules_tab.apply(out, regime={"on": True, "close": 600.0, "ma": 550.0, "date": "2026-10-02"}) == out


def test_rules_tab_regime_off_and_missing():
    off = rules_tab.apply(PAGE, regime={"on": False, "close": 500.0, "ma": 550.0, "date": "d"})
    assert "今日の地合い：新規停止" in off
    assert "今日の地合い：判定不可" in rules_tab.apply(PAGE, regime=None)
    assert rules_tab.rule_problems(rules_tab.apply(PAGE)) == ["mc57-swing-screener: missing"]
    assert rules_tab.apply("<html></html>") == "<html></html>"
