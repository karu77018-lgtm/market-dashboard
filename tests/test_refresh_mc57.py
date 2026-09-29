from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh_mc57  # noqa: E402


def test_stock_ohlcv_reuses_only_exact_target_session_cache(tmp_path: Path, monkeypatch):
    target = "2026-09-28"
    output = tmp_path / "ohlcv.csv"
    rows = []
    for ticker, close in (("AAA", 10.0), ("BBB", 20.0)):
        rows.append({
            "ticker": ticker, "date": target, "open": close, "high": close,
            "low": close, "close": close, "volume": 1000,
            "is_complete": True, "split_checked": True, "split_anomaly": False,
        })
    pd.DataFrame(rows).to_csv(output, index=False)

    def unexpected_download(*args, **kwargs):
        raise AssertionError("same-session cached tickers should not be downloaded")

    monkeypatch.setattr(refresh_mc57.la, "_download", unexpected_download)
    stats = refresh_mc57.stock_ohlcv(["AAA", "BBB"], target, output, chunk_size=1)

    assert stats["target_session_coverage"] == 1.0
    assert stats["target_session_fresh"] == 0
    assert stats["target_session_same_day_cache"] == 2
    assert stats["failed_tickers"] == []


def test_resolve_refresh_sessions_blocks_provider_regression():
    sessions = [f"2026-09-{day:02d}" for day in range(2, 26)]
    resolved, target, observed = refresh_mc57.resolve_refresh_sessions(
        sessions[-20:], "2026-09-28", count=20
    )

    assert observed == "2026-09-25"
    assert target == "2026-09-28"
    assert resolved[-1] == "2026-09-28"
    assert len(resolved) == 20


def test_mc57_prices_fills_only_missing_current_bar_from_tradingview(monkeypatch):
    target = "2026-09-28"
    dates = pd.to_datetime(["2026-09-25"])

    monkeypatch.setattr(refresh_mc57, "MC57_ETFS", ["SMH", "QQQE"])
    monkeypatch.setattr(
        refresh_mc57.yf,
        "download",
        lambda **kwargs: pd.DataFrame({
            ("Adj Close", "SMH"): [590.0],
            ("Adj Close", "QQQE"): [118.0],
        }, index=dates),
    )
    monkeypatch.setattr(refresh_mc57.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        refresh_mc57.la,
        "fetch_tradingview_current_closes",
        lambda symbols: {"SMH": 600.0, "QQQE": 120.0},
    )

    close = refresh_mc57.mc57_prices(target)

    assert close.at[pd.Timestamp(target), "SMH"] == 600.0
    assert close.at[pd.Timestamp(target), "QQQE"] == 120.0
    assert close.at[pd.Timestamp("2026-09-25"), "SMH"] == 590.0
