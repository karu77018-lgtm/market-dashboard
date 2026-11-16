import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import refresh_help as rh  # noqa: E402
import render_jev_ranking as rj  # noqa: E402
import decline_anatomy as da  # noqa: E402

PAGE = ('<html><head><title>x</title></head><body><div class="wrap"><header><h1>Command Center</h1>'
        '<div class="asof">分析基準日 2026-11-25</div></header><div id="tqqq-rule-card">a</div>'
        "<footer class='disc'>f</footer></div></body></html>")


def test_closes_skip_weekends_and_holidays():
    closes = [datetime.fromtimestamp(t, timezone.utc) for t in rh.closes_after("2026-11-25", 5)]
    days = [c.astimezone(rh.mc.NEW_YORK).date().isoformat() for c in closes]
    assert days == ["2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03"]  # Thanksgiving skipped
    assert closes[0].astimezone(rh.mc.NEW_YORK).hour == 13                                  # early close
    assert len(rh.closes_after("2026-11-25")) == rh.AHEAD


def test_block_under_header_and_idempotent():
    out = rh.apply(PAGE)
    assert out.index("</header>") < out.index('id="refresh-help"') < out.index('id="tqqq-rule-card"')
    assert rh.apply(out) == out and out.count(rh.STYLE_ID) == 1
    assert rh.WORKFLOW_URL in out and "Run workflow" in out and 'data-session="2026-11-25"' in out
    soup = str(BeautifulSoup(out, "html.parser"))
    assert rh.BLOCK_RE.search(soup).group(0) == rh.BLOCK_RE.search(out).group(0)
    assert rh.apply("<html><body>no header</body></html>") == "<html><body>no header</body></html>"


def test_display_blocks_do_not_change_the_jev_page_hash():
    with_blocks = rh.apply(PAGE)
    assert rj.source_hash(with_blocks) == rj.source_hash(PAGE)
    card = da.apply(PAGE.replace("<footer", '<div class="card ch-card"></div><footer'),
                    {"session": "2026-11-25", "index": "QQQ", "active": False, "dd_now": -1.0})
    assert da.CARD_ID in card
    assert rj.source_hash(card) == rj.source_hash(PAGE.replace("<footer", '<div class="card ch-card"></div><footer'))
