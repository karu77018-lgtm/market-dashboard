from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pickup_watch as pw  # noqa: E402


def _frame(n=320, k=40, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    rows = []
    for t in range(k):
        drift = 0.006 if t == 0 else rng.normal(0.0, 0.0005)
        c = 20 * np.exp(np.cumsum(rng.normal(drift, 0.03, n)))
        if t == 0:
            c[:120] = c[120] * np.linspace(0.45, 1.0, 120)  # doubled off its low
        for i, d in enumerate(idx):
            rows.append({"ticker": f"T{t:02d}", "date": d, "open": c[i], "high": c[i] * 1.03,
                         "low": c[i] * 0.97, "close": c[i], "volume": 2e6})
    return pd.DataFrame(rows)


def test_compute_runs_and_card_renders():
    f = _frame()
    res = pw.compute(f, industry_map={f"T{t:02d}": ("A" if t < 20 else "B") for t in range(40)}, regime={"on": True})
    assert res["session"] and isinstance(res["rows"], list)
    for r in res["rows"]:
        assert r["rs21"] >= 85 and r["uplow"] >= 2.0 and r["sar_age"] <= 8
    html = pw.card_html(res)
    assert pw.CARD_ID in html and "拾う枠（監視）" in html and "資金は割り当てない" in html


def test_apply_inserts_once_and_survives_errors():
    page = '<html><head></head><body><section id="t-alloc"><div>x</div></section></body></html>'
    out = pw.apply(page, _frame(), regime={"on": True})
    assert out.count(f'id="{pw.CARD_ID}"') == 1 and "mc57-pickup-watch-style" in out
    assert pw.apply(out, _frame(), regime=None) == out
    assert pw.apply(page, pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])) != "" 
