from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import candle_refresh as cr  # noqa: E402
from enhance_source_mc57 import SCRIPT  # noqa: E402


def test_replaces_old_candle_code_and_is_idempotent():
    page = ('<html><head><style id="mc57-candle-style">old</style></head><body>'
            '<script id="mc57-candle-script">var old=1;</script></body></html>')
    out = cr.apply(page)
    assert "var old=1" not in out and "OP上値の壁" in out and out.count('id="mc57-candle-script"') == 1
    assert cr.apply(out) == out
    assert SCRIPT.strip() in out


def test_page_without_candle_code_is_left_alone():
    page = "<html><body>none</body></html>"
    assert cr.apply(page) == page
