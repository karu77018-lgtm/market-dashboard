"""Massive (and narrow TradingView) substitutes used only when Yahoo fails.

Yahoo Finance stays the primary route.  Everything here runs only after a
Yahoo request failed or returned no usable target-session bar, and every use is
recorded so the published page can say "Massive代替".

Massive daily bars are split-adjusted but not dividend-adjusted, while the
Yahoo history in the caches is Adj-Close adjusted.  Substituted bars are only
appended after the last cached date (never spliced into older history), exactly
like the existing TradingView current-close fallback.  No MC57/V38 formula is
changed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from provider_inputs import (
    MASSIVE_BASE,
    ProviderError,
    _finite,
    _get_json,
    _normalize_grouped_results,
)

NY = ZoneInfo("America/New_York")
MAX_GAP_SESSIONS = 5
# Index/futures symbols Massive grouped stocks cannot provide.  Values are
# (TradingView scanner market, TradingView symbol).
TRADINGVIEW_DAILY_BARS = {
    "^VIX": ("america", "CBOE:VIX"),
    "^VXN": ("america", "CBOE:VXN"),
    "NQ=F": ("futures", "CME_MINI:NQ1!"),
}
TRADINGVIEW_BAR_COMPLETE_ET = (17, 0)

GroupedFetcher = Callable[[list[str]], dict[str, dict[str, dict[str, float | int]]]]


def _ny_date_from_ms(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(NY).date().isoformat()


def massive_daily_bars(api_key: str, ticker: str, start: str, end: str,
                       *, client: requests.Session | None = None) -> dict[str, dict[str, float]]:
    payload = _get_json(
        client or requests.Session(),
        f"{MASSIVE_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
        params={"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": api_key},
    )
    if str(payload.get("status") or "").upper() not in {"OK", "DELAYED"}:
        raise ProviderError(f"Massive daily bars status for {ticker}: {payload.get('status')}")
    bars: dict[str, dict[str, float]] = {}
    for item in payload.get("results") or []:
        if not isinstance(item, dict) or _finite(item.get("t")) is None:
            continue
        close = _finite(item.get("c"))
        if close is None:
            continue
        bars[_ny_date_from_ms(float(item["t"]))] = {
            k: v for k, v in ((k, _finite(item.get(k))) for k in ("o", "h", "l", "c", "v")) if v is not None
        }
    return bars


def massive_completed_sessions(api_key: str, count: int, *, now_utc: datetime | None = None) -> list[str]:
    """Same contract as the Yahoo calendar: real QQQ/SPY sessions, 16:15 ET cutoff."""
    from v38 import live_acquisition as la

    now = now_utc or datetime.now(timezone.utc)
    end = now.astimezone(NY).date()
    start = end - timedelta(days=max(120, count * 3))
    client = requests.Session()
    qqq = massive_daily_bars(api_key, "QQQ", start.isoformat(), end.isoformat(), client=client)
    spy = massive_daily_bars(api_key, "SPY", start.isoformat(), end.isoformat(), client=client)
    target = la.choose_completed_session(qqq, spy, now_utc=now)
    common = sorted(d for d in set(qqq) & set(spy) if d <= target)
    if len(common) < count:
        raise ProviderError(f"only {len(common)} completed Massive QQQ/SPY sessions available; need {count}")
    return common[-count:]


def massive_grouped_raw(api_key: str, days: Iterable[str], tickers: Iterable[str],
                        cache_path: str | Path) -> dict[str, dict[str, dict[str, float | int]]]:
    """All-market grouped daily bars restricted to an explicit ETF/stock list.

    The universe grouped cache only keeps common shares, so ETFs need their own
    small cache.  One request returns the whole market for one day.
    """
    wanted = sorted(set(days))
    allowed = {str(t).upper() for t in tickers}
    path = Path(cache_path)
    try:
        stored = json.loads(path.read_text(encoding="utf-8")).get("sessions", {})
    except Exception:
        stored = {}
    sessions = {d: rows for d, rows in stored.items() if isinstance(rows, dict)}
    client = requests.Session()
    for day in wanted:
        if allowed.issubset(sessions.get(day, {})):
            continue
        payload = _get_json(
            client, f"{MASSIVE_BASE}/v2/aggs/grouped/locale/us/market/stocks/{day}",
            params={"adjusted": "true", "include_otc": "false", "apiKey": api_key},
        )
        if str(payload.get("status") or "").upper() not in {"OK", "DELAYED"}:
            raise ProviderError(f"Massive grouped status for {day}: {payload.get('status')}")
        rows = _normalize_grouped_results(payload.get("results") or [], allowed)
        if not rows:
            raise ProviderError(f"Massive grouped response for {day} had none of the requested ETFs")
        sessions[day] = {**sessions.get(day, {}), **rows}
    keep = dict(sorted(sessions.items())[-40:])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "source-mc57.massive-etf-grouped.1", "sessions": keep},
                               sort_keys=True) + "\n", encoding="utf-8")
    return {d: keep.get(d, {}) for d in wanted}


def gap_sessions(last_date: str | None, target: str, sessions: list[str]) -> list[str] | None:
    """Sessions after ``last_date`` through ``target``; None when the gap is unknown or too long."""
    if not last_date or last_date >= target:
        return [] if last_date == target else None
    if not sessions or last_date < sessions[0] or target not in sessions:
        return None
    gap = [s for s in sessions if last_date < s <= target]
    return gap if 0 < len(gap) <= MAX_GAP_SESSIONS else None


def ohlcv_rows_from_grouped(ticker: str, last_date: str | None, target: str, sessions: list[str],
                            grouped: dict[str, dict[str, dict[str, float | int]]]) -> list[dict[str, Any]]:
    """Rows in the work/ohlcv.csv schema for the sessions missing after the cache."""
    gap = gap_sessions(last_date, target, sessions)
    if not gap or any(ticker not in grouped.get(day, {}) for day in gap):
        return []
    rows = []
    for day in gap:
        bar = grouped[day][ticker]
        rows.append({
            "ticker": ticker, "date": day, "open": bar.get("o", bar["c"]), "high": bar["h"],
            "low": bar["l"], "close": bar["c"], "volume": bar["v"], "is_complete": True,
            "split_checked": False, "split_anomaly": False,
        })
    return rows


def tradingview_daily_bars(symbols: Iterable[str], target: str, *, now_utc: datetime | None = None,
                           timeout: float = 30.0) -> dict[str, dict[str, Any]]:
    """Completed daily bar for ``target`` for index/futures symbols, or nothing.

    The scanner exposes the current and previous daily bar with their start
    time.  A bar's trading date is its New York start time + 6h (futures open
    at 18:00 ET the evening before).  The current bar is used only after 17:00
    ET on the target date; otherwise only the previous (finished) bar.
    """
    from v38 import live_acquisition as la
    import urllib.request

    now = (now_utc or datetime.now(timezone.utc)).astimezone(NY)
    done = (now.date().isoformat() > target or (
        now.date().isoformat() == target and (now.hour, now.minute) >= TRADINGVIEW_BAR_COMPLETE_ET))
    by_market: dict[str, dict[str, str]] = {}
    for symbol in symbols:
        if symbol in TRADINGVIEW_DAILY_BARS:
            market, tv = TRADINGVIEW_DAILY_BARS[symbol]
            by_market.setdefault(market, {})[tv] = symbol
    fields = ("time", "open", "high", "low", "close", "volume")
    columns = [*fields, *(f"{f}[1]" for f in fields)]
    out: dict[str, dict[str, Any]] = {}
    for market, mapping in by_market.items():
        body = {"filter": [], "options": {"lang": "en"},
                "symbols": {"query": {"types": []}, "tickers": list(mapping)},
                "columns": columns, "range": [0, len(mapping)]}
        req = urllib.request.Request(
            la.TRADINGVIEW_URL.replace("/america/", f"/{market}/"),
            data=json.dumps(body, separators=(",", ":")).encode(), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": "Mozilla/5.0 (v38-market-dashboard)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8")).get("data") or []
        except Exception:
            continue
        for item in data:
            symbol = mapping.get(item.get("s")) if isinstance(item, dict) else None
            values = item.get("d") if symbol else None
            if not isinstance(values, list) or len(values) != len(columns):
                continue
            current, previous = values[:len(fields)], values[len(fields):]
            for bar, allowed in ((current, done), (previous, True)):
                start = _finite(bar[0])
                if start is None or not allowed:
                    continue
                trade_date = (datetime.fromtimestamp(start, timezone.utc).astimezone(NY)
                              + timedelta(hours=6)).date().isoformat()
                close = _finite(bar[4])
                if trade_date == target and close is not None:
                    out[symbol] = {"date": target, "open": _finite(bar[1]) or close,
                                   "high": _finite(bar[2]) or close, "low": _finite(bar[3]) or close,
                                   "close": close, "volume": _finite(bar[5]) or 0.0}
                    break
    return out


def market_inputs_fallback(cached: dict[str, Any], *, target: str, generated_at: str,
                           sessions: list[str], etf_bars: GroupedFetcher,
                           tv_bars: Callable[[list[str], str], dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Rebuild data/market_inputs.json from the last good series plus substitutes."""
    from v38 import live_acquisition as la

    prior_series = cached.get("series") if isinstance(cached.get("series"), dict) else {}
    series: dict[str, list[dict[str, Any]]] = {}
    gaps: dict[str, list[str]] = {}
    for symbol in la.MARKET_SYMBOLS:
        rows = [r for r in prior_series.get(symbol) or [] if isinstance(r, dict) and r.get("date", "") <= target]
        series[symbol] = rows
        last = rows[-1]["date"] if rows else None
        gap = gap_sessions(last, target, sessions)
        if gap:
            gaps[symbol] = gap
    plain = {s: g for s, g in gaps.items() if s.replace("-", "").isalnum() and s.isupper()}
    massive_used: list[str] = []
    if plain:
        days = sorted({d for g in plain.values() for d in g})
        try:
            grouped = etf_bars(days)
        except ProviderError:
            grouped = {}
        for symbol, gap in plain.items():
            if all(symbol in grouped.get(day, {}) for day in gap):
                for day in gap:
                    bar = grouped[day][symbol]
                    series[symbol].append({"date": day, "open": bar.get("o", bar["c"]), "high": bar["h"],
                                           "low": bar["l"], "close": bar["c"], "volume": bar["v"]})
                massive_used.append(symbol)
    tv_needed = [s for s, g in gaps.items() if s in TRADINGVIEW_DAILY_BARS and g == [target]]
    tv_used: list[str] = []
    if tv_needed:
        for symbol, row in tv_bars(tv_needed, target).items():
            series[symbol].append(row)
            tv_used.append(symbol)
    series = {s: rows[-260:] for s, rows in series.items()}

    def current(symbol: str) -> bool:
        return bool(series.get(symbol) and series[symbol][-1]["date"] == target)

    missing = [s for s in la.PRIMARY_MARKET_SYMBOLS if not current(s)]
    if missing:
        raise la.LiveAcquisitionError("required market inputs missing current session after Massive fallback: "
                                      + ",".join(missing))
    sector_present = sum(current(s) for s in la.SECTOR_MARKET_SYMBOLS)
    sector_coverage = sector_present / len(la.SECTOR_MARKET_SYMBOLS)
    if sector_coverage < 0.80:
        raise la.LiveAcquisitionError("major-sector market-input coverage too low after Massive fallback "
                                      f"({sector_present}/{len(la.SECTOR_MARKET_SYMBOLS)})")
    present = sum(current(s) for s in la.MARKET_SYMBOLS)
    out = {k: v for k, v in cached.items() if k not in {"series", "fred", "massive_market_structure"}}
    out.update({
        "session_date": target, "generated_at": generated_at,
        "coverage": present / len(la.MARKET_SYMBOLS), "required_coverage": 1.0,
        "sector_coverage": sector_coverage,
        "source": ("Massive代替: last good Yahoo adjusted series + Massive split-adjusted daily bars "
                   "(ETFs) + TradingView completed daily bars (index/futures) after Yahoo failed"),
        "current_session_fallback_symbols": sorted(massive_used + tv_used),
        "massive_fallback_symbols": sorted(massive_used),
        "tradingview_fallback_symbols": sorted(tv_used),
        "series": series,
    })
    return out


def mc57_fill(series: dict[str, pd.Series], pending: list[str], *, target: str, sessions: list[str],
              etf_bars: GroupedFetcher) -> list[str]:
    """Append Massive closes for MC57 ETFs whose history stops before ``target``.

    Mutates ``series`` and returns the tickers that were completed.
    """
    gaps = {}
    for ticker in pending:
        s = series.get(ticker)
        last = s.index[-1].strftime("%Y-%m-%d") if s is not None and not s.empty else None
        gap = gap_sessions(last, target, sessions)
        if gap:
            gaps[ticker] = gap
    if not gaps:
        return []
    try:
        grouped = etf_bars(sorted({d for g in gaps.values() for d in g}))
    except ProviderError:
        return []
    filled = []
    for ticker, gap in gaps.items():
        if all(ticker in grouped.get(day, {}) for day in gap):
            add = pd.Series({pd.Timestamp(day): float(grouped[day][ticker]["c"]) for day in gap})
            series[ticker] = pd.concat([series[ticker], add]).sort_index()
            filled.append(ticker)
    return filled


def read_close_cache(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(p, index_col=0, parse_dates=True)
    except Exception:
        return pd.DataFrame()
    return frame.sort_index()


def write_close_cache(path: str | Path, close: pd.DataFrame) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    close.to_csv(p, index_label="date", float_format="%.6f")
