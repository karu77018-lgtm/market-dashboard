import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import explain_fold as xf  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = '<html><head></head><body><section id="t-market"><div class="note">x。</div></section></body></html>'


def test_added_once_and_stable():
    out = xf.apply(PAGE)
    assert out.count(xf.STYLE_ID) == 1 and out.count(xf.SCRIPT_ID) == 1
    assert xf.apply(out) == out
    assert xf.apply(str(BeautifulSoup(out, "html.parser"))).count(xf.SCRIPT_ID) == 1
    assert out.index(xf.SCRIPT_ID) > out.index('class="note"')


def test_out_of_jev_hash_and_page_without_body_untouched():
    assert rj.source_hash(xf.apply(PAGE)) == rj.source_hash(PAGE)
    assert xf.apply("<div>x</div>") == "<div>x</div>"


def test_keeps_verdicts_and_rules_visible():
    for k in ("ccrow", "sw-reg", "mkt20-read", "read"):
        assert k in xf.KEEP_CLASSES
    assert "t-rules" in xf.PROSE_OFF and "note" in xf.NOTE_CLASSES
