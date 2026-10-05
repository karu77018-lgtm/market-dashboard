from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import session_check as sc  # noqa: E402


def setup(tmp_path: Path, aapl_open=635.95) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "latest-manifest.json").write_text(json.dumps({"session_date": "2026-10-02"}))
    (tmp_path / "work" / "ohlcv.csv").write_text(
        "ticker,date,open,high,low,close,volume\n"
        f"AAPL,2026-10-02,{aapl_open},1,1,633.91,1\nMSFT,2026-10-02,500,1,1,505,1\n"
        "NVDA,2026-10-01,190,1,1,191,1\nNVDA,2026-10-02,192,1,1,193,1\nXYZ,2026-10-02,1,1,1,1,1\n")
    (tmp_path / "data" / "market_inputs.json").write_text(json.dumps({"series": {
        "SPY": [{"date": "2026-10-02", "open": 770.58, "close": 769.64}], "QQQ": []}}))


REF = {"AAPL": {"open": 635.95, "close": 633.91}, "MSFT": {"open": 500.2, "close": 505.0},
       "NVDA": {"open": 192.0, "close": 193.0}, "SPY": {"open": 770.58, "close": 769.64}}


def test_reads_our_session_bars_only(tmp_path):
    setup(tmp_path)
    mine = sc.ours(tmp_path, "2026-10-02")
    assert sorted(mine) == ["AAPL", "MSFT", "NVDA", "SPY"] and mine["NVDA"] == {"open": 192.0, "close": 193.0}


def test_pass_fail_and_unverified():
    mine = {t: dict(v) for t, v in REF.items()}
    assert sc.compare(mine, REF)["status"] == "PASS"
    mine["AAPL"]["open"] = 622.48  # a pre-market price folded into the daily open
    res = sc.compare(mine, REF)
    assert res["status"] == "FAIL" and res["mismatch"] == ["AAPL"]
    assert sc.compare(mine, {"MSFT": REF["MSFT"]})["status"] == "UNVERIFIED"  # outage: too few to judge


def test_main_stops_publication_on_mismatch_and_not_on_outage(tmp_path, monkeypatch):
    setup(tmp_path, aapl_open=622.48)
    monkeypatch.setattr(sys, "argv", ["session_check.py", "--root", str(tmp_path)])
    monkeypatch.setenv("MASSIVE_API_KEY", "x")
    monkeypatch.setattr(sc, "official", lambda tickers, session, key: REF)
    assert sc.main() == 1
    assert json.loads((tmp_path / "data" / "session-check.json").read_text())["status"] == "FAIL"
    monkeypatch.setattr(sc, "official", lambda tickers, session, key: {})
    assert sc.main() == 0
    monkeypatch.delenv("MASSIVE_API_KEY")
    assert sc.main() == 0
