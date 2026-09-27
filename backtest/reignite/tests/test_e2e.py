"""Full pipeline on a synthetic cache laid out exactly like data.py writes it."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import data  # noqa: E402
import run  # noqa: E402


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def test_backtest_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CACHE", tmp_path)
    monkeypatch.setattr(run, "CACHE", tmp_path)
    monkeypatch.setattr(run, "OUTPUT", tmp_path / "out")
    monkeypatch.setitem(config.PERIODS, "dev", ("2025-02-03", "2025-02-07"))
    monkeypatch.setattr(run, "EARLIEST", "2025-01-01")

    days = pd.bdate_range("2025-01-01", "2025-02-07").strftime("%Y-%m-%d").tolist()
    for k, d in enumerate(days):
        rows = [("SPY", 600 + k, 1e8), ("IWM", 220 - k * 0.1, 3e7), ("QUIET", 5.0, 1e6)]
        # RUNR: +60% on 02-04 -> on the 2日目 list for 02-05
        rows.append(("RUNR", 3.2 if d >= "2025-02-04" else 2.0, 5e7 if d == "2025-02-04" else 1e6))
        df = pd.DataFrame([{"ticker": t, "o": c, "h": c, "l": c, "c": c, "v": v, "vw": c} for t, c, v in rows])
        _write(df, data.daily_path(d))
    _write(pd.DataFrame({"ticker": ["RUNR", "QUIET"], "type": "CS", "active": True, "delisted": None}),
           tmp_path / "ref" / "tickers.parquet")
    _write(pd.DataFrame(columns=["ticker", "date", "split_from", "split_to"]), tmp_path / "ref" / "splits.parquet")

    bars = [{"m": m, "o": 3.2, "h": 3.2, "l": 3.2, "c": 3.2, "v": 20_000, "vw": 3.2} for m in range(570, 600)]
    bars.append({"m": 600, "o": 3.2, "h": 3.35, "l": 3.2, "c": 3.33, "v": 300_000, "vw": 3.3})  # 10:00 fire
    bars.append({"m": 601, "o": 3.34, "h": 3.4, "l": 3.34, "c": 3.4, "v": 50_000, "vw": 3.37})  # fill
    bars.append({"m": 610, "o": 3.4, "h": 3.9, "l": 3.4, "c": 3.85, "v": 50_000, "vw": 3.7})    # all TPs
    _write(pd.DataFrame(bars), data.minute_path("RUNR", "2025-02-05"))
    for d in ("2025-02-06", "2025-02-07"):
        _write(pd.DataFrame(columns=data.MINUTE_COLS), data.minute_path("RUNR", d))

    run.backtest("dev", open_holdout=False)

    out = tmp_path / "out" / "dev"
    trades = pd.read_csv(out / "trades.csv")
    watch = pd.read_csv(out / "watchlist.csv")
    assert set(watch.loc[watch["date"] == "2025-02-05", "ticker"]) == {"RUNR"}
    main = trades[(trades["floor"] == "$30K per 10min") & (~trades["from_open"]) & (trades["slippage"] == 0.01)]
    assert len(main) == 1 and main["pnl"].iat[0] > 0 and main["net"].iat[0] == "2日目"
    # literal $30K/sec floor needs $1.8M/min of baseline turnover -> no trade here
    assert trades[trades["floor"] == "literal $30K/sec"].empty
    summary = (out / "summary.md").read_text()
    assert "## 5. 本番とのズレ" in summary and (out / "monthly_0.png").exists()


def test_holdout_is_sealed(monkeypatch):
    import pytest
    with pytest.raises(SystemExit):
        run.backtest("holdout", open_holdout=False)
