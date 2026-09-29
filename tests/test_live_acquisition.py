from __future__ import annotations

from v38.live_acquisition import MARKET_SYMBOLS, SECTOR_MARKET_SYMBOLS


EXPECTED_EQUAL_WEIGHT_SECTORS = {
    "RSPT", "RSPF", "RSPN", "RSPD", "RSPM", "RSPC",
    "RSPU", "RSPS", "RSPH", "RSPR", "RSPG",
}


def test_major_sector_etfs_are_in_live_market_route():
    assert set(SECTOR_MARKET_SYMBOLS) == EXPECTED_EQUAL_WEIGHT_SECTORS
    assert EXPECTED_EQUAL_WEIGHT_SECTORS.issubset(set(MARKET_SYMBOLS))
    assert len(MARKET_SYMBOLS) == len(set(MARKET_SYMBOLS))


def test_tradingview_current_market_rows_parse_required_etfs(monkeypatch):
    import json
    from v38 import live_acquisition as la

    payload = {
        "data": [
            {"s": "NASDAQ:QQQ", "d": ["QQQ", 600.0, 605.0, 595.0, 602.0, 50000000]},
            {"s": "NASDAQ:TQQQ", "d": ["TQQQ", 70.0, 72.0, 68.0, 71.0, 90000000]},
            {"s": "AMEX:SPY", "d": ["SPY", 680.0, 684.0, 676.0, 681.0, 70000000]},
        ]
    }

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(la.urllib.request, "urlopen", lambda req, timeout: Response())
    rows = la.fetch_tradingview_current_market_rows(
        ["QQQ", "TQQQ", "SPY"], target_session="2026-09-28"
    )

    assert rows["QQQ"]["date"] == "2026-09-28"
    assert rows["QQQ"]["close"] == 602.0
    assert rows["TQQQ"]["volume"] == 90000000.0
    assert rows["SPY"]["high"] == 684.0


def test_tradingview_current_closes_supports_mc57_etfs(monkeypatch):
    import json
    from v38 import live_acquisition as la

    payload = {
        "data": [
            {"s": "NASDAQ:SMH", "d": ["SMH", "NASDAQ", 600.01]},
            {"s": "CBOE:DRAM", "d": ["DRAM", "CBOE", 59.70]},
            {"s": "NASDAQ:QQQE", "d": ["QQQE", "NASDAQ", 119.96]},
        ]
    }

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(la.urllib.request, "urlopen", lambda req, timeout: Response())
    closes = la.fetch_tradingview_current_closes(["SMH", "DRAM", "QQQE"])

    assert closes == {"SMH": 600.01, "DRAM": 59.70, "QQQE": 119.96}
