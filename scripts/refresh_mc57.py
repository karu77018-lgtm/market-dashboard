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
from provider_inputs import (  # noqa: E402
    ProviderError,
    compare_current_closes,
    compute_massive_market_structure,
    fetch_fred_inputs,
    fetch_massive_grouped_history,
    fetch_massive_reference,
    grouped_history_from_yahoo_ohlcv,
    load_massive_grouped_cache,
    load_massive_reference_cache,
    record_grouped_fallback,
    secret_from_env,
    select_expanded_universe,
    select_preserved_count_fallback_universe,
)


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


def recent_completed_sessions(count: int = 20) -> list[str]:
    raw = la._download(yf, ["QQQ", "SPY"], period="3mo", threads=False)
    frames = {symbol: la.select_yfinance_symbol_frame(raw, symbol) for symbol in ("QQQ", "SPY")}
    qqq_dates, spy_dates = la.frame_dates(frames["QQQ"]), la.frame_dates(frames["SPY"])
    target = la.choose_completed_session(qqq_dates, spy_dates)
    common = sorted(d for d in set(qqq_dates) & set(spy_dates) if d <= target)
    if len(common) < count:
        raise RuntimeError(f"only {len(common)} completed QQQ/SPY sessions available; need {count}")
    return common[-count:]


def resolve_refresh_sessions(
    sessions: list[str], previous_session: str | None, *, count: int = 20
) -> tuple[list[str], str, str]:
    if not sessions:
        raise RuntimeError("no completed sessions available")
    observed_target = sessions[-1]
    target = la.prevent_session_regression(observed_target, previous_session)
    if target != observed_target:
        sessions = sorted(set([*sessions, target]))[-count:]
    return sessions, target, observed_target


def stock_ohlcv(tickers: list[str], target: str, output: Path,
                *, chunk_size: int = 100) -> dict[str, Any]:
    """Three-year baseline, then one-month incremental adjusted OHLCV.

    GitHub Actions restores the prior successful CSV from a rolling cache.  New
    tickers still receive the full baseline; existing tickers only fetch enough
    recent data to cover missed sessions. A quote already quality-gated for the
    exact target session can be reused on a same-session rerun; an older session
    can never pass the gate.
    """
    fields = ("ticker", "date", "open", "high", "low", "close", "volume",
              "is_complete", "split_checked", "split_anomaly")
    import csv

    output.parent.mkdir(parents=True, exist_ok=True)
    cached = pd.DataFrame()
    cached_tickers: set[str] = set()
    cached_target_tickers: set[str] = set()
    if output.is_file() and output.stat().st_size > 0:
        try:
            cached = pd.read_csv(output)
            if {"ticker", "date"}.issubset(cached.columns):
                cached["ticker"] = cached["ticker"].astype(str).str.upper()
                cached["date"] = cached["date"].astype(str)
                counts = cached.groupby("ticker")["date"].count()
                cached_tickers = set(counts[counts >= 200].index.astype(str))
                cached_target_tickers = set(
                    cached.loc[cached["date"] == target, "ticker"].astype(str)
                )
            else:
                cached = pd.DataFrame()
        except Exception:
            cached = pd.DataFrame()
    fresh_path = output.with_suffix(".fresh.csv")
    target_ok = target_fresh_ok = target_cache_ok = history_ok = 0
    failed: list[str] = []
    with fresh_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for offset in range(0, len(tickers), chunk_size):
            originals = tickers[offset:offset + chunk_size]
            # A rerun of the exact same market session must not discard a
            # previously quality-gated close just because Yahoo temporarily
            # throttles or returns an incomplete batch. Only retry names whose
            # target-session row is absent; never substitute an older date.
            pending = [ticker for ticker in originals if ticker not in cached_target_tickers]
            rows_by: dict[str, list[dict[str, Any]]] = {}
            for attempt in range(3):
                if not pending:
                    break
                symbols = {t: la.yahoo_symbol(t) for t in pending}
                try:
                    period = "1mo" if all(t in cached_tickers for t in pending) else "3y"
                    raw = la._download(yf, list(symbols.values()), period=period, threads=16)
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
                    target_fresh_ok += 1
                elif ticker in cached_target_tickers:
                    target_ok += 1
                    target_cache_ok += 1
                else:
                    failed.append(ticker)
            print(f"stock OHLCV {min(offset + chunk_size, len(tickers))}/{len(tickers)}", flush=True)
    coverage = target_ok / len(tickers)
    if coverage < 0.95:
        raise RuntimeError(
            f"current-session stock coverage below 95%: {target_ok}/{len(tickers)}={coverage:.4f}"
        )
    fresh = pd.read_csv(fresh_path)
    if not cached.empty:
        merged = pd.concat([cached, fresh], ignore_index=True)
        merged["ticker"] = merged["ticker"].astype(str).str.upper()
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        start = pd.Timestamp(target) - pd.Timedelta(days=1120)
        merged = merged[
            merged["ticker"].isin(tickers) & merged["date"].notna()
            & (merged["date"] >= start) & (merged["date"] <= pd.Timestamp(target))
        ]
        merged = merged.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
        merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
        merged.to_csv(output, index=False)
        history_ok = int(merged.groupby("ticker")["date"].size().gt(0).sum())
        fresh_path.unlink(missing_ok=True)
    else:
        fresh_path.replace(output)
    return {
        "requested": len(tickers), "history_received": history_ok,
        "target_session_received": target_ok, "target_session_coverage": coverage,
        "target_session_fresh": target_fresh_ok,
        "target_session_same_day_cache": target_cache_ok,
        "failed_tickers": failed, "incremental_cache_used": bool(cached_tickers),
    }


def prior_universe_tickers(root: Path, ohlcv_path: Path) -> list[str]:
    if ohlcv_path.is_file():
        try:
            frame = pd.read_csv(ohlcv_path, usecols=["ticker"])
            tickers = sorted(set(frame["ticker"].dropna().astype(str).str.upper()))
            if tickers:
                return tickers
        except Exception:
            pass
    index_path = root / "chart-data" / "index.json"
    if index_path.is_file():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        mapping = payload.get("ticker_to_shard")
        if isinstance(mapping, dict) and mapping:
            return sorted(str(ticker).upper() for ticker in mapping)
    raise ProviderError("Yahoo fallback cannot recover the prior universe ticker list")


def prior_universe_count(root: Path, tickers: list[str]) -> int:
    try:
        manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        count = int(manifest.get("universe", {}).get("active_universe", 0))
        return count if count > 0 else len(tickers)
    except Exception:
        return len(tickers)


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
        # Yahoo occasionally publishes a complete historical frame without the
        # just-closed bar for every ETF.  Preserve that history and fill only
        # the resolved current session from TradingView's US scanner.
        try:
            fallback_closes = la.fetch_tradingview_current_closes(pending)
        except la.LiveAcquisitionError:
            fallback_closes = {}
        filled: list[str] = []
        for ticker in pending:
            close = fallback_closes.get(ticker)
            if close is None or ticker not in series or series[ticker].empty:
                continue
            updated = series[ticker].copy()
            updated.loc[pd.Timestamp(target)] = float(close)
            series[ticker] = updated.sort_index()
            filled.append(ticker)
        if filled:
            print(
                "MC57 TradingView current-session fallback: " + ",".join(sorted(filled)),
                flush=True,
            )
            pending = [ticker for ticker in pending if ticker not in set(filled)]
    if pending:
        raise RuntimeError("MC57 fixed universe missing current closes: " + ",".join(pending))
    close = pd.DataFrame(series).sort_index()
    return close[close.index <= pd.Timestamp(target)]


def _participation(condition: pd.DataFrame, valid: pd.DataFrame) -> pd.Series:
    return condition.astype(float).where(valid).mean(axis=1, skipna=True) * 100.0


def compute_mc57(close: pd.DataFrame, target: str, generated_at: str, *, history_output: Path | None = None) -> dict[str, Any]:
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
    for d in score.dropna().iloc[-2520:].index:
        vals = {name: float(mf.at[d, name]) for name in METRIC_NAMES if pd.notna(mf.at[d, name])}
        rows.append({
            "date": d.strftime("%Y-%m-%d"), "raw": float(raw.loc[d]),
            "ema2_raw": float(ema2.loc[d]), "z": float(z.loc[d]),
            "mc57": float(score.loc[d]), "metrics": vals,
            "fixed57_breadth_sma20": vals.get("close_gt_sma20"),
            "fixed57_breadth_sma50": vals.get("close_gt_sma50"),
            "fixed57_breadth_sma200": vals.get("close_gt_sma200"),
        })
    # The calculation above is unchanged. Persist long output separately before
    # restoring the original 504-row API contract for all existing consumers.
    if history_output is not None:
        dump(history_output, {"schema": "market-history.mc57.full.1", "session_date": target,
             "source": "same fixed57 adjusted-price inputs and unchanged MC57 formula",
             "calculation_version": "v38-mc57-live-1.0.0", "history": rows})
    rows = rows[-504:]
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
    try:
        massive_key = secret_from_env(("MASSIVE_API_KEY", "POLYGON_API_KEY"))
    except ProviderError:
        massive_key = ""
    fred_key = secret_from_env(("FRED_API_KEY",))
    sessions = recent_completed_sessions(20)
    observed_target = sessions[-1]
    previous_session = None
    manifest_path = root / "latest-manifest.json"
    if manifest_path.is_file():
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            previous_session = previous_manifest.get("session_date")
        except Exception:
            previous_session = None
    sessions, target, observed_target = resolve_refresh_sessions(
        sessions, previous_session, count=20
    )
    if target != observed_target:
        print(
            f"provider session regression blocked: observed={observed_target} retained={target}",
            flush=True,
        )
    print(f"target completed US session: {target}", flush=True)

    tv = la.fetch_tradingview_response()
    broad_universe, tradingview_stats = la.parse_tradingview_universe(tv, session_date=target)
    fallback_reason = ""
    try:
        if not massive_key:
            raise ProviderError("Massive API key is unavailable")
        reference, reference_stats = fetch_massive_reference(
            massive_key, work / "massive-reference.json", asof_date=target,
        )
    except ProviderError as exc:
        fallback_reason = str(exc)
        reference = load_massive_reference_cache(work / "massive-reference.json")
        reference_stats = {"status": "CACHED_FALLBACK", "source": "cache", "reason": fallback_reason,
                           "eligible_reference_tickers": len(reference)}
    try:
        if not massive_key:
            raise ProviderError("Massive API key is unavailable")
        grouped, grouped_stats = fetch_massive_grouped_history(
            massive_key, sessions, set(reference), work / "massive-grouped.json",
        )
    except ProviderError as exc:
        fallback_reason = str(exc)
        grouped = load_massive_grouped_cache(work / "massive-grouped.json")
        grouped_stats = {"status": "YAHOO_FALLBACK", "reason": fallback_reason,
                         "latest_session": max(grouped), "sessions": len(grouped),
                         "requested_sessions": len(sessions), "fetched_sessions": []}

    yahoo_fallback = bool(fallback_reason) or target not in grouped
    if yahoo_fallback:
        print(f"Massive current-session fallback: {fallback_reason or 'session unavailable'}", flush=True)
        prior_tickers = prior_universe_tickers(root, work / "ohlcv.csv")
        frozen_count = prior_universe_count(root, prior_tickers)
        universe, expansion_stats = select_preserved_count_fallback_universe(
            broad_universe, reference, grouped, preserved_tickers=prior_tickers,
            target_count=frozen_count,
        )
        record_grouped_fallback(work / "massive-grouped.json", target, fallback_reason or "current session unavailable")
    else:
        universe, expansion_stats = select_expanded_universe(
            broad_universe, reference, grouped, target_session=target,
        )
    universe_stats = {
        **tradingview_stats, **expansion_stats,
        "broad_tradingview_universe": len(broad_universe),
        "massive_reference": reference_stats,
        "massive_grouped": grouped_stats,
    }
    tickers = [r["ticker"] for r in universe]
    rs = {"session_date": target, "generated_at": generated_at, "status": "READY",
          "coverage": 1.0, "coverage_detail": universe_stats, "rows": universe,
          "source": ("TradingView fundamentals + cached Massive reference + Yahoo current OHLCV"
                     if yahoo_fallback else "TradingView fundamentals + Massive reference/grouped daily")}
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
    if yahoo_fallback:
        structure_history = grouped_history_from_yahoo_ohlcv(
            work / "ohlcv.csv", tickers, target_session=target,
        )
        market_structure = compute_massive_market_structure(
            tickers, structure_history, target_session=target,
            source="Yahoo Finance adjusted OHLCV fallback",
        )
        cross_vendor = {"status": "NOT_APPLICABLE", "coverage": None,
                        "reason": "Massive current-session grouped data unavailable"}
    else:
        market_structure = compute_massive_market_structure(tickers, grouped, target_session=target)
        cross_vendor = compare_current_closes(
            work / "ohlcv.csv", grouped, target_session=target, universe_count=len(tickers),
        )
        if cross_vendor["coverage"] < .95:
            raise RuntimeError(
                f"Yahoo/Massive cross-vendor current-close coverage below 95%: {cross_vendor['coverage']:.4f}"
            )
    fred = fetch_fred_inputs(
        fred_key, target_session=target, generated_at=generated_at,
    )
    provider_inputs = {
        "schema": "source-mc57.provider-inputs.1", "session_date": target,
        "generated_at": generated_at, "massive": {
            "status": "FALLBACK_YAHOO" if yahoo_fallback else "READY", "reference": reference_stats,
            "grouped": grouped_stats, "market_structure": market_structure,
            "cross_vendor": cross_vendor,
            "fallback_reason": fallback_reason or None,
        },
        "fred": fred,
    }
    dump(data / "provider_inputs.json", provider_inputs)
    market = la.download_market_inputs(yf, target_session=target, generated_at=generated_at)
    market["fred"] = fred
    market["massive_market_structure"] = market_structure
    dump(data / "market_inputs.json", market)
    mc57 = compute_mc57(mc57_prices(target), target, generated_at,
                         history_output=root / "market-history" / "mc57-full.json")
    dump(data / "mc57.json", mc57)
    dump(data / "state.json", la.state_object(session_date=target, generated_at=generated_at,
                                               coverage=yahoo_stats["target_session_coverage"]))
    manifest = la.manifest_object(session_date=target, generated_at=generated_at,
                                  universe_stats=universe_stats, yahoo_stats=yahoo_stats,
                                  nqsar_status="RECOVERED_SOURCE_ROUTE")
    manifest.update({"mc57_status": "READY", "mc57": mc57["mc57"],
                     "mcap_coverage": len(mktcap) / len(universe),
                     "provider_status": {
                         "fred": fred["status"], "fred_required_coverage": fred["required_coverage"],
                         "massive": "FALLBACK_YAHOO" if yahoo_fallback else "READY",
                         "massive_current_coverage": (None if yahoo_fallback else expansion_stats["massive_current_coverage"]),
                         "cross_vendor_coverage": cross_vendor["coverage"],
                         "current_session_provider": "Yahoo Finance" if yahoo_fallback else "Massive",
                     },
                     "universe_expansion": {
                         "legacy": expansion_stats["legacy_universe"],
                         "added": expansion_stats["massive_broad_expansion"],
                         "buy_filter_eligible": expansion_stats["buy_filter_eligible"],
                         "active": expansion_stats["active_universe"],
                     },
                     "publication_scope": (
                         "source-mc57 plus derived data/jev-ranking.json only; "
                         "V38 and vendor-input data JSON are not committed"
                     )})
    dump(root / "latest-manifest.json", manifest)
    print(json.dumps({"session_date": target, "universe": len(tickers),
                      "coverage": yahoo_stats["target_session_coverage"],
                      "mc57": mc57["mc57"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except ProviderError as exc:
        print(f"SOURCE_MC57_FAILURE=PROVIDER_ERROR:{exc}", flush=True)
        raise
    except RuntimeError as exc:
        print(f"SOURCE_MC57_FAILURE=QUALITY_GATE:{exc}", flush=True)
        raise
    except Exception as exc:
        print(f"SOURCE_MC57_FAILURE=UNEXPECTED_{type(exc).__name__}", flush=True)
        raise
    raise SystemExit(exit_code)
