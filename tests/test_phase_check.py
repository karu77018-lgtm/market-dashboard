import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase_check as pc  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = ('<html><head><title>x</title></head><body><div class="card"><h2>前</h2></div>'
        '<div class="card da-card" id="decline-anatomy"><div class="chd"><h2>今回の下げの分解</h2></div><span class="da-end"></span></div>'
        '</body></html>')


def _px(path):
    idx = pd.bdate_range("2024-01-01", periods=len(path))
    return pd.DataFrame({"QQQ": path, "SPY": path, "^VIX": [25.0] * len(path)}, index=idx)


def _decline_then(bounce):
    up = list(100 * 1.002 ** np.arange(300))
    down = list(np.linspace(up[-1], up[-1] * 0.8, 20)[1:])   # -20% over 19 sessions
    return up + down + bounce


def test_rally_start_and_signs():
    low = 100 * 1.002 ** 299 * 0.8
    slow_rise = [low * (1 + 0.012 * k) for k in range(1, 6)]           # +1.2% a day: +5% on day 5
    st = pc.qqq_phase(_px(_decline_then(slow_rise)), {})
    assert st["in_decline"] and st["up5"]["days"] == 5 and st["up5"]["signs"] == [False, True, True]
    assert st["up5"]["score"] == 2 and st["up10"] is None
    jump = [low * 1.06]                                                  # +6% in one day
    st = pc.qqq_phase(_px(_decline_then(jump)), {})
    assert st["up5"]["days"] == 1 and st["up5"]["score"] == 0
    broke = [low * 1.06, low * 0.99]                                     # new low: the start is reset and logged
    st = pc.qqq_phase(_px(_decline_then(broke)), {})
    assert st["up5"] is None and st["failed"][-1]["kind"] == "up5" and st["low_close"] == round(low * 0.99, 2)


def test_not_in_decline_and_spy_start():
    path = list(100 * 1.002 ** np.arange(300)) + [100 * 1.002 ** 299 * 0.94]
    px = _px(path)
    q = pc.qqq_phase(px, {})
    assert not q["in_decline"]
    s = pc.spy_phase(px)
    assert s["event"]["status"] == "open" and s["event"]["vix"] == 25.0
    html = pc.card_html({"session": "2025-02-28", "qqq": q, "spy": s})
    assert "下げの初動" in html and "44%" in html and "高値圏・通常" in html


def test_card_text_matches_reference():
    st = json.loads((ROOT / pc.STATE_SEED).read_text(encoding="utf-8"))
    html = pc.card_html(st)
    up5 = st["qqq"]["up5"]
    if up5:
        band = pc._band(up5["score"])
        n, ok = pc.REF_UP5[band][:2]
        assert f"{round(ok / n * 100)}%" in html and f'{up5["score"]}/3' in html
    for ref in (pc.REF_UP5, pc.REF_UP10, pc.REF_DOWN):
        for n, ok, h1, h2 in ref.values():
            assert h1[0] + h2[0] == n and h1[1] + h2[1] == ok
    assert sum(v[0] for v in pc.REF_UP5.values()) == pc.BASE_UP5[0] and sum(v[1] for v in pc.REF_UP5.values()) == pc.BASE_UP5[1]
    assert sum(v[0] for v in pc.REF_UP10.values()) == pc.BASE_UP10[0]
    assert sum(v[0] for v in pc.REF_DOWN.values()) == pc.BASE_DOWN[0] and sum(v[1] for v in pc.REF_DOWN.values()) == pc.BASE_DOWN[1]


def test_card_placement_stability_and_hash(tmp_path):
    st = json.loads((ROOT / pc.STATE_SEED).read_text(encoding="utf-8"))
    out = pc.apply(PAGE, st)
    assert out.index('id="phase-check"') < out.index('id="decline-anatomy"')
    assert pc.apply(out, st) == out and out.count(pc.STYLE_ID) == 1 and pc.embedded_state(out) == st
    soup = str(BeautifulSoup(out, "html.parser"))
    assert pc.embedded_state(soup) == st and pc.CARD_RE.search(pc.apply(soup, st)).group(0) == pc.CARD_RE.search(out).group(0)
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    (tmp_path / "seed").mkdir()
    (tmp_path / pc.STATE_SEED).write_text(json.dumps(st), encoding="utf-8")
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "1999-01-04"}), encoding="utf-8")
    assert pc.rerender(PAGE, tmp_path) == PAGE
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": st["session"]}), encoding="utf-8")
    assert pc.CARD_ID in pc.rerender(PAGE, tmp_path)
    assert pc.apply("<html><body>none</body></html>", st) == "<html><body>none</body></html>"
