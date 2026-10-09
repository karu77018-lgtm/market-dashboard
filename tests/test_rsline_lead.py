from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import rsline_lead as rl  # noqa: E402

DAYS = pd.bdate_range("2025-01-02", periods=300)
N = len(DAYS)
PEAK = N - 24  # the price high (and the old RS line high) is outside the 20-session freshness window


def leader_close(i: int) -> float:
    if i <= PEAK:
        return 20 * (100 / 20) ** (i / PEAK)
    return 100 - 4 * (i - PEAK) / (N - 1 - PEAK)  # drifts to 96 = 4% below the high


def frame(leader_volume: float = 3e5) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for k in range(40):
        t = f"D{k:02d}"
        c = 60 * np.exp(np.cumsum(rng.normal(-0.001, 0.01, N)))
        for i, d in enumerate(DAYS):
            rows.append((t, d, c[i], c[i] * 1.01, c[i] * 0.99, c[i], 1e7))
    for i, d in enumerate(DAYS):
        c = leader_close(i)
        rows.append(("LEAD", d, c, c * 1.005, c * 0.995, c, leader_volume))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def spy(drop_on_last: bool = True) -> pd.Series:
    s = pd.Series(500.0, index=DAYS)
    if drop_on_last:
        s.iloc[-1] = 450.0  # the market falls, the leader holds: RS line at a new high today
    return s


SESSION = DAYS[-1].strftime("%Y-%m-%d")


def test_rs_line_new_high_before_the_price_is_found():
    res = rl.scan(frame(), spy(), SESSION)
    assert [r["t"] for r in res["today"]] == ["LEAD"]
    r = res["today"][0]
    assert r["back"] == 0 and 0.02 < r["off"] <= 0.08 and r["rs189"] >= rl.MIN_RS189
    assert r["dv20"] >= 20e6


def test_no_signal_without_the_rs_line_high_or_without_spy():
    assert rl.scan(frame(), spy(drop_on_last=False), SESSION)["today"] == []
    res = rl.scan(frame(), None, SESSION)
    assert res["rows"] == [] and res["reason"] == "spy_missing"


def test_illiquid_leader_is_not_shown():
    assert rl.scan(frame(leader_volume=1e5), spy(), SESSION)["today"] == []  # $9.6M a day


def test_ledger_records_only_on_regime_on_days(tmp_path):
    res = rl.scan(frame(), spy(), SESSION)
    led = rl.record_and_advance(rl.load_ledger(tmp_path), res, frame(), SESSION, {}, regime_on=False)
    assert led["signals"] == {}
    led = rl.record_and_advance(led, res, frame(), SESSION, {}, regime_on=True)
    assert list(led["signals"]) == [f"{SESSION}:LEAD"]
    assert led["signals"][f"{SESSION}:LEAD"]["status"] == "約定待ち"
    rl.save_ledger(led, tmp_path)
    assert rl.load_ledger(tmp_path)["signals"].keys() == led["signals"].keys()


def setups_page() -> str:
    return ('<html><head></head><body><section id="t-today">'
            '<div class="msec" id="ipo-base-msec"><div class="msec-l">IPOベース</div></div><div class="card">ipo</div>'
            '<div class="msec"><div class="msec-l">② 支えへの接触</div></div><div class="card">b</div>'
            '</section><section id="t-port"></section></body></html>')


def test_section_goes_between_ipo_and_options_and_is_idempotent():
    res = rl.scan(frame(), spy(), SESSION)
    out = rl.apply(setups_page(), res, {"on": True}, None)
    assert out.index("IPOベース") < out.index("RSライン先行") < out.index("支えへの接触")
    assert "LEAD" in out and "地合いOK" in out and "通常スイング枠には入れない" in out
    again = rl.apply(out, res, {"on": True}, None)
    assert again.count(f'id="{rl.CARD_ID}"') == 1 and again.count('id="rsline-lead-style"') == 1
    empty = rl.apply(setups_page(), {"rows": [], "today": []}, {"on": False}, None)
    assert "該当なし" in empty and "地合い停止中" in empty
