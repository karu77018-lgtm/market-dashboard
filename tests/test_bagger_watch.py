from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bagger_watch as bw  # noqa: E402

DAYS = pd.bdate_range("2024-06-03", periods=420)
N = len(DAYS)
TOP, LOW = 200, 300  # prior high at bar 200, base low at bar 300 (-50%)


def releader(i: int, end: float) -> float:
    """20 -> 60 (prior run), down to 30, then back up to ``end`` x the prior high."""
    if i <= TOP:
        return 20 * 3 ** (i / TOP)
    if i <= LOW:
        return 60 - 30 * (i - TOP) / (LOW - TOP)
    return 30 + (60 * end - 30) * (i - LOW) / (N - 1 - LOW)


def frame(end: float = 1.003, vol: float = 1e6) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for k in range(40):  # a flat-to-weak crowd so the leader ranks high on RS
        c = 50 * np.exp(np.cumsum(rng.normal(-0.0005, 0.01, N)))
        rows += [(f"D{k:02d}", d, c[i], c[i] * 1.01, c[i] * 0.99, c[i], 1e6) for i, d in enumerate(DAYS)]
    for i, d in enumerate(DAYS):
        c = releader(i, end)
        rows.append(("LEAD", d, c, c * 1.005, c * 0.995, c, vol))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


SESSION = DAYS[-1].strftime("%Y-%m-%d")


def test_breakout_after_a_deep_base_is_found_today():
    res = bw.scan(frame(1.003), SESSION)
    bo = [r for r in res["rows"] if r["kind"] == "breakout"]
    assert [r["t"] for r in bo] == ["LEAD"] and [r["t"] for r in res["today"]] == ["LEAD"]
    r = bo[0]
    assert r["back"] == 0 and 0.45 < r["depth"] < 0.55 and r["rs"] >= bw.BO_RS
    assert abs(r["stop"] - r["peak"] * 0.75) < 1e-9


def test_watch_below_the_high_and_not_shown_when_illiquid():
    res = bw.scan(frame(0.93), SESSION)
    w = [r for r in res["rows"] if r["kind"] == "watch"]
    assert [r["t"] for r in w] == ["LEAD"] and res["today"] == []
    assert 0.05 < w[0]["off"] < 0.10
    assert bw.scan(frame(0.93, vol=2e5), SESSION)["rows"] == []  # about $11M a day


def test_eps_state_from_point_in_time_quarters(monkeypatch, tmp_path):
    def q(start, end, val, filed, form="10-Q"):
        return {"start": start, "end": end, "val": val, "filed": filed, "form": form}
    facts = {"us-gaap:EarningsPerShareDiluted": {"USD/shares": [
        q("2025-01-01", "2025-03-31", -0.20, "2025-05-01"), q("2025-04-01", "2025-06-30", -0.10, "2025-08-01"),
        q("2025-07-01", "2025-09-30", 0.05, "2025-11-01"), q("2025-01-01", "2025-09-30", -0.25, "2025-11-01"),
        q("2025-01-01", "2025-12-31", 0.05, "2026-02-20", "10-K"),
        q("2026-01-01", "2026-03-31", 0.10, "2026-05-01"),
        q("2026-04-01", "2026-06-30", 0.30, "2026-08-01")]}}
    monkeypatch.setattr(bw, "_facts", lambda t, root, cik: facts)
    assert bw.fundamentals("X", "2026-07-15", tmp_path, {})["eps_state"] == "turn"   # Q1: -0.20 -> 0.10
    f = bw.fundamentals("X", "2026-08-15", tmp_path, {})
    assert f["eps_state"] == "turn" and f["eps0"] == 0.30 and f["eps_prev"] == -0.10
    monkeypatch.setattr(bw, "_facts", lambda t, root, cik: None)
    assert bw.fundamentals("X", "2026-08-15", tmp_path, {}) == {"eps_state": "na"}


def test_ledger_follows_the_trailing_stop(tmp_path):
    f = frame(1.003)
    res = bw.scan(f, SESSION)
    led = bw.record_and_advance(bw.load_ledger(tmp_path), res, f, SESSION)
    key = f"{SESSION}:LEAD"
    assert led["signals"][key]["status"] == "保有中"
    later = pd.bdate_range(DAYS[-1] + pd.Timedelta(days=1), periods=3)
    entry = led["signals"][key]["entry"]
    extra = pd.DataFrame([("LEAD", later[0], 0, 0, 0, entry * 1.2, 1e6), ("LEAD", later[1], 0, 0, 0, entry * 0.85, 1e6),
                          ("LEAD", later[2], 0, 0, 0, entry * 0.8, 1e6)],
                         columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    led = bw.record_and_advance(led, {"today": []}, pd.concat([f, extra]), str(later[-1].date()))
    st = led["signals"][key]
    assert st["status"] == "手仕舞い" and st["exit_date"] == str(later[1].date()) and abs(st["ret"] + 0.15) < 1e-6
    bw.save_ledger(led, tmp_path)
    assert bw.ledger_summary(bw.load_ledger(tmp_path))["closed"] == 1


def setups_page() -> str:
    return ('<html><head></head><body><section id="t-today">'
            '<div class="msec" id="rsline-lead-msec"><div class="msec-l">② RSライン先行</div></div><div class="card">r</div>'
            '<div class="msec"><div class="msec-l">③ オプション配置（検証中）</div></div><div class="card">o</div>'
            '</section><section id="t-port"></section></body></html>')


def test_section_goes_before_options_and_is_idempotent():
    res = bw.scan(frame(1.003), SESSION)
    for r in res["rows"]:
        r["eps_state"] = "better"
    out = bw.apply(setups_page(), res, {"on": True}, None)
    assert out.index("RSライン先行") < out.index(bw.TITLE) < out.index("オプション配置")
    assert "LEAD" in out and "EPS改善" in out and "6枠には入れない" in out and bw.RESEARCH in out
    again = bw.apply(out, res, {"on": True}, None)
    assert again.count(f'id="{bw.CARD_ID}"') == 1 and again.count('id="bagger-watch-style"') == 1
    empty = bw.apply(setups_page(), {"rows": [], "today": []}, {"on": False}, None)
    assert "該当なし" in empty and "地合い停止中" in empty
