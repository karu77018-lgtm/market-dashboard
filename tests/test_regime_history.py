import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import regime_history as rh  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

CARD = ('<div class="card reg-card"><div class="hdr reg-hd"><h2>レジーム警戒灯</h2></div><div class="reg-body">'
        '<div class="reg-grid"><div class="reg-cell">F1</div></div><div class="note"><p>3灯は足し算しない。</p></div></div></div>'
        '<div class="card"><h2>次</h2></div>')
PAGE = f"<html><head><title>x</title></head><body>{CARD}</body></html>"


def _state(n=60):
    d = pd.bdate_range("2026-01-02", periods=n)
    return {"session": str(d[-1].date()), "dates": [str(x.date()) for x in d],
            "f1": list(np.linspace(0.1, 0.5, n).round(3)), "f2": [0.3] * n, "f3": [0.45] * n,
            "qqq": [500.0 + i for i in range(n)]}


def _panel(n=320, k=80, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    drift = np.linspace(0.0005, 0.003, k)
    close = pd.DataFrame(100 * np.exp(np.cumsum(drift + rng.normal(0, 0.01, (n, k)), axis=0)), index=idx,
                         columns=[f"T{i}" for i in range(k)])
    return {"Close": close, "High": close * 1.01, "Volume": close * 0 + 1e6}


def test_series_follow_the_card_definitions():
    s = rh.series(_panel()).dropna()
    assert len(s) > 50 and ((s >= 0) & (s <= 1)).all().all()
    W = _panel()
    W["Close"].iloc[-10:, -20:] *= 0.5          # the strongest names collapse: leaders drop out, F1 jumps
    W["High"] = W["Close"] * 1.01
    t = rh.series(W)
    assert t["f1"].iloc[-1] > s["f1"].iloc[-1] and t["f3"].iloc[-1] >= s["f3"].iloc[-1]
    st = rh.build_state(_panel(), {"series": {"QQQ": [{"date": "2026-03-02", "close": 1.0}]}})
    assert len(st["dates"]) == len(st["f1"]) == len(st["qqq"]) and st["session"] == st["dates"][-1]


def test_panel_reads_the_refresh_csv(tmp_path):
    rows = [{"ticker": "aa", "date": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "is_complete": True},
            {"ticker": "AA", "date": "2026-01-05", "open": 1, "high": 2, "low": 1, "close": 1.6, "volume": 10, "is_complete": False}]
    p = tmp_path / "ohlcv.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    W = rh.panel(p, "2026-01-05")
    assert list(W["Close"].columns) == ["AA"] and len(W["Close"]) == 1


def test_block_sits_in_the_card_before_the_notes_and_is_stable():
    st = _state()
    out = rh.apply(PAGE, st)
    assert out.index('class="reg-grid"') < out.index('id="reg-history"') < out.index('<div class="note">')
    assert rh.apply(out, st) == out and out.count(rh.STYLE_ID) == 1 and rh.embedded_state(out) == st
    soup = str(BeautifulSoup(out, "html.parser"))
    assert rh.BLOCK_RE.search(soup) and rh.embedded_state(soup) == st                    # survives a bs4 rewrite
    assert rh.BLOCK_RE.search(rh.apply(soup, st)).group(0) == rh.BLOCK_RE.search(out).group(0)
    assert "F1〜F3の推移" in out and "<polyline" in out and "50%" not in rh.BLOCK_RE.search(out).group(0).split("</svg>")[1][:200]
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    assert rh.apply("<html><body>none</body></html>", st) == "<html><body>none</body></html>"


def test_display_path_and_refresh_fallback(tmp_path):
    st = _state()
    (tmp_path / "seed").mkdir()
    (tmp_path / rh.STATE_SEED).write_text(json.dumps(st), encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "1999-01-04"}), encoding="utf-8")
    assert rh.rerender(PAGE, tmp_path) == PAGE
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": st["session"]}), encoding="utf-8")
    assert rh.BLOCK_ID in rh.rerender(PAGE, tmp_path)
    assert rh.run(PAGE, tmp_path, tmp_path / "missing.csv", st["session"]).count(f'id="{rh.BLOCK_ID}"') == 1
