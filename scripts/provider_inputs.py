#!/usr/bin/env python3
"""Provider adapters for the isolated source-mc57 refresh.

Massive is split by role: reference data is cached, grouped daily data is an
optional bulk route when entitled, and current-session publication can fall
back to Yahoo without blocking the dashboard. FRED is used for authoritative
macro observations. The module keeps provider payloads out of the published
repository; only derived values are rendered into source-mc57.html and
summarized in latest-manifest.json.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import pandas as pd
import requests


MASSIVE_BASE = "https://api.massive.com"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
MAJOR_US_MICS = {"XNAS", "XNYS", "XASE", "ARCX", "BATS", "IEXG"}
COMMON_SECURITY_TYPES = {"CS", "ADRC"}
LEGACY_MIN_MCAP = 200_000_000.0
LEGACY_MIN_PRICE = 1.0
EXPANSION_MIN_MCAP = 50_000_000.0
EXPANSION_MIN_PRICE = 5.0
EXPANSION_MIN_MEDIAN_DDV20 = 20_000_000.0
EXPANSION_MIN_ADR20 = 0.025
EXPANSION_MIN_SESSIONS = 10

FRED_SERIES = {
    "DGS3MO": {"label": "米国3カ月金利", "units": "%", "max_age_days": 7, "required": True},
    "DGS2": {"label": "米国2年金利", "units": "%", "max_age_days": 7, "required": True},
    "DGS10": {"label": "米国10年金利", "units": "%", "max_age_days": 7, "required": True},
    "DFII10": {"label": "米国10年実質金利", "units": "%", "max_age_days": 7, "required": True},
    "T10YIE": {"label": "10年期待インフレ", "units": "%", "max_age_days": 7, "required": True},
    "T10Y2Y": {"label": "10年-2年金利差", "units": "%pt", "max_age_days": 7, "required": True},
    "BAMLH0A0HYM2": {"label": "米HY OAS", "units": "%", "max_age_days": 10, "required": True},
    "NFCI": {"label": "Chicago Fed NFCI", "units": "index", "max_age_days": 14, "required": False},
}


class ProviderError(RuntimeError):
    pass


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def load_massive_reference_cache(cache_path: str | Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(Path(cache_path))
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ProviderError("Massive reference cache is unavailable")
    return {
        str(row["ticker"]).upper(): row
        for row in rows if isinstance(row, dict) and row.get("ticker")
    }


def load_massive_grouped_cache(
    cache_path: str | Path,
) -> dict[str, dict[str, dict[str, float | int]]]:
    payload = _read_json(Path(cache_path))
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict) or not sessions:
        raise ProviderError("Massive grouped cache is unavailable")
    return {
        str(day): rows for day, rows in sessions.items()
        if isinstance(rows, dict) and rows
    }


def record_grouped_fallback(cache_path: str | Path, session_date: str, reason: str) -> None:
    path = Path(cache_path)
    payload = _read_json(path)
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict):
        raise ProviderError("Massive grouped cache is unavailable")
    fallbacks = payload.get("fallback_sessions")
    if not isinstance(fallbacks, dict):
        fallbacks = {}
    fallbacks[session_date] = {
        "source": "Yahoo Finance adjusted OHLCV",
        "reason": reason[:240],
    }
    payload["fallback_sessions"] = fallbacks
    _write_json(path, payload)


def _url_with_key(url: str, api_key: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["apiKey"] = api_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 45,
    attempts: int = 5,
) -> dict[str, Any]:
    last_error: Exception | None = None
    last_status: int | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=timeout)
            last_status = response.status_code
            if response.status_code == 429:
                delay = min(float(response.headers.get("Retry-After", 60)), 90.0)
                time.sleep(max(delay, 1.0))
                continue
            if 400 <= response.status_code < 500:
                # Authentication/entitlement errors are deterministic for the
                # request. Retrying them only burns free-plan rate budget.
                raise ProviderError(
                    f"provider request rejected: {_safe_url(url)} "
                    f"(status={response.status_code})"
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderError(f"provider response is not an object: {_safe_url(url)}")
            return payload
        except ProviderError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 12))
    raise ProviderError(
        f"provider request failed after {attempts} attempts: {_safe_url(url)}: "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
        f" (status={last_status if last_status is not None else 'none'})"
    )


def fetch_massive_reference(
    api_key: str,
    cache_path: str | Path,
    *,
    asof_date: str,
    refresh_days: int = 7,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return active US common shares/ADRs from Massive reference data."""
    path = Path(cache_path)
    cached = _read_json(path)
    cached_date = cached.get("asof_date")
    cached_rows = cached.get("rows")
    if isinstance(cached_date, str) and isinstance(cached_rows, list):
        age = (pd.Timestamp(asof_date) - pd.Timestamp(cached_date)).days
        if 0 <= age < refresh_days and cached_rows:
            rows = cached_rows
            return {r["ticker"]: r for r in rows if isinstance(r, dict) and r.get("ticker")}, {
                "status": "READY", "source": "cache", "asof_date": cached_date,
                "eligible_reference_tickers": len(rows), "pages": cached.get("pages"),
            }

    client = requests.Session()
    url = f"{MASSIVE_BASE}/v3/reference/tickers"
    params: dict[str, Any] | None = {
        "market": "stocks", "locale": "us", "active": "true", "date": asof_date,
        "limit": 1000, "sort": "ticker", "order": "asc", "apiKey": api_key,
    }
    rows: list[dict[str, Any]] = []
    pages = 0
    while url:
        payload = _get_json(client, url, params=params)
        pages += 1
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            security_type = str(item.get("type") or "").strip().upper()
            mic = str(item.get("primary_exchange") or "").strip().upper()
            if (
                ticker and item.get("active") is not False
                and str(item.get("market") or "").lower() == "stocks"
                and str(item.get("locale") or "").lower() == "us"
                and str(item.get("currency_name") or "usd").lower() == "usd"
                and security_type in COMMON_SECURITY_TYPES and mic in MAJOR_US_MICS
            ):
                rows.append({
                    "ticker": ticker, "name": str(item.get("name") or ticker),
                    "type": security_type, "primary_exchange": mic,
                    "cik": item.get("cik"), "composite_figi": item.get("composite_figi"),
                })
        next_url = payload.get("next_url")
        url = _url_with_key(str(next_url), api_key) if next_url else ""
        params = None
        if pages > 50:
            raise ProviderError("Massive reference pagination exceeded 50 pages")
    unique = {row["ticker"]: row for row in rows}
    stored = {"schema": "source-mc57.massive-reference.1", "asof_date": asof_date,
              "pages": pages, "rows": sorted(unique.values(), key=lambda r: r["ticker"])}
    _write_json(path, stored)
    return unique, {"status": "READY", "source": "api", "asof_date": asof_date,
                    "eligible_reference_tickers": len(unique), "pages": pages}


def _normalize_grouped_results(
    results: Iterable[Any], allowed_tickers: set[str]
) -> dict[str, dict[str, float | int]]:
    rows: dict[str, dict[str, float | int]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("T") or "").strip().upper()
        close, high, low, volume = (_finite(item.get(k)) for k in ("c", "h", "l", "v"))
        if ticker not in allowed_tickers or close is None or high is None or low is None or volume is None:
            continue
        row: dict[str, float | int] = {
            "c": close, "h": high, "l": low, "v": volume,
        }
        for source in ("o", "vw", "n"):
            value = _finite(item.get(source))
            if value is not None:
                row[source] = int(value) if source == "n" else value
        rows[ticker] = row
    return rows


def fetch_massive_grouped_history(
    api_key: str,
    sessions: Iterable[str],
    allowed_tickers: set[str],
    cache_path: str | Path,
) -> tuple[dict[str, dict[str, dict[str, float | int]]], dict[str, Any]]:
    """Fetch split-adjusted all-market daily bars, with rolling local cache."""
    wanted = list(dict.fromkeys(str(x) for x in sessions))[-20:]
    if not wanted:
        raise ProviderError("no sessions supplied for Massive grouped history")
    path = Path(cache_path)
    cached = _read_json(path)
    stored_sessions = cached.get("sessions") if isinstance(cached.get("sessions"), dict) else {}
    history: dict[str, dict[str, dict[str, float | int]]] = {
        day: rows for day, rows in stored_sessions.items()
        if day in wanted and isinstance(rows, dict)
    }
    client = requests.Session()
    fetched: list[str] = []
    for day in wanted:
        if day in history and history[day]:
            continue
        payload = _get_json(
            client,
            f"{MASSIVE_BASE}/v2/aggs/grouped/locale/us/market/stocks/{day}",
            params={"adjusted": "true", "include_otc": "false", "apiKey": api_key},
        )
        if str(payload.get("status") or "").upper() not in {"OK", "DELAYED"}:
            raise ProviderError(f"Massive grouped status for {day}: {payload.get('status')}")
        rows = _normalize_grouped_results(payload.get("results") or [], allowed_tickers)
        if not rows:
            raise ProviderError(f"Massive grouped response for {day} contained no eligible rows")
        history[day] = rows
        fetched.append(day)
        # Keep successful earlier dates even if the newest date is not entitled yet.
        _write_json(path, {"schema": "source-mc57.massive-grouped.1", "sessions": history})
    _write_json(path, {"schema": "source-mc57.massive-grouped.1", "sessions": history})
    current_count = len(history.get(wanted[-1], {}))
    return history, {
        "status": "READY", "sessions": len(history), "requested_sessions": len(wanted),
        "fetched_sessions": fetched, "latest_session": wanted[-1],
        "latest_eligible_rows": current_count,
    }


def select_expanded_universe(
    broad_rows: list[dict[str, Any]],
    reference: dict[str, dict[str, Any]],
    grouped: dict[str, dict[str, dict[str, float | int]]],
    *,
    target_session: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a broad research universe and annotate, but do not apply, buy filters.

    The legacy market-cap/price route remains available for continuity.  Any
    additional TradingView symbol confirmed as an active US common share/ADR
    by Massive and carrying a current-session bar joins the research universe.
    Liquidity, volatility, price, market-cap, and history thresholds are stored
    as selection metadata only; they must not shrink the measurement universe.
    """
    dates = sorted(d for d in grouped if d <= target_session)[-20:]
    current = grouped.get(target_session, {})
    selected: list[dict[str, Any]] = []
    legacy_count = expansion_count = buy_eligible_count = 0
    candidate_count = 0
    for raw in broad_rows:
        ticker = str(raw.get("ticker") or "").upper()
        price = _finite(raw.get("price"))
        market_cap = _finite(raw.get("market_cap"))
        if not ticker or price is None or market_cap is None:
            continue
        legacy = market_cap >= LEGACY_MIN_MCAP and price >= LEGACY_MIN_PRICE
        observations = [grouped[d][ticker] for d in dates if ticker in grouped[d]]
        ddv = [float(x["c"]) * float(x["v"]) for x in observations if x.get("c") and x.get("v")]
        adr = [
            (float(x["h"]) - float(x["l"])) / float(x["c"])
            for x in observations if x.get("c") and x.get("h") is not None and x.get("l") is not None
        ]
        median_ddv = float(np.median(ddv)) if ddv else None
        median_adr = float(np.median(adr)) if adr else None
        expansion_candidate = not legacy and ticker in reference and ticker in current
        candidate_count += int(expansion_candidate)
        buy_eligible = (
            market_cap >= EXPANSION_MIN_MCAP and price >= EXPANSION_MIN_PRICE
            and ticker in reference and ticker in current
            and len(observations) >= EXPANSION_MIN_SESSIONS
            and median_ddv is not None and median_ddv >= EXPANSION_MIN_MEDIAN_DDV20
            and median_adr is not None and median_adr >= EXPANSION_MIN_ADR20
        )
        if not (legacy or expansion_candidate):
            continue
        row = dict(raw)
        row["median_dollar_volume_20"] = median_ddv
        row["median_adr20"] = median_adr
        row["universe_route"] = "legacy" if legacy else "massive_broad_expansion"
        row["buy_filter_eligible"] = buy_eligible
        row["buy_filter_failures"] = [
            label for label, passed in (
                ("price", price >= EXPANSION_MIN_PRICE),
                ("market_cap", market_cap >= EXPANSION_MIN_MCAP),
                ("massive_reference", ticker in reference),
                ("current_session", ticker in current),
                ("history", len(observations) >= EXPANSION_MIN_SESSIONS),
                ("median_dollar_volume_20", median_ddv is not None and median_ddv >= EXPANSION_MIN_MEDIAN_DDV20),
                ("median_adr20", median_adr is not None and median_adr >= EXPANSION_MIN_ADR20),
            ) if not passed
        ]
        if ticker in reference:
            row["massive_security_type"] = reference[ticker].get("type")
            row["massive_primary_exchange"] = reference[ticker].get("primary_exchange")
        row["source"] = "TradingView fundamentals + Massive reference/grouped daily"
        selected.append(row)
        legacy_count += int(legacy)
        expansion_count += int(expansion_candidate)
        buy_eligible_count += int(buy_eligible)
    selected.sort(key=lambda row: row["ticker"])
    if not selected:
        raise ProviderError("expanded universe resolved to zero tickers")
    covered = sum(1 for row in selected if row["ticker"] in current)
    coverage = covered / len(selected)
    if coverage < 0.95:
        raise ProviderError(
            f"Massive latest-session universe coverage below 95%: {covered}/{len(selected)}={coverage:.4f}"
        )
    return selected, {
        "active_universe": len(selected), "legacy_universe": legacy_count,
        "expansion_candidates": candidate_count, "massive_broad_expansion": expansion_count,
        "buy_filter_eligible": buy_eligible_count,
        "massive_current_covered": covered, "massive_current_coverage": coverage,
        "research_universe_rules": {
            "legacy_route": "market_cap >= 200M and price >= 1",
            "broad_expansion_route": "TradingView row + Massive active US common share/ADR + current-session bar",
            "selection_filters_applied": False,
        },
        "buy_filter_rules": {
            "market_cap_min": EXPANSION_MIN_MCAP, "price_min": EXPANSION_MIN_PRICE,
            "median_dollar_volume_20_min": EXPANSION_MIN_MEDIAN_DDV20,
            "median_adr20_min": EXPANSION_MIN_ADR20,
            "minimum_observed_sessions": EXPANSION_MIN_SESSIONS,
            "security_types": sorted(COMMON_SECURITY_TYPES),
        },
    }


def select_preserved_count_fallback_universe(
    broad_rows: list[dict[str, Any]],
    reference: dict[str, dict[str, Any]],
    grouped: dict[str, dict[str, dict[str, float | int]]],
    *,
    preserved_tickers: Iterable[str],
    target_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep the prior universe count when current Massive bars are unavailable."""
    if target_count <= 0:
        raise ProviderError("Yahoo fallback requires a positive prior universe count")
    cached_session = max(grouped)
    candidates, stats = select_expanded_universe(
        broad_rows, reference, grouped, target_session=cached_session,
    )
    by_ticker = {str(row["ticker"]).upper(): row for row in candidates}
    # A few symbols can be new since the last Massive EOD cache.  Keep the
    # count stable by admitting currently listed TradingView rows that are
    # confirmed active common shares/ADRs by the cached Massive reference.
    for raw in broad_rows:
        ticker = str(raw.get("ticker") or "").upper()
        price, market_cap = _finite(raw.get("price")), _finite(raw.get("market_cap"))
        if (
            not ticker or ticker in by_ticker or ticker not in reference
            or price is None or price < EXPANSION_MIN_PRICE
            or market_cap is None or market_cap < EXPANSION_MIN_MCAP
        ):
            continue
        observations = [
            grouped[day][ticker] for day in sorted(grouped)[-20:]
            if ticker in grouped[day]
        ]
        ddv = [float(row["c"]) * float(row["v"]) for row in observations
               if row.get("c") and row.get("v")]
        adr = [(float(row["h"]) - float(row["l"])) / float(row["c"])
               for row in observations
               if row.get("c") and row.get("h") is not None and row.get("l") is not None]
        row = dict(raw)
        row.update({
            "median_dollar_volume_20": float(np.median(ddv)) if ddv else None,
            "median_adr20": float(np.median(adr)) if adr else None,
            "universe_route": "yahoo_fallback_fill",
            "buy_filter_eligible": False,
            "buy_filter_failures": ["massive_cached_history"],
            "massive_security_type": reference[ticker].get("type"),
            "massive_primary_exchange": reference[ticker].get("primary_exchange"),
        })
        by_ticker[ticker] = row
    prior = list(dict.fromkeys(str(ticker).upper() for ticker in preserved_tickers))
    chosen = [ticker for ticker in prior if ticker in by_ticker]
    chosen_set = set(chosen)
    replacements = sorted(
        (ticker for ticker in by_ticker if ticker not in chosen_set),
        key=lambda ticker: (
            not bool(by_ticker[ticker].get("buy_filter_eligible")),
            -float(by_ticker[ticker].get("market_cap") or 0),
            ticker,
        ),
    )
    chosen.extend(replacements[:max(target_count - len(chosen), 0)])
    if len(chosen) < target_count:
        raise ProviderError(
            f"Yahoo fallback cannot preserve universe count: {len(chosen)}/{target_count}"
        )
    chosen = chosen[:target_count]
    selected = []
    for ticker in chosen:
        row = dict(by_ticker[ticker])
        row["source"] = "TradingView fundamentals + cached Massive reference + Yahoo current OHLCV"
        row["current_session_provider"] = "Yahoo Finance"
        selected.append(row)
    selected.sort(key=lambda row: row["ticker"])
    preserved = sum(ticker in set(prior) for ticker in chosen)
    stats.update({
        "active_universe": len(selected),
        "fallback_mode": "YAHOO_PRESERVED_COUNT",
        "fallback_cached_massive_session": cached_session,
        "fallback_target_count": target_count,
        "fallback_preserved_tickers": preserved,
        "fallback_replacements": target_count - preserved,
    })
    return selected, stats


def grouped_history_from_yahoo_ohlcv(
    ohlcv_csv: str | Path,
    tickers: Iterable[str],
    *,
    target_session: str,
) -> dict[str, dict[str, dict[str, float | int]]]:
    frame = pd.read_csv(ohlcv_csv)
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ProviderError("Yahoo OHLCV cache is missing required columns")
    allowed = {str(ticker).upper() for ticker in tickers}
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = frame["date"].astype(str)
    frame = frame[(frame["ticker"].isin(allowed)) & (frame["date"] <= target_session)]
    dates = sorted(frame["date"].dropna().unique())[-20:]
    frame = frame[frame["date"].isin(dates)]
    history: dict[str, dict[str, dict[str, float | int]]] = {}
    for row in frame.itertuples(index=False):
        values = {name: _finite(getattr(row, name)) for name in ("open", "high", "low", "close", "volume")}
        if any(values[name] is None for name in ("high", "low", "close", "volume")):
            continue
        history.setdefault(str(row.date), {})[str(row.ticker)] = {
            "o": values["open"], "h": values["high"], "l": values["low"],
            "c": values["close"], "v": values["volume"],
        }
    if target_session not in history or not history[target_session]:
        raise ProviderError(f"Yahoo OHLCV has no rows for fallback session {target_session}")
    return history


def compute_massive_market_structure(
    tickers: Iterable[str],
    grouped: dict[str, dict[str, dict[str, float | int]]],
    *,
    target_session: str,
    source: str = "Massive split-adjusted grouped daily aggregates",
) -> dict[str, Any]:
    ticker_list = list(tickers)
    dates = sorted(d for d in grouped if d <= target_session)
    if len(dates) < 2:
        raise ProviderError("Massive market structure requires two completed sessions")
    previous_session = dates[-2]
    current, previous = grouped[dates[-1]], grouped[previous_session]
    advances = declines = unchanged = up4 = down4 = compared = 0
    up_volume = down_volume = 0.0
    for ticker in ticker_list:
        if ticker not in current or ticker not in previous:
            continue
        now, before = _finite(current[ticker].get("c")), _finite(previous[ticker].get("c"))
        volume = _finite(current[ticker].get("v")) or 0.0
        if now is None or before is None or before <= 0:
            continue
        compared += 1
        change = now / before - 1.0
        if change > 0:
            advances += 1
            up_volume += volume
        elif change < 0:
            declines += 1
            down_volume += volume
        else:
            unchanged += 1
        up4 += int(change >= 0.04)
        down4 += int(change <= -0.04)
    if compared == 0:
        raise ProviderError("Massive market structure had no comparable tickers")
    return {
        "status": "READY", "session_date": target_session, "previous_session": previous_session,
        "compared_tickers": compared, "advances": advances, "declines": declines,
        "unchanged": unchanged, "advance_decline_net": advances - declines,
        "advance_decline_ratio": advances / max(declines, 1),
        "up_volume": up_volume, "down_volume": down_volume,
        "up_down_volume_ratio": up_volume / max(down_volume, 1.0),
        "up_4pct": up4, "down_4pct": down4, "four_pct_net": up4 - down4,
        "coverage": compared / max(len(ticker_list), 1),
        "source": source,
    }


def compare_current_closes(
    ohlcv_csv: str | Path,
    grouped: dict[str, dict[str, dict[str, float | int]]],
    *,
    target_session: str,
    universe_count: int,
) -> dict[str, Any]:
    frame = pd.read_csv(ohlcv_csv, usecols=["ticker", "date", "close"])
    frame = frame[frame["date"].astype(str) == target_session]
    yahoo = {str(r.ticker).upper(): float(r.close) for r in frame.itertuples() if _finite(r.close)}
    massive = grouped.get(target_session, {})
    deviations: list[tuple[str, float]] = []
    for ticker, yclose in yahoo.items():
        mclose = _finite(massive.get(ticker, {}).get("c"))
        if mclose is not None and mclose > 0 and yclose > 0:
            deviations.append((ticker, abs(yclose / mclose - 1.0)))
    values = [value for _, value in deviations]
    return {
        "status": "READY" if len(values) / max(universe_count, 1) >= 0.95 else "PARTIAL",
        "compared": len(values), "coverage": len(values) / max(universe_count, 1),
        "median_absolute_deviation": float(np.median(values)) if values else None,
        "p95_absolute_deviation": float(np.quantile(values, .95)) if values else None,
        "over_3pct_count": sum(value > .03 for value in values),
        "largest_deviations": [
            {"ticker": ticker, "absolute_deviation": value}
            for ticker, value in sorted(deviations, key=lambda item: item[1], reverse=True)[:10]
        ],
        "vendors": ["Yahoo Finance adjusted OHLCV", "Massive adjusted grouped daily"],
    }


def fetch_fred_inputs(
    api_key: str,
    *,
    target_session: str,
    generated_at: str,
) -> dict[str, Any]:
    client = requests.Session()
    observation_start = (pd.Timestamp(target_session) - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
    series: dict[str, Any] = {}
    required_ready = 0
    required_total = sum(bool(meta["required"]) for meta in FRED_SERIES.values())
    for series_id, meta in FRED_SERIES.items():
        try:
            payload = _get_json(client, FRED_BASE, params={
                "series_id": series_id, "api_key": api_key, "file_type": "json",
                "observation_start": observation_start, "observation_end": target_session,
                "sort_order": "asc",
            })
            points: list[dict[str, Any]] = []
            for item in payload.get("observations") or []:
                value = _finite(item.get("value")) if isinstance(item, dict) else None
                day = item.get("date") if isinstance(item, dict) else None
                if value is not None and isinstance(day, str):
                    points.append({"date": day, "value": value})
            if not points:
                raise ProviderError("no numeric observations")
            last = points[-1]
            age_days = (pd.Timestamp(target_session) - pd.Timestamp(last["date"])).days
            ready = 0 <= age_days <= int(meta["max_age_days"])
            row = {
                **meta, "status": "READY" if ready else "STALE", "last_date": last["date"],
                "last_value": last["value"], "age_days": age_days,
                "change_5_observations": last["value"] - points[-6]["value"] if len(points) >= 6 else None,
                "change_20_observations": last["value"] - points[-21]["value"] if len(points) >= 21 else None,
                "history": points[-260:],
            }
            required_ready += int(bool(meta["required"]) and ready)
        except Exception as exc:
            row = {**meta, "status": "ERROR", "reason": str(exc)[:240], "history": []}
        series[series_id] = row
    coverage = required_ready / max(required_total, 1)
    status = "READY" if required_ready == required_total else ("PARTIAL" if coverage >= .70 else "ERROR")
    if status == "ERROR":
        raise ProviderError(f"FRED required-series coverage too low: {required_ready}/{required_total}")
    return {
        "schema": "source-mc57.fred.1", "status": status, "session_date": target_session,
        "generated_at": generated_at, "required_ready": required_ready,
        "required_total": required_total, "required_coverage": coverage,
        "source": "Federal Reserve Bank of St. Louis FRED API",
        "series": series,
    }


def secret_from_env(names: Iterable[str]) -> str:
    import os

    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise ProviderError("missing required API key: " + " or ".join(names))
