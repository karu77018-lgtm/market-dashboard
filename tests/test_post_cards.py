import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import post_cards as pq  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = (ROOT / "source-mc57.html").read_text(encoding="utf-8")


def test_cards_are_valid_svg_with_post_text():
    items = pq.cards(PAGE)
    assert [i[1] for i in items] == ["いまの局面", "今回の下げの中身"]
    for name, title, svg, text in items:
        root = ET.fromstring(svg)                                  # well-formed: the phone turns it into a PNG
        assert root.get("viewBox") == "0 0 1600 900" and "xmlns" in svg
        assert "売買の推奨ではありません" in svg and text.startswith("【米国株") and "参考値" in text


def test_block_on_publish_tab_stable_and_out_of_jev_hash():
    mini = '<html><head></head><body><div class="tab" id="t-post1"><div class="msec">old</div></div></body></html>'
    # use the real page's states inside a small page
    import re
    states = "".join(re.findall(r'<script id="(?:phase-check|decline-anatomy|reg-history|ftd-check)-state" type="application/json">.*?</script>', PAGE, re.S))
    page = mini.replace("</body>", states + "</body>")
    out = pq.apply(page)
    assert out.index('id="t-post1"') < out.index('id="post-cards"') < out.index("old")
    assert pq.apply(out) == out and out.count(pq.STYLE_ID) == 1
    assert pq.apply(str(BeautifulSoup(out, "html.parser"))).count('id="post-cards"') == 1
    assert rj.source_hash(out) == rj.source_hash(page)
    assert "画像にする" in out and "投稿文をコピー" in out
