from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard_fixes import rs_tab_taps  # noqa: E402


def _item(ticker: str, extra: str = "") -> str:
    return (
        f'<div class="rsx-item"{extra}><div class="rsx-row"><span class="rsx-rk">1</span>'
        f'<div class="rsx-name"><div><b>{ticker}</b><span class="rsx-badge ok">適格</span></div>'
        '<small>業種</small></div><div class="rsx-score"><b>99.0</b></div></div></div>'
    )


def test_rs_top10_rows_become_tappable():
    html = (
        '<section id="t-rs"><div class="card rsx-card">'
        + _item("USDE") + _item("BRK.A") + _item("AMD", ' data-tkone="AMD"')
        + _item("not a ticker!")
        + '</div></section>'
        '<section id="t-market">' + _item("ZZZ") + '</section>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert rs_tab_taps(soup) == 2
    items = soup.select("#t-rs .rsx-item")
    assert [item.get("data-tkone") for item in items] == ["USDE", "BRK.A", "AMD", None]
    assert soup.select_one("#t-market .rsx-item").get("data-tkone") is None  # other tabs untouched
    assert rs_tab_taps(soup) == 0  # idempotent


def test_current_dashboard_rs_rows_all_resolve_to_ticker_details():
    path = ROOT / "source-mc57.html"
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rs_tab_taps(soup)
    items = soup.select("#t-rs .rsx-item")
    assert items, "RS tab Top10 rows not found"
    assert all(item.get("data-tkone") for item in items)
