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


def test_reading_and_signals():
    st = _state(40)
    st["f1"], st["f2"], st["f3"] = [0.25] * 40, [0.3] * 40, [0.45] * 40
    st["u200"] = [1] * 40
    assert rh.reading(st)[1] == "特別な合図なし"
    calm = {**st, "f1": [0.1] * 40, "f2": [0.1] * 40, "f3": [0.3] * 40}
    assert rh.reading(calm)[0] == "rgr-warn" and all(rh.signals(calm)["calm"])
    wash = {**st, "f3": [0.65] * 40, "u200": [0] * 40}
    assert rh.reading(wash)[1].startswith("荒れ場")
    assert rh.reading({**wash, "u200": [1] * 40})[1] == "F3は高いが200日線の上"
    f3 = [0.45] * 30 + [0.65, 0.62, 0.5, 0.4, 0.33, 0.3, 0.3, 0.3, 0.3, 0.3]
    clear = {**st, "f3": f3}
    sg = rh.signals(clear)
    assert sg["clear_first"].index(True) == 34 and sum(sg["clear_first"]) == 1
    head = rh.reading(clear)[1]
    assert head.startswith("F3の回復の合図") and st["dates"][34][5:7].lstrip("0") in head


def test_action_text_is_revised_even_without_state(tmp_path):
    page = PAGE.replace('<p>3灯は足し算しない。</p>', '<p>3灯は足し算しない。</p><p><b>行動</b>：F2点灯で新規サイズを絞る。</p>')
    out = rh.rerender(page, tmp_path)
    assert "F2点灯で新規サイズを絞る" not in out and rh.ACTION in out and rh.rerender(out, tmp_path) == out
    assert str(BeautifulSoup(out, "html.parser")).count("rgh-act") == 1
    assert rh.revise_action(str(BeautifulSoup(out, "html.parser"))).count("行動") == 1


def test_weekly_long_view(tmp_path):
    st = _state(60)
    st["u200"] = [1] * 60
    wk = rh.weekly_from_daily(st)
    assert len(wk["dates"]) == 13 and wk["dates"][-1] == st["dates"][-1]       # 2026-01-02 is a Friday
    assert abs(wk["f1"][1] - sum(st["f1"][1:6]) / 5) < 1e-3                     # weekly average
    old = {k: v[:3] for k, v in rh.weekly_from_daily(_state(15)).items()}
    old = {**{k: v for k, v in old.items()}, "dates": ["2025-06-06", "2025-06-13", "2025-06-20"], "note": "N"}
    m = rh.merge_weekly(old, st)
    assert m["dates"][:3] == old["dates"] and m["dates"][3:] == wk["dates"] and m["note"] == "N"
    (tmp_path / "seed").mkdir()
    assert rh.save_archive(tmp_path, m) and not rh.save_archive(tmp_path, m) and rh.load_archive(tmp_path) == m
    st["weekly"] = {k: (v * 6)[:72] if isinstance(v, list) else v for k, v in wk.items()}
    out = rh.apply(PAGE, st)
    assert "data-k=\"wa\"" in out and "週足" in out and out.count("class=\"rgh-tab") >= 2 and rh.apply(out, st) == out
    long_old = rh.weekly_from_daily({**_state(400), "u200": [1] * 400})
    (tmp_path / rh.ARCHIVE).unlink()
    rh.save_archive(tmp_path, {**long_old, "dates": [str(pd.Timestamp(d) - pd.Timedelta(days=800))[:10] for d in long_old["dates"]]})
    page_without = rh.apply(PAGE, _state(60))
    assert rh.rerender(page_without, tmp_path).count("data-k=\"wa\"") >= 1   # display path adds the archive
