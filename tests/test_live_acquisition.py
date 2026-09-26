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
