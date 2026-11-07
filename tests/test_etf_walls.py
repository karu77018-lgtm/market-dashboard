import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import etf_walls as ew  # noqa: E402


def _opt(kind, strike, oi, iv=0.6, exp="261218"):
    return {"option": f"SOXL{exp}{kind}{int(strike * 1000):08d}", "open_interest": oi, "iv": iv}


def _payload(close, high, low):
    opts = [_opt("C", 60, 9000), _opt("C", 55, 1000), _opt("P", 40, 8000), _opt("P", 45, 900)]
    return {"timestamp": "2026-11-07 02:31:53",
            "data": {"close": close, "high": high, "low": low, "iv30": 160.0, "options": opts}}


def test_snapshot_has_walls_and_prices():
    s = ew.snapshot(_payload(50.0, 52.0, 48.0), "SOXL", "2026-11-06")
    assert s["close"] == 50.0 and s["high"] == 52.0 and s["iv30"] == 160.0
    assert s["cw"] and s["cw"] >= 50 and s["pw"] and s["pw"] <= 50


def test_forward_fills_after_enough_sessions(tmp_path):
    led = ew.load_ledger(tmp_path)
    closes = [50, 51, 53, 49, 47, 52, 61]
    for i, c in enumerate(closes):
        snap = ew.snapshot(_payload(c, c + 1, c - 1), "SOXL", f"2026-11-{10 + i:02d}")
        led = ew.record(led, f"2026-11-{10 + i:02d}", {"SOXL": snap})
    led = ew.forward(led)
    first = led["days"]["2026-11-10"]["SOXL"]
    f5 = first["fwd"]["5"]
    assert f5["end"] == "2026-11-15"
    assert abs(f5["ret"] - (52 / 50 - 1)) < 1e-9
    assert f5["max_up"] == round(54 / 50 - 1, 5) and f5["max_dn"] == round(46 / 50 - 1, 5)
    assert "20" not in first["fwd"]
    assert "5" not in led["days"]["2026-11-12"]["SOXL"].get("fwd", {})


def test_run_records_and_survives_fetch_failure(tmp_path):
    def fake(t):
        return None if t == "QQQ" else _payload(50.0, 51.0, 49.0)
    snaps = ew.run(tmp_path, "2026-11-06", fetch=fake)
    assert set(snaps) == {"SOXL", "TQQQ"}
    led = ew.load_ledger(tmp_path)
    assert set(led["days"]["2026-11-06"]) == {"SOXL", "TQQQ"}
