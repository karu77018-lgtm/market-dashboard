from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import rule_refresh  # noqa: E402
import rules_tab  # noqa: E402


def test_remove_div_is_balanced():
    html = '<div id="a"><div id="x"><div>in</div><div>in2</div></div><p>keep</p></div>'
    assert rule_refresh.remove_div(html, "x") == '<div id="a"><p>keep</p></div>'
    assert rule_refresh.remove_div(html, "missing") == html


def test_mixed_rule_versions_refuse_publication_without_saved_inputs(tmp_path: Path):
    old = ('<html><head></head><body><section id="t-alloc"><div class="card" id="mc57-swing-screener">old</div>'
           '</section><section id="t-rules"><div class="card"><h2>スイングルール</h2>コア10銘柄</div></section></body></html>')
    (tmp_path / "source-mc57.html").write_text(old, encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "2026-10-02"}))
    sys.argv = ["rule_refresh.py", "--root", str(tmp_path)]
    assert rule_refresh.main() == 1
    problems = rules_tab.rule_problems((tmp_path / "source-mc57.html").read_text())
    assert any(p.startswith("mc57-swing-screener") for p in problems)


def test_consistent_page_passes(tmp_path: Path):
    page = ('<html><head></head><body><section id="t-alloc">'
            f'<div class="card" id="mc57-swing-screener" data-rule="{rules_tab.RULE_ID}">x</div></section>'
            f'<section id="t-rules"><div class="card" id="rules-card" data-rule="{rules_tab.RULE_ID}">r</div></section>'
            '</body></html>')
    (tmp_path / "source-mc57.html").write_text(page, encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "2026-10-02"}))
    sys.argv = ["rule_refresh.py", "--root", str(tmp_path)]
    assert rule_refresh.main() == 0
