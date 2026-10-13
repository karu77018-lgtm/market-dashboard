"""2026-10-13 review fixes: frozen-source wording patches, macro inputs, favicon, stance label."""
from __future__ import annotations

import base64
import lzma
import sys
import tarfile
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_exact_source_mc57_clone as clone  # noqa: E402
import dashboard_fixes  # noqa: E402


def _frozen_source() -> str:
    with tarfile.open(ROOT / "bootstrap/recovery-assets.tar.xz") as tar:
        parts = sorted((m.name for m in tar.getmembers() if ".py.lzma.b85.part" in m.name),
                       key=lambda n: int(n.rsplit("part", 1)[1]))
        raw = "".join(tar.extractfile(p).read().decode().strip() for p in parts)
    return lzma.decompress(base64.b85decode(raw.encode())).decode()


def test_display_patches_match_the_frozen_source_once_and_compile():
    text = _frozen_source()
    for old, new, label in clone.DISPLAY_PATCHES:
        assert text.count(old) == 1, label
        text = text.replace(old, new, 1)
    compile(text, "patched-source", "exec")
    assert 'RS21/63/189すべて85以上 {pulse.get("all3", 0)}' in text
    assert "ftd_up = bool(ftd)" in text and text.count('if ftd_up else') == 2
    clear = text.index('if state == "NO_CORRECTION":')
    assert clear < text.index("rec.update(state=state, st=st, cls=cls)")
    assert text.rindex('state = "NO_CORRECTION"', 0, clear) > text.index('st, cls = "上昇継続中（FTD非対象）", "mut"')
    # the count itself is RS21/63/189 in the frozen source
    assert "(top.rs21>=85)&(top.rs63>=85)&(top.rs189>=85)" in text


def test_macro_inputs_cover_what_the_frozen_source_reads():
    from v38 import live_acquisition as la
    text = _frozen_source()
    start = text.index("MACRO_TICKERS = [")
    block = text[start:text.index("]", start) + 1]
    namespace: dict = {}
    exec(block, namespace)
    wanted = set(namespace["MACRO_TICKERS"]) - {"^VIX", "^VIX3M", "^VXN", "QQQ", "QQQE", "SPY", "RSP", "IWM"}
    assert wanted <= set(la.MARKET_SYMBOLS)
    assert not set(la.MACRO_DIAGNOSTIC_SYMBOLS) & set(la.PRIMARY_MARKET_SYMBOLS)
    assert len(la.MARKET_SYMBOLS) == len(set(la.MARKET_SYMBOLS))


def test_favicon_is_added_once(tmp_path):
    page = "<html><head><title>x</title></head><body></body></html>"
    out = dashboard_fixes.apply(page, tmp_path)
    assert out.count('rel="icon"') == 1
    assert dashboard_fixes.apply(out, tmp_path).count('rel="icon"') == 1


def test_weekly_stance_says_the_target_is_inside_the_sleeve():
    import legacy_archive as la
    soup = BeautifulSoup("<html></html>", "html.parser")
    html = la.stance_html(soup, {"days": {"2026-10-09": {"target": 0.25, "gold": 0.0}}, "last_day": "2026-10-09"})
    assert "枠の中のTQQQ <b>25%</b>" in html and "資産全体の配分は上部のカード" in html
