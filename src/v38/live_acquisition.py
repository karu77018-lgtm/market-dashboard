from __future__ import annotations

import csv
import json
import math
import re
import time
import urllib.request
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

CALCULATION_VERSION = "v38-live-acquisition-1.2.0"
STATE_SCHEMA_VERSION = "v38.state.1"
MANIFEST_SCHEMA_VERSION = "v38.acquisition.1"
MARKET_INPUT_SCHEMA_VERSION = "v38.market_inputs.1"
TRADINGVIEW_URL = "https://scanner.tradingview.com/america/scan"
ALLOWED_EXCHANGES = ("NYSE", "NASDAQ", "AMEX")
UNIVERSE_MIN_MCAP = 200_000_000.0
UNIVERSE_MIN_PRICE = 1.0
UNIVERSE_FALLBACK_RATIO = 0.80
MIN_CURRENT_FETCH_COVERAGE = 0.80
SESSION_CUTOFF_ET = dtime(16, 15)
SESSION_TIMEZONE = "America/New_York"
TRADINGVIEW_COLUMNS = (
    "name", "description", "close", "market_cap_basic", "sector",
    "industry", "type", "subtype", "exchange",
)
CLASS_PAIRS = (
    ("GOOGL", "GOOG"), ("FOXA", "FOX"), ("NWSA", "NWS"),
    ("UA", "UAA"), ("LILAK", "LILA"), ("HEI.A", "HEI"),
)
SPECIAL_SECURITY_RE = re.compile(
    r"\bPfd\b|Preferred|Warrant|\bRight(?:s)?\b|\bUnit(?:s)?\b|Subordinated Notes", re.I
)
PRIMARY_MARKET_SYMBOLS = ("QQQ", "TQQQ", "^VIX", "NQ=F", "SPY")
MARKET_SYMBOLS = (
    "QQQ", "TQQQ", "SPY", "RSP", "IWD", "IWF", "IWM", "MDY", "QQQE", "SOXL",
    "^VIX", "^VIX3M", "^VXN", "NQ=F",
    "HYG", "IEF", "^TNX", "^FVX", "DX-Y.NYB", "CL=F", "GC=F",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE",
    "XLU", "XLV", "XLY",
)


class LiveAcquisitionError(RuntimeError):
    pass


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def build_tradingview_payload(*, start: int = 0, end: int = 10000) -> dict[str, Any]:
    if start < 0 or end <= start:
        raise LiveAcquisitionError("invalid TradingView range")
    return {
        "filter": [
            {"left": "exchange", "operation": "in_range", "right": list(ALLOWED_EXCHANGES)},
            {"left": "market_cap_basic", "operation": "egreater", "right": UNIVERSE_MIN_MCAP},
            {"left": "close", "operation": "egreater", "right": UNIVERSE_MIN_PRICE},
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": list(TRADINGVIEW_COLUMNS),
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [start, end],
        "preset": "all_stocks",
    }


def fetch_tradingview_response(*, timeout: float = 30.0) -> dict[str, Any]:
    body = json.dumps(build_tradingview_payload(), separators=(",", ":")).encode()
    req = urllib.request.Request(
        TRADINGVIEW_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "Mozilla/5.0 (v38-market-dashboard)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            obj = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise LiveAcquisitionError(f"TradingView universe fetch failed: {exc}") from exc
    if not isinstance(obj, dict):
        raise LiveAcquisitionError("TradingView response is not a JSON object")
    return obj


def parse_tradingview_universe(response: dict[str, Any], *, session_date: str):
    try:
        session_date = pd.Timestamp(session_date).strftime("%Y-%m-%d")
    except Exception as exc:
        raise LiveAcquisitionError(f"invalid session_date: {session_date}") from exc
    data = response.get("data")
    if not isinstance(data, list):
        raise LiveAcquisitionError("TradingView response.data must be a list")
    parsed, malformed, below_floor, special = [], 0, 0, 0
    for item in data:
        if not isinstance(item, dict):
            malformed += 1
            continue
        symbol, values = item.get("s"), item.get("d")
        if not isinstance(symbol, str) or ":" not in symbol or not isinstance(values, list) or len(values) < len(TRADINGVIEW_COLUMNS):
            malformed += 1
            continue
        exchange_from_symbol, ticker = symbol.split(":", 1)
        row = dict(zip(TRADINGVIEW_COLUMNS, values))
        exchange = str(row.get("exchange") or exchange_from_symbol).strip().upper()
        ticker = ticker.strip().upper()
        price, mcap = _finite(row.get("close")), _finite(row.get("market_cap_basic"))
        if exchange not in ALLOWED_EXCHANGES or price is None or price < UNIVERSE_MIN_PRICE or mcap is None or mcap < UNIVERSE_MIN_MCAP:
            below_floor += 1
            continue
        description = str(row.get("description") or "").strip()
        if not ticker or "/" in ticker or any(c.isspace() for c in ticker) or (description and SPECIAL_SECURITY_RE.search(description)):
            special += 1
            continue
        parsed.append({
            "ticker": ticker, "session_date": session_date, "in_universe": True,
            "name": description or str(row.get("name") or ticker).strip(),
            "market_cap": mcap, "sector": str(row.get("sector") or "").strip(),
            "industry": str(row.get("industry") or "").strip(), "exchange": exchange,
            "price": price, "source": "TradingView america/scan",
        })
    parsed.sort(key=lambda r: (-float(r["market_cap"]), r["exchange"], r["ticker"]))
    unique, duplicate_symbol = {}, 0
    for row in parsed:
        if row["ticker"] in unique:
            duplicate_symbol += 1
        else:
            unique[row["ticker"]] = row
    survivors = list(unique.values())
    have = {r["ticker"] for r in survivors}
    discard = {drop for keep, drop in CLASS_PAIRS if keep in have and drop in have}
    survivors = sorted((r for r in survivors if r["ticker"] not in discard), key=lambda r: r["ticker"])
    if not survivors:
        raise LiveAcquisitionError("TradingView universe resolved to zero tickers")
    return survivors, {
        "response_total_count": response.get("totalCount"), "response_rows": len(data),
        "malformed_rows": malformed, "below_floor_rows": below_floor,
        "special_security_rows": special, "duplicate_symbol_rows": duplicate_symbol,
        "duplicate_class_rows": len(discard), "active_universe": len(survivors),
        "biotech_heuristic_applied": False,
    }


def validate_universe_count(new_count: int, previous_count: int | None) -> None:
    if new_count <= 0:
        raise LiveAcquisitionError("new universe count must be positive")
    if previous_count and previous_count > 0:
        floor = math.floor(previous_count * UNIVERSE_FALLBACK_RATIO)
        if new_count < floor:
            raise LiveAcquisitionError(f"universe count guard failed: {new_count} < 80% of previous {previous_count} ({floor})")


def yahoo_symbol(ticker: str) -> str:
    return str(ticker).strip().upper().replace(".", "-")


def _normalise_frame_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def select_yfinance_symbol_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = [str(x) for x in raw.columns.get_level_values(0)]
        level1 = [str(x) for x in raw.columns.get_level_values(1)]
        if symbol in level0:
            return _normalise_frame_columns(raw[symbol])
        if symbol in level1:
            return _normalise_frame_columns(raw.xs(symbol, axis=1, level=1))
        return pd.DataFrame()
    return _normalise_frame_columns(raw)


def frame_dates(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return []
    f = _normalise_frame_columns(frame)
    if "close" not in f.columns:
        return []
    out = []
    for idx, value in f["close"].items():
        if _finite(value) is None:
            continue
        try:
            out.append(pd.Timestamp(idx).strftime("%Y-%m-%d"))
        except Exception:
            pass
    return sorted(set(out))


def choose_completed_session(qqq_dates: Iterable[str], spy_dates: Iterable[str], *, now_utc: datetime | None = None) -> str:
    """Choose the latest completed common QQQ/SPY daily session.

    The recovered production contract uses America/New_York and 16:15 ET as the
    daily completion cutoff. Real observed QQQ/SPY sessions are the calendar;
    weekends, holidays and ad-hoc closures are therefore not synthesized.
    """
    common = sorted(set(qqq_dates) & set(spy_dates))
    if not common:
        raise LiveAcquisitionError("QQQ/SPY have no common daily session")
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ny = now.astimezone(ZoneInfo(SESSION_TIMEZONE))
    candidates = [d for d in common if d <= ny.date().isoformat()]
    if not candidates:
        raise LiveAcquisitionError("QQQ/SPY common sessions are in the future")
    latest = candidates[-1]
    if latest == ny.date().isoformat() and ny.time() < SESSION_CUTOFF_ET:
        if len(candidates) < 2:
            raise LiveAcquisitionError("no prior completed QQQ/SPY session available")
        latest = candidates[-2]
    return latest


def prevent_session_regression(observed_session: str, previous_session: str | None) -> str:
    """Keep a transient provider response from moving publication backward.

    A retained prior session still has to pass the normal stock-coverage and
    required-market-symbol checks. Otherwise the staged run aborts without
    replacing the existing atomic publication.
    """
    try:
        observed = pd.Timestamp(observed_session).strftime("%Y-%m-%d")
        previous = (
            pd.Timestamp(previous_session).strftime("%Y-%m-%d")
            if previous_session
            else None
        )
    except Exception as exc:
        raise LiveAcquisitionError("invalid observed/previous session date") from exc
    return previous if previous is not None and previous > observed else observed


def adjusted_ohlcv_rows(frame: pd.DataFrame, *, ticker: str, target_session: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    f = _normalise_frame_columns(frame)
    if not {"high", "low", "close", "volume"}.issubset(f.columns):
        return []
    rows = []
    for idx, raw in f.iterrows():
        try:
            day = pd.Timestamp(idx).strftime("%Y-%m-%d")
        except Exception:
            continue
        if day > target_session:
            continue
        close = _finite(raw.get("close"))
        adj = _finite(raw.get("adj_close")) if "adj_close" in f.columns else None
        factor = adj / close if close and close > 0 and adj and adj > 0 else None
        split_checked = factor is not None and math.isfinite(factor) and factor > 0

        def av(name: str):
            value = _finite(raw.get(name))
            return value * factor if value is not None and factor is not None else None

        row = {
            "ticker": ticker, "date": day, "open": av("open") if "open" in f.columns else None,
            "high": av("high"), "low": av("low"), "close": av("close"),
            "volume": _finite(raw.get("volume")), "is_complete": True,
            "split_checked": split_checked, "split_anomaly": False,
        }
        if not all(row[k] is None for k in ("high", "low", "close", "volume")):
            rows.append(row)
    return rows


def market_rows(frame: pd.DataFrame, *, target_session: str, max_rows: int = 260):
    rows = adjusted_ohlcv_rows(frame, ticker="_", target_session=target_session)
    out = [{k: r[k] for k in ("date", "open", "high", "low", "close", "volume")} for r in rows if r["close"] is not None]
    return out[-max_rows:]


def _download(yf: Any, symbols: list[str], *, period: str, threads: int | bool) -> pd.DataFrame:
    return yf.download(tickers=symbols, period=period, interval="1d", group_by="ticker",
                       auto_adjust=False, actions=False, progress=False, threads=threads, timeout=20)


def fetch_benchmark_frames(yf: Any) -> dict[str, pd.DataFrame]:
    raw = _download(yf, ["QQQ", "SPY"], period="1mo", threads=False)
    return {s: select_yfinance_symbol_frame(raw, s) for s in ("QQQ", "SPY")}


def download_stock_ohlcv(yf: Any, tickers: list[str], *, target_session: str, output_path: str | Path, chunk_size: int = 100):
    if not tickers:
        raise LiveAcquisitionError("no tickers supplied to Yahoo")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ("ticker", "date", "open", "high", "low", "close", "volume", "is_complete", "split_checked", "split_anomaly")
    target_ok, history_ok, failed = 0, 0, []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for offset in range(0, len(tickers), chunk_size):
            originals = tickers[offset:offset + chunk_size]
            symbol_map = {t: yahoo_symbol(t) for t in originals}
            try:
                raw = _download(yf, list(symbol_map.values()), period="2y", threads=16)
            except Exception:
                raw = pd.DataFrame()
            rows_by = {}
            missing = []
            for ticker, symbol in symbol_map.items():
                rows = adjusted_ohlcv_rows(select_yfinance_symbol_frame(raw, symbol), ticker=ticker, target_session=target_session)
                rows_by[ticker] = rows
                if not any(r["date"] == target_session and r["close"] is not None for r in rows):
                    missing.append(ticker)
            for round_no in range(2):
                if not missing:
                    break
                retry_map = {t: yahoo_symbol(t) for t in missing}
                try:
                    retry = _download(yf, list(retry_map.values()), period="2y", threads=16)
                except Exception:
                    retry = pd.DataFrame()
                next_missing = []
                for ticker, symbol in retry_map.items():
                    rows = adjusted_ohlcv_rows(select_yfinance_symbol_frame(retry, symbol), ticker=ticker, target_session=target_session)
                    if any(r["date"] == target_session and r["close"] is not None for r in rows):
                        rows_by[ticker] = rows
                    else:
                        next_missing.append(ticker)
                missing = next_missing
                if missing:
                    time.sleep(1.5 * (round_no + 1))
            for ticker in originals:
                rows = rows_by.get(ticker) or []
                if rows:
                    history_ok += 1
                    writer.writerows(rows)
                if any(r["date"] == target_session and r["close"] is not None for r in rows):
                    target_ok += 1
                else:
                    failed.append(ticker)
    coverage = target_ok / len(tickers)
    if coverage < MIN_CURRENT_FETCH_COVERAGE:
        raise LiveAcquisitionError(f"Yahoo current-session coverage too low: {target_ok}/{len(tickers)}={coverage:.3f}")
    return {"requested": len(tickers), "history_received": history_ok, "target_session_received": target_ok,
            "target_session_coverage": coverage, "failed_tickers": failed}


def download_market_inputs(yf: Any, *, target_session: str, generated_at: str) -> dict[str, Any]:
    series: dict[str, list[dict[str, Any]]] = {}
    present = 0
    for offset in range(0, len(MARKET_SYMBOLS), 10):
        symbols = list(MARKET_SYMBOLS[offset:offset + 10])
        try:
            raw = _download(yf, symbols, period="2y", threads=False)
        except Exception:
            raw = pd.DataFrame()
        for symbol in symbols:
            rows = market_rows(
                select_yfinance_symbol_frame(raw, symbol),
                target_session=target_session,
            )
            if not rows or rows[-1]["date"] != target_session:
                try:
                    retry = _download(yf, [symbol], period="2y", threads=False)
                except Exception:
                    retry = pd.DataFrame()
                retried = market_rows(
                    select_yfinance_symbol_frame(retry, symbol),
                    target_session=target_session,
                )
                if retried:
                    rows = retried
            series[symbol] = rows
            present += int(bool(rows and rows[-1]["date"] == target_session))
    primary_present = sum(
        int(bool(series.get(symbol) and series[symbol][-1]["date"] == target_session))
        for symbol in PRIMARY_MARKET_SYMBOLS
    )
    if primary_present != len(PRIMARY_MARKET_SYMBOLS):
        missing = [
            symbol for symbol in PRIMARY_MARKET_SYMBOLS
            if not series.get(symbol) or series[symbol][-1]["date"] != target_session
        ]
        raise LiveAcquisitionError(
            "required market inputs missing current session: " + ",".join(missing)
        )
    return {
        "session_date": target_session, "generated_at": generated_at,
        "coverage": present / len(MARKET_SYMBOLS),
        "required_coverage": primary_present / len(PRIMARY_MARKET_SYMBOLS),
        "source": "Yahoo Finance via yfinance 0.2.66; OHLC adjusted by Adj Close when available",
        "schema_version": MARKET_INPUT_SCHEMA_VERSION, "calculation_version": CALCULATION_VERSION,
        "symbols": list(MARKET_SYMBOLS),
        "required_symbols": list(PRIMARY_MARKET_SYMBOLS),
        "diagnostic_symbols": [s for s in MARKET_SYMBOLS if s not in PRIMARY_MARKET_SYMBOLS],
        "series": series,
        "qqq_4h_status": "DATA_REQUIRED", "qqq_4h_reason": "STAGE56_4H_FIXTURE_NOT_AVAILABLE",
    }


def previous_active_universe(rs_path: str | Path) -> int | None:
    try:
        obj = json.loads(Path(rs_path).read_text(encoding="utf-8"))
        n = int(obj.get("coverage_detail", {}).get("active_universe"))
        return n if n > 0 else None
    except Exception:
        return None


def write_universe_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = ("ticker", "session_date", "in_universe", "name", "market_cap", "sector", "industry", "exchange", "price", "source")
    with p.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


def write_json(path: str | Path, obj: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return p


def state_object(*, session_date: str, generated_at: str, coverage: float) -> dict[str, Any]:
    return {
        "session_date": session_date,
        "generated_at": generated_at,
        "coverage": coverage,
        "source": "authoritative-session:QQQ+SPY; universe:TradingView; prices:Yahoo",
        "schema_version": STATE_SCHEMA_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "status": "READY",
        "session_contract": {
            "timezone": SESSION_TIMEZONE,
            "cutoff_et": "16:15",
            "calendar": "observed common QQQ/SPY completed daily sessions",
        },
    }


def manifest_object(*, session_date: str, generated_at: str, universe_stats: dict[str, Any], yahoo_stats: dict[str, Any], nqsar_status: str):
    return {
        "session_date": session_date, "generated_at": generated_at,
        "coverage": yahoo_stats["target_session_coverage"],
        "source": "TradingView america/scan + Yahoo Finance/yfinance 0.2.66",
        "schema_version": MANIFEST_SCHEMA_VERSION, "calculation_version": CALCULATION_VERSION, "status": "READY",
        "session_contract": {
            "timezone": SESSION_TIMEZONE,
            "cutoff_et": "16:15",
            "calendar": "observed common QQQ/SPY completed daily sessions",
            "price_primary": "Yahoo Finance",
            "ticker_resolution_fallback": "FMP only when explicitly available; never substitute unverified price values",
        },
        "universe": universe_stats, "yahoo": yahoo_stats, "nqsar_status": nqsar_status,
        "mc57_status": "DATA_REQUIRED", "mc57_reason": "FIXED57_AND_GOLDEN_FIXTURE_NOT_AVAILABLE",
        "structural_clinical_biotech_status": "DATA_REQUIRED", "peer_theme_status": "DATA_REQUIRED",
        "options_status": "DATA_REQUIRED", "positions_status": "DATA_REQUIRED",
    }
