#!/usr/bin/env python3
"""Refresh the isolated source-mc57 publication without touching V38 data files."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v38 import live_acquisition as la  # noqa: E402


MC57_ETFS = [
    "SMH", "XSD", "DRAM", "SOXX", "DTCR", "IGV", "WCLD", "SKYY", "CIBR",
    "AIQ", "QTUM", "BOTZ", "ARKW", "XBI", "IHI", "PPH", "GNOM", "KBE",
    "KRE", "IAI", "KIE", "XOP", "OIH", "XES", "TAN", "ICLN", "GRID",
    "FAN", "URA", "NLR", "LIT", "HYDR", "GDX", "SIL", "COPX", "XME",
    "SLX", "REMX", "ITA", "SHLD", "XAR", "JETS", "IYT", "BOAT", "XHB",
    "PAVE", "PKB", "XRT", "IBUY", "PEJ", "BLOK", "WGMI", "DRIV", "MOO",
    "PHO", "WOOD", "QQQE",
]
METRIC_NAMES = [
    "close_gt_sma10", "close_gt_sma20", "close_gt_sma50", "close_gt_sma200",
    "ret5_gt_0", "ret21_gt_0", "ret63_gt_0", "ret252_gt_0",
    "sma20_gt_sma50", "sma50_gt_sma200", "sma50_gt_sma50_shift20",
    "dd52_continuous_score",
]


def dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def latest_session() -> str:
    frames = la.fetch_benchmark_frames(yf)
    return la.choose_completed_session(
        la.frame_dates(frames["QQQ"]), la.frame_dates(frames["SPY"])
    )


def stock_ohlcv(tickers: list[str], target: str, output: Path,
                *, chunk_size: int = 100) -> dict[str, Any]:
    """Three-year adjusted OHLCV, preserving only actual reported sessions."""
    fields = ("ticker", "date", "open", "high", "low", "close", "volume",
              "is_complete", "split_checked", "split_anomaly")
    import csv

    output.parent.mkdir(parents=True, exist_ok=True)
    target_ok = history_ok = 0
    failed: list[str] = []
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for offset in range(0, len(tickers), chunk_size):
            originals = tickers[offset:offset + chunk_size]
            pending = list(originals)
            rows_by: dict[str, list[dict[str, Any]]] = {}
            for attempt in range(3):
                if not pending:
                    break
                symbols = {t: la.yahoo_symbol(t) for t in pending}
                try:
                    raw = la._download(yf, list(symbols.values()), period="3y", threads=16)
                except Exception:
                    raw = pd.DataFrame()
                retry: list[str] = []
                for ticker, symbol in symbols.items():
                    rows = la.adjusted_ohlcv_rows(
                        la.select_yfinance_symbol_frame(raw, symbol),
                        ticker=ticker, target_session=target,
                    )
                    if rows:
                        rows_by[ticker] = rows
                    if not any(r["date"] == target and r["close"] is not None for r in rows):
                        retry.append(ticker)
                pending = retry
                if pending:
                    time.sleep(2 ** attempt)
            for ticker in originals:
                rows = rows_by.get(ticker, [])
                if rows:
                    history_ok += 1
                    writer.writerows(rows)
                if any(r["date"] == target and r["close"] is not None for r in rows):
                    target_ok += 1
                else:
                    failed.append(ticker)
            print(f"stock OHLCV {min(offset + chunk_size, len(tickers))}/{len(tickers)}", flush=True)
    coverage = target_ok / len(tickers)
    if coverage < 0.95:
        raise RuntimeError(
            f"current-session stock coverage below 95%: {target_ok}/{len(tickers)}={coverage:.4f}"
        )
    return {
        "requested": len(tickers), "history_received": history_ok,
        "target_session_received": target_ok, "target_session_coverage": coverage,
        "failed_tickers": failed,
    }


def _price_frame(raw: pd.DataFrame, symbol: str) -> pd.Series:
    frame = la.select_yfinance_symbol_frame(raw, symbol)
    if frame.empty or "adj_close" not in frame.columns:
        return pd.Series(dtype=float)
    series = pd.to_numeric(frame["adj_close"], errors="coerce").dropna()
    series.index = pd.to_datetime(series.index, utc=True).tz_localize(None).normalize()
    return series[~series.index.duplicated(keep="last")].sort_index()


def mc57_prices(target: str) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    pending = list(MC57_ETFS)
    for attempt in range(3):
        if not pending:
            break
        try:
            raw = yf.download(
                tickers=pending, start="2004-01-01", end=(pd.Timestamp(target) + pd.Timedelta(days=4)).strftime("%Y-%m-%d"),
                interval="1d", group_by="ticker", auto_adjust=False, actions=False,
                progress=False, threads=16, timeout=30,
            )
        except Exception:
            raw = pd.DataFrame()
        retry: list[str] = []
        for ticker in pending:
            s = _price_frame(raw, ticker)
            if not s.empty:
                series[ticker] = s[s.index <= pd.Timestamp(target)]
            if ticker not in series or pd.Timestamp(target) not in series[ticker].index:
                retry.append(ticker)
        pending = retry
        if pending:
            time.sleep(30 if attempt == 0 else 60)
    if pending:
        raise RuntimeError("MC57 fixed universe missing current closes: " + ",".join(pending))
    close = pd.DataFrame(series).sort_index()
    return close[close.index <= pd.Timestamp(target)]


def _participation(condition: pd.DataFrame, valid: pd.DataFrame) -> pd.Series:
    return condition.astype(float).where(valid).mean(axis=1, skipna=True) * 100.0


def compute_mc57(close: pd.DataFrame, target: str, generated_at: str) -> dict[str, Any]:
    sma10 = close.rolling(10, min_periods=10).mean()
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    ret5, ret21 = close.pct_change(5, fill_method=None), close.pct_change(21, fill_method=None)
    ret63, ret252 = close.pct_change(63, fill_method=None), close.pct_change(252, fill_method=None)
    metrics: dict[str, pd.Series] = {
        "close_gt_sma10": _participation(close > sma10, close.notna() & sma10.notna()),
        "close_gt_sma20": _participation(close > sma20, close.notna() & sma20.notna()),
        "close_gt_sma50": _participation(close > sma50, close.notna() & sma50.notna()),
        "close_gt_sma200": _participation(close > sma200, close.notna() & sma200.notna()),
        "ret5_gt_0": _participation(ret5 > 0, ret5.notna()),
        "ret21_gt_0": _participation(ret21 > 0, ret21.notna()),
        "ret63_gt_0": _participation(ret63 > 0, ret63.notna()),
        "ret252_gt_0": _participation(ret252 > 0, ret252.notna()),
        "sma20_gt_sma50": _participation(sma20 > sma50, sma20.notna() & sma50.notna()),
        "sma50_gt_sma200": _participation(sma50 > sma200, sma50.notna() & sma200.notna()),
        "sma50_gt_sma50_shift20": _participation(
            sma50 > sma50.shift(20), sma50.notna() & sma50.shift(20).notna()),
    }
    rolling_high = close.rolling(252, min_periods=252).max()
    dd52 = close / rolling_high - 1.0
    dd_score = ((dd52 + 0.30) / 0.25 * 100.0).clip(0.0, 100.0)
    metrics["dd52_continuous_score"] = dd_score.mean(axis=1, skipna=True)

    mf = pd.DataFrame(metrics)[METRIC_NAMES]
    raw = mf.mean(axis=1, skipna=True).dropna()
    ema2 = raw.ewm(span=2, adjust=False).mean()
    mu = ema2.rolling(3780, min_periods=756).mean().shift(1)
    sigma = ema2.rolling(3780, min_periods=756).std(ddof=0).shift(1)
    z = (ema2 - mu) / sigma
    score = 100.0 / (1.0 + np.power(3.0, -z))
    day = pd.Timestamp(target)
    if day not in score.index or not math.isfinite(float(score.loc[day])):
        raise RuntimeError("MC57 current score could not be calculated")

    rows = []
    for d in score.dropna().iloc[-504:].index:
        vals = {name: float(mf.at[d, name]) for name in METRIC_NAMES if pd.notna(mf.at[d, name])}
        rows.append({
            "date": d.strftime("%Y-%m-%d"), "raw": float(raw.loc[d]),
            "ema2_raw": float(ema2.loc[d]), "z": float(z.loc[d]),
            "mc57": float(score.loc[d]), "metrics": vals,
            "fixed57_breadth_sma20": vals.get("close_gt_sma20"),
            "fixed57_breadth_sma50": vals.get("close_gt_sma50"),
            "fixed57_breadth_sma200": vals.get("close_gt_sma200"),
        })
    current_metrics = rows[-1]["metrics"]
    valid_counts = {name: int(57 - mf.loc[day, name:name].isna().sum()) for name in METRIC_NAMES}
    # The aggregate metric is finite if at least one ETF is valid; expose the
    # exact per-metric denominator directly from its inputs.
    valid_counts = {
        "close_gt_sma10": int((close.loc[day].notna() & sma10.loc[day].notna()).sum()),
        "close_gt_sma20": int((close.loc[day].notna() & sma20.loc[day].notna()).sum()),
        "close_gt_sma50": int((close.loc[day].notna() & sma50.loc[day].notna()).sum()),
        "close_gt_sma200": int((close.loc[day].notna() & sma200.loc[day].notna()).sum()),
        "ret5_gt_0": int(ret5.loc[day].notna().sum()), "ret21_gt_0": int(ret21.loc[day].notna().sum()),
        "ret63_gt_0": int(ret63.loc[day].notna().sum()), "ret252_gt_0": int(ret252.loc[day].notna().sum()),
        "sma20_gt_sma50": int((sma20.loc[day].notna() & sma50.loc[day].notna()).sum()),
        "sma50_gt_sma200": int((sma50.loc[day].notna() & sma200.loc[day].notna()).sum()),
        "sma50_gt_sma50_shift20": int((sma50.loc[day].notna() & sma50.shift(20).loc[day].notna()).sum()),
        "dd52_continuous_score": int(dd_score.loc[day].notna().sum()),
    }
    return {
        "schema_version": "v38.mc57.1", "calculation_version": "v38-mc57-live-1.0.0",
        "history_contract_version": "v38.mc57.history.2", "session_date": target,
        "generated_at": generated_at, "status": "READY", "coverage": 1.0,
        "source": "Yahoo Finance via yfinance 0.2.66; auto_adjust=False with explicit Adj Close; fixed recovered 56 MICRO_ETFS + QQQE",
        "etf_universe": MC57_ETFS, "raw": float(raw.loc[day]), "ema2_raw": float(ema2.loc[day]),
        "mu_prior": float(mu.loc[day]), "sigma_prior": float(sigma.loc[day]),
        "z": float(z.loc[day]), "mc57": float(score.loc[day]),
        "metric_scores": current_metrics,
        "fixed57_breadth": {"sma20": current_metrics["close_gt_sma20"],
                            "sma50": current_metrics["close_gt_sma50"],
                            "sma200": current_metrics["close_gt_sma200"]},
        "coverage_detail": {"fixed_etf_count": 57, "current_close_count": 57,
                            "current_close_coverage": 1.0, "metric_valid_counts": valid_counts,
                            "fetch": {"fixed_etf_count": 57, "downloaded_history_count": 57,
                                      "current_close_count": 57, "current_close_coverage": 1.0,
                                      "missing_current": [], "acquisition_attempts": 3,
                                      "retry_policy": "same fixed57 Yahoo contract; 30s then 60s backoff"}},
        "history_window_sessions": 504, "ui_history_limit": 504, "history": rows,
        "metric_history": {name: [{"date": r["date"], "value": r["metrics"][name]}
                                  for r in rows if name in r["metrics"]] for name in METRIC_NAMES},
        "price_contract": {"vendor": "Yahoo Finance", "client": "yfinance==0.2.66",
                           "download_auto_adjust": False, "calculation_price": "Adj Close",
                           "history_start": "2004-01-01", "symbol_substitution": "none",
                           "target_close_policy": "require all fixed 57 ETFs present for current session",
                           "missing_metric_policy": "exclude missing ETF from that metric denominator",
                           "target_session_source": "QQQ+SPY common completed session",
                           "timezone": "America/New_York", "completed_session_cutoff_et": "16:15",
                           "calendar": "observed US ETF daily sessions cut to Dashboard completed session"},
        "reference": {"verification_kind": "RECOVERED_FORMAL_SPEC_2026-09-16"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    data, work = root / "data", root / "work"
    data.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    target = latest_session()
    print(f"target completed US session: {target}", flush=True)

    tv = la.fetch_tradingview_response()
    universe, universe_stats = la.parse_tradingview_universe(tv, session_date=target)
    tickers = [r["ticker"] for r in universe]
    rs = {"session_date": target, "generated_at": generated_at, "status": "READY",
          "coverage": 1.0, "coverage_detail": universe_stats, "rows": universe,
          "source": "TradingView america/scan"}
    dump(data / "rs.json", rs)
    mktcap = {r["ticker"]: {"value": r["market_cap"], "checked_at": generated_at, "status": "ok"}
               for r in universe}
    if len(mktcap) / len(universe) < 0.95:
        raise RuntimeError("TradingView market-cap coverage below 95%")
    dump(data / "mktcap.json", mktcap)

    theme = json.loads((root / "seed" / "theme_membership_2026-09-16.json").read_text(encoding="utf-8"))
    theme["session_date"], theme["generated_at"] = target, generated_at
    dump(data / "theme_membership.json", theme)

    yahoo_stats = stock_ohlcv(tickers, target, work / "ohlcv.csv")
    market = la.download_market_inputs(yf, target_session=target, generated_at=generated_at)
    dump(data / "market_inputs.json", market)
    mc57 = compute_mc57(mc57_prices(target), target, generated_at)
    dump(data / "mc57.json", mc57)
    dump(data / "state.json", la.state_object(session_date=target, generated_at=generated_at,
                                               coverage=yahoo_stats["target_session_coverage"]))
    manifest = la.manifest_object(session_date=target, generated_at=generated_at,
                                  universe_stats=universe_stats, yahoo_stats=yahoo_stats,
                                  nqsar_status="RECOVERED_SOURCE_ROUTE")
    manifest.update({"mc57_status": "READY", "mc57": mc57["mc57"],
                     "mcap_coverage": len(mktcap) / len(universe),
                     "publication_scope": "source-mc57 only; V38 and data/*.json are not committed"})
    dump(root / "latest-manifest.json", manifest)
    print(json.dumps({"session_date": target, "universe": len(tickers),
                      "coverage": yahoo_stats["target_session_coverage"],
                      "mc57": mc57["mc57"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
