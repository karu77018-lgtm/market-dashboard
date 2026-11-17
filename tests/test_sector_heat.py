import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sector_heat as sh  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = ('<html><head><title>x</title></head><body><div class="card" id="mc57-swing-screener"><div>本命</div></div>'
        '<div class="card">next</div></body></html>')


def _frame(n=160):
    days = pd.bdate_range("2026-01-01", periods=n)
    rows = []
    for k in range(60):
        g = 1.004 if k < 20 else (1.0 if k < 40 else 0.996)   # three sectors: rising, flat, falling
        for i, d in enumerate(days):
            px = 100 * g ** i
            rows.append({"ticker": f"T{k}", "date": d, "open": px, "high": px, "low": px, "close": px, "volume": 1e6})
    return pd.DataFrame(rows), days


def test_ranks_log_and_outcomes(tmp_path):
    frame, days = _frame()
    (tmp_path / "seed").mkdir()
    (tmp_path / "track-record").mkdir()
    sectors = {f"T{k}": ("Technology" if k < 20 else ("Energy" if k < 40 else "Utilities")) for k in range(60)}
    (tmp_path / sh.MAP).write_text(json.dumps({"sectors": sectors}), encoding="utf-8")
    s1 = str(days[70].date())
    (tmp_path / "track-record" / "signals.json").write_text(json.dumps({"sessions": {s1: {"best": [{"t": "T1"}, {"t": "T40"}]}}}), encoding="utf-8")
    st = sh.build(frame, tmp_path, s1)
    assert [s["name"] for s in st["sectors"] if s["hot"]] == ["Technology", "Energy"]   # the upper half of the ranks
    assert st["today"] == [{"t": "T1", "sector": "Technology", "hot": True}, {"t": "T40", "sector": "Utilities", "hot": False}]
    log = sh.load_log(tmp_path)
    t1 = next(e for e in log["entries"] if e["t"] == "T1")
    assert t1["r20"] == round((1.004 ** 90 / 1.004 ** 71 - 1) * 100, 2) and t1["r60"] == round((1.004 ** 130 / 1.004 ** 71 - 1) * 100, 2)
    sh.build(frame, tmp_path, s1)
    assert len(sh.load_log(tmp_path)["entries"]) == 2                   # logged once
    out = sh.apply(PAGE, st)
    assert out.index("本命") < out.index('id="sector-heat"') < out.index("next")
    assert sh.apply(out, st) == out and sh.embedded_state(out) == st and "過熱セクター" in out
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    soup = str(BeautifulSoup(out, "html.parser"))
    assert sh.apply(soup, st).count('id="sector-heat"') == 1
