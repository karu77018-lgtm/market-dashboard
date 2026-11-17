import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fold  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = "<html><head><title>x</title></head><body><div>a</div></body></html>"


def test_ensure_is_idempotent_and_out_of_the_jev_hash():
    out = fold.ensure(PAGE)
    assert out.count(fold.STYLE_ID) == 1 and out.count(fold.SCRIPT_ID) == 1 and fold.ensure(out) == out
    assert out.index(fold.SCRIPT_ID) < out.index("</body>") and out.index(fold.STYLE_ID) < out.index("</head>")
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    soup = str(BeautifulSoup(out, "html.parser"))
    assert fold.ensure(soup).count(fold.STYLE_ID) == 1


def test_blocks_are_closed_details_with_a_summary_line():
    c = fold.card("x", "<h2>T</h2>", "key line", "<p>body</p>")
    s = fold.sub("y", "Sub", "k2", "<p>b</p>")
    for h, fid in ((c, "x"), (s, "y")):
        d = BeautifulSoup(h, "html.parser").find("details")
        assert d["data-fold"] == fid and not d.has_attr("open") and d.find("summary").find(class_="fold-k")
    assert "key line" in c and "<p>body</p>" in c


def test_live_cards_fold():
    import json
    import phase_check as pc
    import ftd_check as fc
    st = json.loads((ROOT / pc.STATE_SEED).read_text(encoding="utf-8"))
    html = pc.card_html(st)
    assert 'data-fold="phase-check"' in html and pc.key_of(st) in html and "本物の底になる率" in pc.key_of(st)
    fs = json.loads((ROOT / fc.STATE_SEED).read_text(encoding="utf-8"))
    assert 'data-fold="ftd-check"' in fc.block_html(fs) and "NASDAQ100" in fc.key_of(fs)
