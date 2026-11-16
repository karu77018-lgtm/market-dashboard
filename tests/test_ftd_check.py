import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ftd_check as fc  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

CARD = ('<div class="card"><h2>フォロースルー・デイ <span class="h2en">FTD (proxy)</span></h2><div class="sub">前提</div>'
        '<div class="ftd-row"><span class="ftd-x">NASDAQ100</span><span class="warnt">FTD無効</span><div class="dddays">割れ</div></div>'
        '<div class="ftd-row"><span class="ftd-x">S&amp;P500</span><span class="warnt">試行</span><div class="dddays">割れ</div></div>'
        '</div><div class="card mh-card"><h2>次</h2></div>')
PAGE = f"<html><head><title>x</title></head><body>{CARD}</body></html>"


def _bars(tail: list[tuple[float, float, float]]) -> pd.DataFrame:
    """300 rising sessions, a 15% slide, then ``tail`` = (close, low, volume) rows."""
    up = list(100 * 1.002 ** np.arange(300))
    down = list(up[-1] * np.linspace(1, 0.85, 16)[1:])
    closes = up + down
    rows = [(c, c * 0.995, 1000.0) for c in closes] + tail
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    return pd.DataFrame({"close": [r[0] for r in rows], "low": [r[1] for r in rows], "volume": [r[2] for r in rows]}, index=idx)


def _rally(after: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Day1..Day3 small gains, Day4 +2% on higher volume (the FTD), then ``after``."""
    base = 100 * 1.002 ** 299 * 0.85
    d = [(base * 1.003, base * 1.0, 900.0), (base * 1.006, base * 1.002, 900.0), (base * 1.009, base * 1.005, 900.0)]
    ftd = (base * 1.009 * 1.02, base * 1.012, 1200.0)
    return d + [ftd] + after


def test_events_follow_the_card_rules():
    df = _bars(_rally([]))
    ev = fc.events(df)
    assert len(ev) == 1 and ev[0]["day"] == 4 and ev[0]["end"] is None
    assert round(ev[0]["pct"], 4) == 0.02
    low = ev[0]["low"]
    broken = _bars(_rally([(low * 0.99, low * 0.98, 1500.0)]))
    e = fc.events(broken)[0]
    assert e["end"] == len(broken) - 1 and e["why"] == "low"
    quiet = _bars(_rally([])[:3] + [(_rally([])[3][0], _rally([])[3][1], 800.0)])   # +2% on lower volume: no FTD
    assert fc.events(quiet) == []


def test_odds_follow_what_is_known():
    df = _bars(_rally([]))
    r = fc.check(df)
    assert r["day"] == 4 and r["risky"] and r["age"] == 0 and fc.odds(r)[0] == 70
    c = r["close"]
    up = fc.check(_bars(_rally([(c * 1.004, c * 0.999, 1100.0)])))
    assert up["next_down"] is False and fc.odds(up)[0] == fc.NEXT_DAY[(True, False)]
    down = fc.check(_bars(_rally([(c * 0.997, c * 0.995, 1300.0)])))
    assert down["next_down"] and down["dist"] and fc.odds(down)[0] == 77
    three = fc.check(_bars(_rally([(c * 1.004, c * 0.999, 1100.0), (c * 1.008, c * 1.0, 1000.0), (c * 1.01, c * 1.004, 900.0)])))
    assert three["warnings"] == 0 and fc.odds(three)[0] == 31
    gone = fc.check(_bars(_rally([(r["low"] * 0.99, r["low"] * 0.98, 1500.0)])))
    assert gone["broken"]["after"] == 1 and fc.odds(gone) == (None, "")
    old = fc.check(_bars(_rally([(c * 1.001, c * 1.0, 900.0)] * (fc.WINDOW + 1))))
    assert old is None                                                      # FTD older than the window


def test_block_sits_inside_the_ftd_card_and_is_stable():
    state = json.loads((ROOT / fc.STATE_SEED).read_text(encoding="utf-8"))
    out = fc.apply(PAGE, state)
    assert out.index("S&amp;P500</span>") < out.index('id="ftd-check"') < out.index('<div class="card mh-card">')
    assert fc.apply(out, state) == out and out.count(fc.STYLE_ID) == 1 and fc.embedded_state(out) == state
    soup = str(BeautifulSoup(out, "html.parser"))
    assert fc.BLOCK_RE.search(soup).group(0) == fc.BLOCK_RE.search(out).group(0)
    assert "騙しチェック" in out and "FTD後の入り方" in out and "売買ルールは変えません" in out
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    assert fc.apply("<html><body>no card</body></html>", state) == "<html><body>no card</body></html>"


def test_rows_text():
    live = {"sym": "QQQ", "label": "NASDAQ100", "ftd": {"date": "2026-11-11", "day": 4, "pct": 2.3, "low": 683.56, "close": 690.38,
            "risky": True, "age": 1, "broken": None, "next_down": True, "dist": False, "warnings": None, "bond": -0.4, "usd": 1.0}}
    t = fc.row_html(live)
    assert "騙し 77%" in t and "683.56" in t and "長期債が下落" in t and "ドル高" in t and "fc-hi" in t
    broke = {**live, "ftd": {**live["ftd"], "broken": {"date": "2026-11-13", "after": 2, "why": "low"}}}
    assert ">騙し</span>" in fc.row_html(broke) and "2営業日後" in fc.row_html(broke)
    assert "FTDはありません" in fc.row_html({"sym": "SPY", "label": "S&P500", "ftd": None})


def test_display_path_uses_seed_of_the_same_session_only(tmp_path):
    seed = json.loads((ROOT / fc.STATE_SEED).read_text(encoding="utf-8"))
    (tmp_path / "seed").mkdir()
    (tmp_path / fc.STATE_SEED).write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "1999-01-04"}), encoding="utf-8")
    assert fc.rerender(PAGE, tmp_path) == PAGE
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": seed["session"]}), encoding="utf-8")
    out = fc.rerender(PAGE, tmp_path)
    assert fc.BLOCK_ID in out and fc.rerender(out, tmp_path) == out
