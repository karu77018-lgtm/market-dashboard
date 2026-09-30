#!/usr/bin/env python3
"""Build a point-in-time dilution magnitude x price-impact study.

Research-only. It joins:
1) Massive 8-K disclosure text (event semantics / disclosed economics)
2) Massive point-in-time ticker overview (shares outstanding / market cap)
3) the repository's frozen event metadata and chart-data price history

It intentionally does not use current free-float as historical truth. Float Shock stays
null until point-in-time float is available.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MASSIVE_BASE = "https://api.massive.com"
DILUTION_CATEGORIES = (
    "public_offering",
    "private_placement",
    "pipe_transaction",
    "warrant_or_conversion",
)
PRIMARY_ISSUANCE_CATEGORIES = {"public_offering", "private_placement", "pipe_transaction"}
BIN_EDGES = (2.0, 5.0, 10.0, 20.0)


def _num(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _money(raw: str | None, unit: str | None) -> float | None:
    value = _num(raw)
    if value is None:
        return None
    scale = {"thousand": 1e3, "million": 1e6, "billion": 1e9}.get((unit or "").lower(), 1.0)
    return value * scale


def _transaction_date_candidate(text: str, filing_date: str | None) -> str | None:
    """Extract a dated transaction/pricing candidate without assuming public availability."""
    if not filing_date:
        return None
    month = (
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    )
    pattern = re.compile(
        rf"\bOn\s+({month}\s+\d{{1,2}},\s+\d{{4}}),"
        r".{0,280}?\b(?:entered into\s+(?:an?\s+)?(?:underwriting|securities purchase|stock purchase|purchase)\s+agreement"
        r"|agreed to\s+(?:issue and sell|sell and issue)"
        r"|(?:launched|priced)\s+(?:the\s+)?(?:registered\s+)?(?:public\s+)?offering)\b",
        re.I,
    )
    filing = dt.date.fromisoformat(filing_date)
    candidates: list[dt.date] = []
    for raw in pattern.findall(text or ""):
        try:
            d = dt.datetime.strptime(raw, "%B %d, %Y").date()
        except ValueError:
            continue
        if filing - dt.timedelta(days=14) <= d <= filing:
            candidates.append(d)
    return min(candidates).isoformat() if candidates else None


def parse_disclosure_terms(text: str, category: str, filing_date: str | None = None) -> dict[str, Any]:
    """Conservative extraction from Massive supporting_text.

    Ambiguous records remain missing instead of being guessed. Transaction dates that
    predate the 8-K are only candidates: they are not assumed to be public/tradable.
    """
    t = re.sub(r"\s+", " ", text or "").strip()
    lower = t.lower()

    # Critical direction guard: sometimes the filer is the BUYER of another issuer's
    # newly issued shares. That is not dilution of the filer (e.g. "X agreed to issue
    # and sell to the Company"). Do not let a broad "Company ... shares" regex cross
    # that clause boundary.
    issuer_mismatch = bool(
        re.search(
            r"pursuant to which\s+(?!the\s+company\b|company\b|we\b|registrant\b)"
            r".{1,180}?\bagreed to\s+issue and sell\s+to\s+(?:the\s+)?Company\b",
            t,
            re.I,
        )
    )

    primary_language = (not issuer_mismatch) and bool(
        re.search(
            r"(?:company|we)\b.{0,180}?"
            r"(?:agreed to|entered into|closed|consummated|issued and sold|sold and issued)"
            r".{0,180}?(?:issue and sell|sell and issue|issued and sold|shares|common stock)",
            t,
            re.I,
        )
        or re.search(r"\b(?:issued and sold|sell and issue|issue and sell)\b.{0,160}\bshares\b", t, re.I)
    )
    selling_holder = bool(re.search(r"\bselling (?:shareholder|stockholder)s?\b", t, re.I))
    secondary_only = selling_holder and not primary_language

    share_matches = [
        _num(x)
        for x in re.findall(
            r"(?:(?:aggregate(?:\s+of)?|up to|approximately)\s+)?"
            r"([0-9][0-9,]*(?:\.\d+)?)\s+(?:shares|common shares)\b",
            t,
            re.I,
        )
    ]
    share_matches = [x for x in share_matches if x and x >= 1]

    base_new_shares = None
    if category in PRIMARY_ISSUANCE_CATEGORIES and primary_language and not secondary_only and share_matches:
        base_new_shares = share_matches[0]

    # Include an explicitly exercised greenshoe/underwriter option in Basic Dilution.
    # An unexercised option remains potential overhang, not issued common shares.
    exercised_option_shares = None
    option_match = re.search(
        r"\boption\b.{0,180}?\bpurchase\s+up\s+to\s+"
        r"(?:an\s+additional\s+)?([0-9][0-9,]*(?:\.\d+)?)\s+(?:additional\s+)?shares\b",
        t,
        re.I,
    )
    option_exercised = bool(
        re.search(r"\boption\b.{0,320}?\b(?:fully exercised|exercised in full)\b", t, re.I)
    )
    if option_match and option_exercised and base_new_shares and not issuer_mismatch:
        exercised_option_shares = _num(option_match.group(1))

    basic_new_shares = (
        base_new_shares + (exercised_option_shares or 0.0)
        if base_new_shares is not None
        else None
    )

    # Explicit shares issuable from warrants / convertibles. Keep separate from issued shares.
    overhang_candidates: list[float] = []
    for pat in (
        r"([0-9][0-9,]*(?:\.\d+)?)\s+shares.{0,120}?\bissuable upon\b.{0,60}?\b(?:exercise|conversion)\b",
        r"\b(?:exercise|conversion)\b.{0,120}?([0-9][0-9,]*(?:\.\d+)?)\s+shares\b",
        r"\bwarrants?\b.{0,120}?\b(?:purchase|acquire)\b.{0,80}?([0-9][0-9,]*(?:\.\d+)?)\s+shares\b",
    ):
        for raw in re.findall(pat, t, re.I):
            value = _num(raw)
            if value and value >= 1:
                overhang_candidates.append(value)
    explicit_overhang_shares = max(overhang_candidates) if overhang_candidates else None

    offer_price = None
    price_patterns = (
        r"\b(?:at\s+a\s+)?price\s+to\s+the\s+public\s+of\s+\$([0-9]+(?:\.[0-9]+)?)",
        r"\boffering\s+price\s+is\s+\$([0-9]+(?:\.[0-9]+)?)",
        r"(?:public offering|offering|purchase|sale)\s+price(?:\s+to\s+the\s+public)?"
        r"(?:\s+(?:of|equal to))?\s*\$([0-9]+(?:\.[0-9]+)?)\s*(?:per share|a share)?",
        r"\bat\s+a\s+(?:purchase|offering)\s+price\s+of\s+\$([0-9]+(?:\.[0-9]+)?)",
        r"\bat\s+\$([0-9]+(?:\.[0-9]+)?)\s+per share\b",
    )
    for pat in price_patterns:
        m = re.search(pat, t, re.I)
        if m:
            offer_price = _num(m.group(1))
            break

    proceeds = []
    for m in re.finditer(
        r"(?:(net|gross|aggregate)\s+)?proceeds[^$]{0,100}\$([0-9][0-9,.]*)\s*(thousand|million|billion)?",
        t,
        re.I,
    ):
        value = _money(m.group(2), m.group(3))
        if value:
            proceeds.append(((m.group(1) or "unspecified").lower(), value))

    gross = next((v for k, v in proceeds if k == "gross"), None)
    net = next((v for k, v in proceeds if k == "net"), None)
    aggregate = next((v for k, v in proceeds if k == "aggregate"), None)
    unspecified = next((v for k, v in proceeds if k == "unspecified"), None)
    explicit_financing = gross or aggregate or net or unspecified
    explicit_financing_basis = (
        "gross_proceeds" if gross
        else "aggregate_proceeds" if aggregate
        else "net_proceeds" if net
        else "unspecified_proceeds" if unspecified
        else None
    )

    # If the disclosed issuer is a counterparty, none of the issuance economics belong
    # to the filer. Keep the record for audit but exclude all dilution terms.
    if issuer_mismatch:
        base_new_shares = None
        exercised_option_shares = None
        basic_new_shares = None
        explicit_overhang_shares = None
        offer_price = None
        explicit_financing = None
        explicit_financing_basis = None

    transaction_date = _transaction_date_candidate(t, filing_date)

    if issuer_mismatch:
        confidence = "high"
    elif secondary_only:
        confidence = "high"
    elif basic_new_shares and offer_price:
        confidence = "high"
    elif basic_new_shares or explicit_financing:
        confidence = "medium"
    elif category == "warrant_or_conversion" and explicit_overhang_shares:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "base_new_shares": base_new_shares,
        "exercised_option_shares": exercised_option_shares,
        "basic_new_shares": basic_new_shares,
        "explicit_overhang_shares": explicit_overhang_shares,
        "offer_price": offer_price,
        "explicit_financing_amount": explicit_financing,
        "explicit_financing_basis": explicit_financing_basis,
        "secondary_only": secondary_only,
        "issuer_mismatch": issuer_mismatch,
        "primary_issuance_language": primary_language,
        "transaction_date_candidate": transaction_date,
        "timing_ambiguous": bool(transaction_date and filing_date and transaction_date < filing_date),
        "extraction_confidence": confidence,
        "text_has_warrant": "warrant" in lower,
        "text_has_convertible": "convertib" in lower,
    }


class MassiveClient:
    def __init__(self, api_key: str, sleep_seconds: float = 13.0):
        self.api_key = api_key
        self.sleep_seconds = max(0.0, sleep_seconds)
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = self.sleep_seconds - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path_or_url.startswith("http"):
            parsed = urllib.parse.urlsplit(path_or_url)
            query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
            query["apiKey"] = self.api_key
            url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
            )
        else:
            query = dict(params or {})
            query["apiKey"] = self.api_key
            url = MASSIVE_BASE + path_or_url + "?" + urllib.parse.urlencode(query)

        for attempt in range(6):
            self._throttle()
            req = urllib.request.Request(url, headers={"User-Agent": "market-dashboard-dilution-study/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    self._last_call = time.time()
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                self._last_call = time.time()
                if exc.code == 429 or 500 <= exc.code < 600:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(60.0, 2.0 ** attempt)
                    time.sleep(delay)
                    continue
                body = exc.read().decode("utf-8", "replace")[:500]
                raise RuntimeError(f"Massive HTTP {exc.code}: {body}") from exc
        raise RuntimeError("Massive request failed after retries")

    def disclosures(self, category: str, start: str, end: str) -> list[dict[str, Any]]:
        params = {
            "tertiary_category": category,
            "filing_date.gte": start,
            "filing_date.lte": end,
            "limit": 1000,
            "sort": "filing_date.asc",
        }
        payload = self.get("/stocks/filings/8-K/vX/disclosures", params)
        rows = list(payload.get("results") or [])
        next_url = payload.get("next_url")
        while next_url:
            payload = self.get(next_url)
            rows.extend(payload.get("results") or [])
            next_url = payload.get("next_url")
        return rows

    def ticker_overview(self, ticker: str, date: str) -> dict[str, Any] | None:
        try:
            payload = self.get(f"/v3/reference/tickers/{urllib.parse.quote(ticker, safe='')}", {"date": date})
        except RuntimeError:
            return None
        result = payload.get("results")
        return result if isinstance(result, dict) else None


def _norm_price_rows(rows: list[list[Any]]) -> list[tuple[str, float, float, float, float, float]]:
    out = []
    for row in rows:
        try:
            out.append(
                (
                    str(row[0])[:10],
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                    float(row[5]),
                )
            )
        except (TypeError, ValueError, IndexError):
            continue
    return out


class PriceStore:
    def __init__(self, repo_root: Path):
        self.root = repo_root / "chart-data"
        self.index = json.loads((self.root / "index.json").read_text())
        self.cache: dict[int, dict[str, Any]] = {}

    def series(self, ticker: str) -> list[tuple[str, float, float, float, float, float]]:
        shard = self.index.get("ticker_to_shard", {}).get(ticker)
        if not isinstance(shard, int):
            return []
        if shard not in self.cache:
            path = self.root / f"shard-{shard:02d}.json"
            self.cache[shard] = json.loads(path.read_text())
        return _norm_price_rows(self.cache[shard].get(ticker) or [])


def _sd(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _event_impact_rows(repo_root: Path, start: str, end: str) -> list[dict[str, Any]]:
    metadata = json.loads((repo_root / "research/event_risk/event-metadata-20260930.json").read_text())
    store = PriceStore(repo_root)
    rows: list[dict[str, Any]] = []
    last_seen: dict[tuple[str, str], dt.date] = {}

    events = [
        e for e in metadata.get("events", [])
        if e.get("category") in DILUTION_CATEGORIES and start <= e.get("filing_date", "") <= end
    ]
    events.sort(key=lambda e: (e.get("filing_date", ""), e.get("ticker", ""), e.get("category", "")))

    for event in events:
        ticker = event.get("ticker")
        date = event.get("filing_date")
        category = event.get("category")
        if not ticker or not date or not category:
            continue
        series = store.series(ticker)
        if not series:
            continue
        prior = [i for i, row in enumerate(series) if row[0] < date]
        future = [i for i, row in enumerate(series) if row[0] > date]
        if not prior or len(future) < 5:
            continue
        pi = prior[-1]
        if pi < 199:
            continue
        close0 = series[pi][4]
        if close0 < 5:
            continue
        ddv20 = statistics.median(series[j][4] * series[j][5] for j in range(pi - 19, pi + 1))
        if ddv20 < 1e7:
            continue

        key = (ticker, category)
        day = dt.date.fromisoformat(date)
        if key in last_seen and (day - last_seen[key]).days < 30:
            continue
        last_seen[key] = day

        daily = [(series[j][4] / series[j - 1][4] - 1) * 100 for j in range(pi - 19, pi + 1)]
        vol20 = _sd(daily)
        if not vol20 or vol20 <= 0:
            continue

        fi = future[0]
        ret1 = (series[fi][4] / close0 - 1) * 100
        ret5 = (series[future[4]][4] / close0 - 1) * 100
        ret20 = None
        if len(future) >= 20:
            ret20 = (series[future[19]][4] / close0 - 1) * 100
        rows.append(
            {
                "ticker": ticker,
                "filing_date": date,
                "category": category,
                "accession_number": event.get("accession_number"),
                "prior_session": series[pi][0],
                "pre_close": close0,
                "ddv20": ddv20,
                "vol20_pct": vol20,
                "gap_pct": (series[fi][1] / close0 - 1) * 100,
                "ret1_pct": ret1,
                "ret5_pct": ret5,
                "ret20_pct": ret20,
            }
        )
    return rows


def _disclosure_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    out = {}
    for row in rows:
        tickers = row.get("tickers") or []
        if isinstance(tickers, str):
            try:
                tickers = json.loads(tickers)
            except json.JSONDecodeError:
                tickers = [tickers]
        for ticker in tickers:
            if ticker:
                out[(str(row.get("accession_number") or ""), str(row.get("tertiary_category") or ""), str(ticker))] = row
    return out


def _bin(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    if value < BIN_EDGES[0]:
        return "<2%"
    if value < BIN_EDGES[1]:
        return "2-5%"
    if value < BIN_EDGES[2]:
        return "5-10%"
    if value < BIN_EDGES[3]:
        return "10-20%"
    return "20%+"


def _q(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    x = (len(s) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows)}
    for field in ("gap_pct", "ret1_pct", "ret5_pct", "ret20_pct"):
        vals = [float(r[field]) for r in rows if r.get(field) is not None and math.isfinite(float(r[field]))]
        out[field] = {
            "n": len(vals),
            "mean": statistics.fmean(vals) if vals else None,
            "p10": _q(vals, 0.10),
            "median": _q(vals, 0.50),
            "p_negative": statistics.fmean([v < 0 for v in vals]) if vals else None,
        }
    return out


def _curve(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    order = ("<2%", "2-5%", "5-10%", "10-20%", "20%+")
    return {
        b: _stats([r for r in rows if _bin(r.get(field)) == b])
        for b in order
    }


def build(repo_root: Path, client: MassiveClient, start: str, end: str, max_events: int = 0) -> dict[str, Any]:
    impact_rows = _event_impact_rows(repo_root, start, end)
    if max_events:
        impact_rows = impact_rows[:max_events]

    disclosures: list[dict[str, Any]] = []
    for category in DILUTION_CATEGORIES:
        disclosures.extend(client.disclosures(category, start, end))
    dmap = _disclosure_map(disclosures)

    overview_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    enriched = []
    for row in impact_rows:
        key = (str(row.get("accession_number") or ""), row["category"], row["ticker"])
        disclosure = dmap.get(key)
        text = str(disclosure.get("supporting_text") or "") if disclosure else ""
        terms = parse_disclosure_terms(text, row["category"], row["filing_date"])

        overview = None
        needs_overview = bool(
            terms["basic_new_shares"]
            or terms["explicit_overhang_shares"]
            or terms["offer_price"]
            or terms["explicit_financing_amount"]
        )
        if needs_overview:
            okey = (row["ticker"], row["prior_session"])
            if okey not in overview_cache:
                overview_cache[okey] = client.ticker_overview(*okey)
            overview = overview_cache[okey]

        share_class_shares = None
        weighted_shares = None
        market_cap = None
        if overview:
            share_class_shares = overview.get("share_class_shares_outstanding")
            weighted_shares = overview.get("weighted_shares_outstanding")
            market_cap = overview.get("market_cap")
        share_class_shares = float(share_class_shares) if share_class_shares not in (None, "") else None
        weighted_shares = float(weighted_shares) if weighted_shares not in (None, "") else None
        # Canonical Basic Dilution denominator: the same listed share class where available.
        # Weighted shares are preserved as a sensitivity because Massive defines them as
        # assuming other share classes are converted into this class.
        pre_shares = share_class_shares or weighted_shares
        market_cap = float(market_cap) if market_cap not in (None, "") else None
        if not market_cap and weighted_shares:
            market_cap = weighted_shares * row["pre_close"]
        elif not market_cap and pre_shares:
            market_cap = pre_shares * row["pre_close"]

        basic_pct = (
            100.0 * terms["basic_new_shares"] / pre_shares
            if terms["basic_new_shares"] and pre_shares and pre_shares > 0
            else 0.0 if terms["secondary_only"] and pre_shares
            else None
        )
        basic_pct_weighted = (
            100.0 * terms["basic_new_shares"] / weighted_shares
            if terms["basic_new_shares"] and weighted_shares and weighted_shares > 0
            else 0.0 if terms["secondary_only"] and weighted_shares
            else None
        )
        overhang_shares = None
        if terms["basic_new_shares"] or terms["explicit_overhang_shares"]:
            overhang_shares = (terms["basic_new_shares"] or 0.0) + (terms["explicit_overhang_shares"] or 0.0)
        fully_diluted_pct = (
            100.0 * overhang_shares / pre_shares
            if overhang_shares and pre_shares and pre_shares > 0
            else basic_pct
        )

        financing = terms["explicit_financing_amount"]
        financing_basis = terms["explicit_financing_basis"]
        if not financing and terms["basic_new_shares"] and terms["offer_price"]:
            financing = terms["basic_new_shares"] * terms["offer_price"]
            financing_basis = "derived_shares_x_offer_price"

        financing_mcap_pct = 100.0 * financing / market_cap if financing and market_cap and market_cap > 0 else None
        offer_discount_pct = (
            100.0 * (terms["offer_price"] / row["pre_close"] - 1)
            if terms["offer_price"] and row["pre_close"] > 0
            else None
        )

        enriched.append(
            {
                **row,
                "disclosure_text_found": bool(text),
                "base_new_shares": terms["base_new_shares"],
                "exercised_option_shares": terms["exercised_option_shares"],
                "basic_new_shares": terms["basic_new_shares"],
                "explicit_overhang_shares": terms["explicit_overhang_shares"],
                "pre_share_class_shares": share_class_shares,
                "pre_weighted_shares": weighted_shares,
                "pit_market_cap": market_cap,
                "basic_dilution_pct": basic_pct,
                "basic_dilution_pct_weighted_sensitivity": basic_pct_weighted,
                "fully_diluted_overhang_pct": fully_diluted_pct,
                "financing_amount": financing,
                "financing_amount_basis": financing_basis,
                "financing_market_cap_pct": financing_mcap_pct,
                "offer_price": terms["offer_price"],
                "offer_discount_pct": offer_discount_pct,
                "float_shock_pct": None,
                "float_shock_status": "PIT_FLOAT_UNAVAILABLE",
                "secondary_only": terms["secondary_only"],
                "issuer_mismatch": terms["issuer_mismatch"],
                "transaction_date_candidate": terms["transaction_date_candidate"],
                "timing_ambiguous": terms["timing_ambiguous"],
                "timing_status": "NEEDS_PUBLICATION_TIMESTAMP" if terms["timing_ambiguous"] else "FILING_DATE_ACCEPTED",
                "extraction_confidence": terms["extraction_confidence"],
                "supporting_text": text,
            }
        )

    modeled = [
        r for r in enriched
        if not r["secondary_only"]
        and not r["issuer_mismatch"]
        and not r["timing_ambiguous"]
        and r["basic_dilution_pct"] is not None
    ]
    coverage = {
        "impact_rows": len(enriched),
        "disclosure_text_found": sum(r["disclosure_text_found"] for r in enriched),
        "basic_dilution_available": sum(r["basic_dilution_pct"] is not None for r in enriched),
        "fully_diluted_overhang_available": sum(r["fully_diluted_overhang_pct"] is not None for r in enriched),
        "financing_market_cap_available": sum(r["financing_market_cap_pct"] is not None for r in enriched),
        "offer_discount_available": sum(r["offer_discount_pct"] is not None for r in enriched),
        "secondary_only": sum(r["secondary_only"] for r in enriched),
        "issuer_mismatch": sum(r["issuer_mismatch"] for r in enriched),
        "timing_ambiguous": sum(r["timing_ambiguous"] for r in enriched),
        "basic_curve_eligible": len(modeled),
        "high_confidence": sum(r["extraction_confidence"] == "high" for r in enriched),
        "float_shock_available": 0,
    }
    return {
        "version": "dilution-magnitude-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_range": [start, end],
        "source": {
            "events": "Massive 8-K disclosures + frozen event-risk metadata",
            "shares_market_cap": "Massive point-in-time ticker overview",
            "prices": "repository chart-data; same event-study filters/cooldown as event-risk-study",
        },
        "definitions": {
            "basic_dilution_pct": "newly issued common shares / point-in-time pre-event same-class shares outstanding * 100; weighted shares are fallback only",
            "basic_dilution_pct_weighted_sensitivity": "newly issued common shares / Massive weighted shares outstanding * 100; robustness field, not primary bin",
            "fully_diluted_overhang_pct": "(new common shares + explicitly quantified warrant/convertible shares) / point-in-time pre-event same-class shares (weighted fallback) * 100",
            "timing_guard": "if a transaction/pricing date predates the 8-K filing but public availability is not proven, the row is excluded from impact curves pending a publication timestamp",
            "financing_market_cap_pct": "reported/derived financing amount / point-in-time pre-event market cap * 100",
            "offer_discount_pct": "offer price / pre-event close - 1",
            "float_shock_pct": "reserved; not backfilled with today's float because historical PIT float is unavailable",
        },
        "filters": [
            ">=200 prior sessions",
            "pre-event close >= $5",
            "DDV20 >= $10M",
            "30-calendar-day same ticker/category cooldown",
        ],
        "coverage": coverage,
        "basic_dilution_curve": _curve(modeled, "basic_dilution_pct"),
        "fully_diluted_overhang_curve": _curve(
            [
                r for r in enriched
                if not r["secondary_only"] and not r["issuer_mismatch"] and not r["timing_ambiguous"]
                and r["fully_diluted_overhang_pct"] is not None
            ],
            "fully_diluted_overhang_pct",
        ),
        "financing_market_cap_curve": _curve(
            [
                r for r in enriched
                if not r["secondary_only"] and not r["issuer_mismatch"] and not r["timing_ambiguous"]
                and r["financing_market_cap_pct"] is not None
            ],
            "financing_market_cap_pct",
        ),
        "rows": enriched,
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    c = payload["coverage"]
    lines = [
        "# Dilution magnitude v1 — 2026-09-30",
        "",
        "This is the first magnitude-aware layer on top of the validated 60D dilution hazard.",
        "Production MC57/V38 logic is unchanged.",
        "",
        "## Coverage",
        f"- Impact-qualified dilution events: {c['impact_rows']}",
        f"- 8-K supporting text matched: {c['disclosure_text_found']}",
        f"- Basic dilution % available: {c['basic_dilution_available']}",
        f"- Financing / market cap available: {c['financing_market_cap_available']}",
        f"- Offer discount available: {c['offer_discount_available']}",
        f"- Secondary-only offerings identified: {c['secondary_only']}",
        f"- Counterparty-issuer mismatches excluded: {c['issuer_mismatch']}",
        f"- Timing-ambiguous rows excluded from curves: {c['timing_ambiguous']}",
        f"- Basic curve eligible after quality guards: {c['basic_curve_eligible']}",
        "- Historical Float Shock: intentionally unavailable until point-in-time float exists.",
        "",
        "## Basic dilution × realized return",
        "",
        "| Basic dilution | n | Gap median | 1D median | 5D median | 5D p10 | 20D median |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for bucket, stat in payload["basic_dilution_curve"].items():
        def f(field: str, key: str = "median") -> str:
            v = stat[field].get(key)
            return "—" if v is None else f"{v:.2f}%"
        lines.append(
            f"| {bucket} | {stat['n']} | {f('gap_pct')} | {f('ret1_pct')} | "
            f"{f('ret5_pct')} | {f('ret5_pct','p10')} | {f('ret20_pct')} |"
        )
    lines += [
        "",
        "## Interpretation rules",
        "- Do not treat dilution % as the price impact itself.",
        "- Offer discount and financing/market-cap are separate explanatory variables.",
        "- Selling-shareholder-only offerings are excluded from primary dilution bins.",
        "- Counterparty issuances (the filer is the buyer, not issuer) are excluded.",
        "- Rows whose transaction date predates filing are withheld from impact curves until public/tradable time is resolved.",
        "- Net proceeds are tagged as such; when exact gross proceeds are unavailable, the amount basis is preserved.",
        "- Missing text/terms stay missing; the parser does not fabricate a value.",
        "",
        "## Next layer",
        "Join cash runway / burn when a point-in-time financial source is entitled, then add Expected Move + pre-earnings Expectation Load.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-09-21")
    ap.add_argument("--sleep", type=float, default=13.0)
    ap.add_argument("--max-events", type=int, default=0)
    ap.add_argument("--output", default="research/event_risk/dilution-magnitude-v1.json")
    ap.add_argument("--report", default="maintenance/dilution-magnitude-v1-20260930.md")
    args = ap.parse_args()

    key = os.getenv("MASSIVE_API_KEY") or os.getenv("MASSIVE_KEY") or os.getenv("POLYGON_API_KEY")
    if not key:
        raise SystemExit("MASSIVE_API_KEY is required")

    root = Path(args.repo_root).resolve()
    payload = build(root, MassiveClient(key, args.sleep), args.start, args.end, args.max_events)
    output = root / args.output
    report = root / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=False, allow_nan=False) + "\n")
    write_report(payload, report)
    print(json.dumps({"ok": True, "version": payload["version"], "coverage": payload["coverage"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
