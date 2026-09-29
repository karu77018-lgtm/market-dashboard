from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from enhance_source_mc57 import STYLE, axis_html  # noqa: E402


def test_breadth_axis_has_visible_date_labels_and_axis_line():
    dates = list(pd.date_range("2024-09-01", periods=505, freq="D"))
    rendered = axis_html(dates)

    assert 'class="dax mc57-breadth-axis"' in rendered
    assert 'aria-label="日付軸"' in rendered
    assert rendered.count("<span>") == 5
    assert "24/9" in rendered
    assert "mc57-breadth-axis{border-top:1px" in STYLE
    assert "font-size:12px" in STYLE
