import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prediction_log as pl  # noqa: E402
import display_health as dh  # noqa: E402
import render_jev_ranking as rj  # noqa: E402

PAGE = ('<html><head><title>x</title></head><body><header>h</header>'
        '<div class="card pc-card" id="phase-check">P<span class="pc-end"></span></div><div class="card">next</div></body></html>')


def _market(path, sym="QQQ"):
    d = pd.bdate_range("2025-01-01", periods=len(path))
    return {"series": {sym: [{"date": str(x.date()), "close": float(c)} for x, c in zip(d, path)]}}, [str(x.date()) for x in d]


def test_records_once_and_resolves():
    up = [100.0] * 260
    path = up + [85.0, 89.5, 90.0, 99.0]           # low 85, back within 2% of 100 on the last day
    mk, days = _market(path)
    entry = {"id": "up5-QQQ-x", "kind": "up5", "sym": "QQQ", "event": days[261], "prob": 42, "basis": "b", "low": 85.0,
             "recorded": days[261], "outcome": None, "resolved": None}
    log = {"schema": "prediction-log.1", "entries": [dict(entry)]}
    pl.resolve(log["entries"], mk)
    assert log["entries"][0]["outcome"] == 1 and log["entries"][0]["resolved"] == days[-1]
    fail = dict(entry, id="b")
    mk2, _ = _market(up + [85.0, 89.5, 84.0])
    pl.resolve([fail], mk2)
    assert fail["outcome"] == 0
    ftd = {"id": "ftd-QQQ-x", "kind": "ftd", "sym": "QQQ", "event": days[261], "prob": 70, "low": 89.0, "outcome": None}
    pl.resolve([ftd], mk)
    assert ftd["outcome"] is None                   # not broken, fewer than 25 sessions: still open
    sm = pl.summary(log)
    assert sm["n"] == 1 and sm["pred"] == 42 and sm["hit"] == 100


def test_candidates_are_fixed_the_first_time():
    phase = json.loads((ROOT / "seed/phase-check-state.json").read_text(encoding="utf-8"))
    ftd = json.loads((ROOT / "seed/ftd-check-state.json").read_text(encoding="utf-8"))
    log = pl.update({"entries": []}, phase, ftd, "2026-11-16", None)
    n = len(log["entries"])
    for e in log["entries"]:
        e["prob"] = -1                               # a later run must not overwrite a recorded number
    log = pl.update(log, phase, ftd, "2026-11-17", None)
    assert len(log["entries"]) == n and all(e["prob"] == -1 for e in log["entries"])


def test_card_after_phase_card_and_out_of_jev_hash():
    log = json.loads((ROOT / pl.LOG).read_text(encoding="utf-8"))
    out = pl.apply(PAGE, log)
    assert out.index('id="phase-check"') < out.index('id="prediction-log"') < out.index("next")
    assert pl.apply(out, log) == out and "予測の答え合わせ" in out
    assert rj.source_hash(out) == rj.source_hash(PAGE)


def test_display_health_notice(tmp_path):
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "2026-11-17"}), encoding="utf-8")
    out = dh.apply(PAGE, tmp_path)
    assert 'id="display-health"' in out and "局面チェック（表示なし）" in out and dh.apply(out, tmp_path) == out
    assert rj.source_hash(out) == rj.source_hash(PAGE)
    from bs4 import BeautifulSoup
    assert dh.apply(str(BeautifulSoup(out, "html.parser")), tmp_path).count('id="display-health"') == 1
