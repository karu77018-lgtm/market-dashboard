from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from theme_gate import CARD_ID, apply, card_html, evaluate  # noqa: E402


def _frame(n_days: int = 320) -> tuple[pd.DataFrame, list[dict]]:
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows, members = [], []
    rng = np.random.default_rng(0)
    # Hot theme: 6 stocks, flat for 200 days then +60% over the last 63 sessions.
    for k in range(6):
        t = f"HOT{k}"
        path = np.r_[np.ones(n_days - 63), np.linspace(1.0, 1.6 + 0.02 * k, 63)]
        members.append({"ticker": t, "theme_name": "テスト急騰"})
        for d, p in zip(dates, path * 50):
            rows.append((t, d, p, p * 1.01, p * 0.99, p, 1e6))
    # Background: 60 drifting stocks in a flat theme.
    for k in range(60):
        t = f"BG{k}"
        path = np.cumprod(1 + rng.normal(0, 0.01, n_days))
        members.append({"ticker": t, "theme_name": "テスト横ばい"})
        for d, p in zip(dates, path * 30):
            rows.append((t, d, p, p * 1.01, p * 0.99, p, 1e6))
    frame = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    return frame, members


def test_hot_theme_passes_and_flat_theme_is_hidden():
    frame, members = _frame()
    result = evaluate(frame, members)
    names = {t["theme"]: t for t in result["themes"]}
    assert names["テスト急騰"]["status"] == "合格"
    assert names["テスト急騰"]["leaders"] >= 3
    assert "テスト横ばい" not in names


def test_card_is_inserted_before_theme_thermometer_once(tmp_path):
    frame, members = _frame()
    path = tmp_path / "theme_membership.json"
    path.write_text(json.dumps({"rows": members}, ensure_ascii=False), encoding="utf-8")
    page = ('<html><head></head><body><div class="card"><div class="chd"><h2>テーマETFの温度計（重複あり）'
            '</h2></div></div></body></html>')
    out = apply(page, frame, path)
    assert out.count(f'id="{CARD_ID}"') == 1
    assert out.index(CARD_ID) < out.index("テーマETFの温度計")
    assert apply(out, frame, path) == out  # idempotent
    assert apply(page, frame, tmp_path / "missing.json") == page  # graceful without membership


def test_card_handles_no_qualifying_theme():
    html = card_html({"session": "2026-09-30", "themes": []})
    assert "合格・監視テーマなし" in html
