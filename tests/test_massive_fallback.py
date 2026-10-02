from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import massive_fallback as mf  # noqa: E402
import refresh_mc57  # noqa: E402
from v38 import live_acquisition as la  # noqa: E402

SESSIONS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-09-01", "2026-09-28")]
TARGET, PREV = SESSIONS[-1], SESSIONS[-2]


def _bar(c: float) -> dict[str, float]:
    return {"o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1e6}


def test_session_calendar_falls_back_to_massive(monkeypatch):
    def yahoo_down(count):
        raise RuntimeError("YFRateLimitError")

    monkeypatch.setattr(refresh_mc57, "_yahoo_completed_sessions", yahoo_down)
    monkeypatch.setattr(refresh_mc57.mf, "massive_completed_sessions", lambda key, count: SESSIONS[-count:])
    refresh_mc57.SUBSTITUTE.clear()
    assert refresh_mc57.recent_completed_sessions(5, "key") == SESSIONS[-5:]
    assert refresh_mc57.SUBSTITUTE["session_calendar"]
    with pytest.raises(RuntimeError):
        refresh_mc57.recent_completed_sessions(5, "")


def test_massive_calendar_respects_completion_cutoff(monkeypatch):
    bars = {d: _bar(100) for d in SESSIONS}
    monkeypatch.setattr(mf, "massive_daily_bars", lambda *a, **k: bars)
    before_close = datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc)  # 15:00 ET
    after_close = datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc)   # 17:00 ET
    assert mf.massive_completed_sessions("k", 5, now_utc=before_close)[-1] == PREV
    assert mf.massive_completed_sessions("k", 5, now_utc=after_close)[-1] == TARGET


def test_stock_ohlcv_fills_target_from_massive_when_yahoo_fails(tmp_path: Path, monkeypatch):
    output = tmp_path / "ohlcv.csv"
    tickers = [f"T{i:02d}" for i in range(20)]
    rows = [{"ticker": t, "date": d, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1,
             "is_complete": True, "split_checked": True, "split_anomaly": False}
            for t in tickers[:19] for d in SESSIONS[:-2]]  # cache ends two sessions back
    pd.DataFrame(rows).to_csv(output, index=False)
    calls = []

    def yahoo_down(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("YFRateLimitError")

    monkeypatch.setattr(refresh_mc57.la, "_download", yahoo_down)
    monkeypatch.setattr(refresh_mc57.time, "sleep", lambda s: None)
    grouped = {d: {t: _bar(11) for t in tickers} for d in SESSIONS[-20:]}
    stats = refresh_mc57.stock_ohlcv(tickers, TARGET, output, chunk_size=5,
                                     massive_grouped=grouped, sessions=SESSIONS[-20:])
    assert stats["target_session_massive_substitute"] == 19
    assert stats["failed_tickers"] == ["T19"]  # no cached history: never built from Massive
    assert stats["yahoo_circuit_open"] is True
    assert len(calls) == 6  # two chunks x three attempts, then Yahoo is skipped
    merged = pd.read_csv(output)
    t0 = merged[merged["ticker"] == "T00"].sort_values("date")
    assert list(t0["date"].tail(2)) == [PREV, TARGET] and t0["close"].iloc[-1] == 11


def test_grouped_rows_refuse_unknown_or_long_gaps():
    grouped = {d: {"AAA": _bar(5)} for d in SESSIONS[-20:]}
    window = SESSIONS[-20:]
    assert mf.ohlcv_rows_from_grouped("AAA", "2026-08-01", TARGET, window, grouped) == []
    assert mf.ohlcv_rows_from_grouped("AAA", SESSIONS[-8], TARGET, window, grouped) == []  # 7 > 5
    assert len(mf.ohlcv_rows_from_grouped("AAA", SESSIONS[-4], TARGET, window, grouped)) == 3


def test_mc57_prices_uses_cache_plus_massive_when_yahoo_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(refresh_mc57, "MC57_ETFS", ["SMH", "QQQE"])
    monkeypatch.setattr(refresh_mc57.yf, "download", lambda **kw: (_ for _ in ()).throw(RuntimeError("rate")))
    monkeypatch.setattr(refresh_mc57.time, "sleep", lambda s: None)
    monkeypatch.setattr(refresh_mc57.la, "fetch_tradingview_current_closes",
                        lambda symbols: (_ for _ in ()).throw(AssertionError("Massive first")))
    cache = tmp_path / "mc57-prices.csv"
    idx = pd.to_datetime(SESSIONS[:-1])
    mf.write_close_cache(cache, pd.DataFrame({"SMH": 590.0, "QQQE": 118.0}, index=idx))
    refresh_mc57.SUBSTITUTE.clear()
    close = refresh_mc57.mc57_prices(TARGET, cache_path=cache, sessions=SESSIONS,
                                     etf_bars=lambda days: {d: {"SMH": _bar(600), "QQQE": _bar(120)} for d in days})
    assert close.at[pd.Timestamp(TARGET), "SMH"] == 600.0
    assert close.at[pd.Timestamp(PREV), "QQQE"] == 118.0
    assert refresh_mc57.SUBSTITUTE["mc57_etfs_massive"] == ["QQQE", "SMH"]
    assert pd.Timestamp(TARGET) in mf.read_close_cache(cache).index


def _cached_market() -> dict:
    series = {s: [{"date": d, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}
                  for d in SESSIONS[:-1]] for s in la.MARKET_SYMBOLS}
    return {"session_date": PREV, "series": series, "symbols": list(la.MARKET_SYMBOLS)}


def test_market_inputs_fallback_completes_required_symbols():
    etf = lambda days: {d: {s: _bar(2.0) for s in la.MARKET_SYMBOLS if s.isalpha()} for d in days}
    tv = lambda symbols, day: {s: {"date": day, "open": 3.0, "high": 3.0, "low": 3.0, "close": 3.0,
                                   "volume": 0.0} for s in symbols}
    out = mf.market_inputs_fallback(_cached_market(), target=TARGET, generated_at="g", sessions=SESSIONS,
                                    etf_bars=etf, tv_bars=tv)
    assert out["series"]["QQQ"][-1] == {"date": TARGET, "open": 2.0, "high": 2.02, "low": 1.98,
                                        "close": 2.0, "volume": 1e6}
    assert out["series"]["NQ=F"][-1]["close"] == 3.0
    assert "^VIX" in out["tradingview_fallback_symbols"] and "Massive代替" in out["source"]
    with pytest.raises(la.LiveAcquisitionError):
        mf.market_inputs_fallback(_cached_market(), target=TARGET, generated_at="g", sessions=SESSIONS,
                                  etf_bars=etf, tv_bars=lambda symbols, day: {})


def test_tradingview_daily_bar_picks_completed_target_bar(monkeypatch):
    # NQ bar for 2026-09-28 starts 2026-09-27 18:00 ET (22:00 UTC); the new bar opened at 18:00 ET on the 28th.
    prev_start = datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc).timestamp()
    cur_start = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc).timestamp()
    payload = {"data": [{"s": "CME_MINI:NQ1!", "d": [cur_start, 9, 9, 9, 9, 1, prev_start, 5, 6, 4, 5.5, 2]}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: Resp(json.dumps(payload).encode()))
    late = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)
    bar = mf.tradingview_daily_bars(["NQ=F"], TARGET, now_utc=late)["NQ=F"]
    assert bar["close"] == 5.5 and bar["date"] == TARGET


def test_page_badge_marks_massive_substitute(tmp_path: Path):
    from enhance_source_mc57 import substitute_badge
    manifest = tmp_path / "latest-manifest.json"
    page = '<body><div class="wrap"><header><h1>x</h1><div class="asof">分析基準日 2026-09-28</div></header>'
    manifest.write_text(json.dumps({"provider_status": {"yahoo_substitute": None}}))
    assert substitute_badge(page, manifest) == page
    manifest.write_text(json.dumps({"provider_status": {"yahoo_substitute": {
        "session_calendar": "Massive", "stock_bars_massive": 3950, "mc57_etfs_massive": ["SMH"]}}}))
    out = substitute_badge(page, manifest)
    assert "Massive代替：営業日判定・個別3,950銘柄・MC57 ETF 1本" in out
    assert substitute_badge(out, manifest) == out
