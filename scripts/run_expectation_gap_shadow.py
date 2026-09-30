#!/usr/bin/env python3
"""Universal Expectation Gap research shadow.

Research-only, isolated from MC57/V38 production logic.

Stage 1 (all dashboard names):
- Build a deterministic, cross-sectional Expectation Load baseline from price/RS/extension.
- Stratify leaders into low / middle / high expectation-load research cohorts.

Stage 2 (bounded candidates only):
- Pull point-in-time public evidence from Massive in batch: news, 8-K disclosures,
  Form 4, short interest, and short volume.
- Ask Jev English semantic questions only. Jev does not calculate returns, ranks,
  probabilities, or EV math.
- Persist only derived features and hashes, never vendor article/disclosure text.

The combined labels are provisional research labels, not production ranking signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from run_jev_live_shadow import (
    ShadowRunError,
    embedded_json,
    fetch_news_bulk,
    parse_timestamp,
    safe_number,
    utc_iso,
)

MASSIVE_BASE = "https://api.massive.com"
DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"

DISCLOSURE_CATEGORIES = (
    "quarterly_results",
    "guidance_issuance_or_update",
    "guidance_withdrawal",
    "significant_contract_award",
    "partnership_or_collaboration",
    "regulatory_decision",
    "public_offering",
    "private_placement",
    "warrant_or_conversion",
)

DEFAULT_COMPONENTS = (
    "rs21",
    "rs63",
    "ret21",
    "high_proximity",
    "extension50",
    "relative_volume",
)


def canonical_hash(value: Any) -> str:
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    """Mid-rank percentile in [0, 100], deterministic on ties."""
    ordered = sorted((v, k) for k, v in values.items())
    n = len(ordered)
    if not n:
        return {}
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][0] == ordered[i][0]:
            j += 1
        mid = (i + j - 1) / 2
        pct = 50.0 if n == 1 else 100.0 * mid / (n - 1)
        for _, key in ordered[i:j]:
            out[key] = pct
        i = j
    return out


def build_expectation_load(details: dict[str, Any]) -> dict[str, dict[str, Any]]:
    eligible: dict[str, dict[str, Any]] = {}
    raw_fields: dict[str, dict[str, float]] = {
        "ret21": {},
        "high_proximity": {},
        "extension50": {},
        "relative_volume": {},
    }

    for ticker, d in details.items():
        if not isinstance(d, dict):
            continue
        px = _finite(d.get("px"))
        rs21 = _finite(d.get("rs21"))
        rs63 = _finite(d.get("rs"))
        rs189 = _finite(d.get("rs189"))
        if d.get("off") or px is None or px < 5 or rs21 is None or rs63 is None or rs189 is None:
            continue
        ret21 = _finite(d.get("d21"))
        d52 = _finite(d.get("d52"))
        v50 = _finite(d.get("v50"))
        rv = _finite(d.get("rv"))
        eligible[ticker] = d
        if ret21 is not None:
            raw_fields["ret21"][ticker] = ret21
        if d52 is not None:
            raw_fields["high_proximity"][ticker] = d52  # closer to zero / positive = higher load
        if v50 is not None:
            raw_fields["extension50"][ticker] = v50
        if rv is not None:
            raw_fields["relative_volume"][ticker] = rv

    pct_fields = {name: percentile_map(vals) for name, vals in raw_fields.items()}
    rows: dict[str, dict[str, Any]] = {}
    raw_scores: dict[str, float] = {}
    for ticker, d in eligible.items():
        components = {
            "rs21": _finite(d.get("rs21")),
            "rs63": _finite(d.get("rs")),
            "ret21": pct_fields["ret21"].get(ticker),
            "high_proximity": pct_fields["high_proximity"].get(ticker),
            "extension50": pct_fields["extension50"].get(ticker),
            "relative_volume": pct_fields["relative_volume"].get(ticker),
        }
        present = [float(v) for v in components.values() if v is not None]
        baseline = statistics.fmean(present) if present else None
        if baseline is not None:
            raw_scores[ticker] = baseline
        rows[ticker] = {
            "ticker": ticker,
            "price": _finite(d.get("px")),
            "rs21": _finite(d.get("rs21")),
            "rs63": _finite(d.get("rs")),
            "rs189": _finite(d.get("rs189")),
            "ret21_pct": _finite(d.get("d21")),
            "distance_52w_high_pct": _finite(d.get("d52")),
            "extension_50ma_pct": _finite(d.get("v50")),
            "relative_volume": _finite(d.get("rv")),
            "sector": d.get("sec"),
            "subtheme": d.get("sth"),
            "market_cap_band": d.get("cap"),
            "expectation_components_pctile": components,
            "expectation_load_raw": baseline,
        }

    final_pct = percentile_map(raw_scores)
    for ticker, row in rows.items():
        row["expectation_load_pctile"] = final_pct.get(ticker)
    return rows


def select_stratified_candidates(
    rows: dict[str, dict[str, Any]], max_candidates: int
) -> list[dict[str, Any]]:
    leaders = [
        r for r in rows.values()
        if r.get("expectation_load_pctile") is not None
        and (r.get("rs63") or 0) >= 70
        and (r.get("rs189") or 0) >= 70
    ]
    if not leaders:
        return []
    max_candidates = max(3, max_candidates)
    low_n = max_candidates // 3
    high_n = max_candidates // 3
    mid_n = max_candidates - low_n - high_n

    low = sorted(leaders, key=lambda r: (r["expectation_load_pctile"], -r["rs189"], r["ticker"]))[:low_n]
    high = sorted(leaders, key=lambda r: (-r["expectation_load_pctile"], -r["rs189"], r["ticker"]))[:high_n]
    used = {r["ticker"] for r in low + high}
    middle_pool = [r for r in leaders if r["ticker"] not in used]
    middle = sorted(
        middle_pool,
        key=lambda r: (abs(r["expectation_load_pctile"] - 50), -r["rs189"], r["ticker"]),
    )[:mid_n]

    tagged = []
    for cohort, group in (("low_load", low), ("mid_load", middle), ("high_load", high)):
        for row in group:
            tagged.append({**row, "research_cohort": cohort})
    return tagged


class MassivePacer:
    def __init__(self, api_key: str, min_interval: float):
        self.api_key = api_key
        self.min_interval = max(0.0, min_interval)
        self.last_at: float | None = None
        self.session = requests.Session()

    def _pace(self) -> None:
        if self.last_at is not None:
            delay = self.min_interval - (time.monotonic() - self.last_at)
            if delay > 0:
                time.sleep(delay)

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("https://") else MASSIVE_BASE + path_or_url
        if path_or_url.startswith("https://"):
            parsed = urlparse(path_or_url)
            if parsed.netloc != "api.massive.com":
                raise ShadowRunError("Unexpected Massive pagination host")
        query = dict(params or {})
        query["apiKey"] = self.api_key
        for attempt in range(5):
            self._pace()
            self.last_at = time.monotonic()
            try:
                response = self.session.get(url, params=query, timeout=45)
            except requests.RequestException as exc:
                if attempt < 4:
                    time.sleep(min(2**attempt, 20))
                    continue
                raise ShadowRunError(f"Massive request failed: {type(exc).__name__}") from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 4:
                    time.sleep(min(2**attempt, 30))
                    continue
            if response.status_code == 410:
                raise ShadowRunError("Massive endpoint is in HTTP 410 brownout")
            if response.status_code >= 400:
                raise ShadowRunError(f"Massive request rejected: HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ShadowRunError("Massive response was not a JSON object")
            return payload
        raise ShadowRunError("Massive request failed after retries")

    def paged(self, path: str, params: dict[str, Any], max_pages: int = 20) -> list[dict[str, Any]]:
        payload = self.get(path, params)
        rows = list(payload.get("results") or [])
        pages = 1
        next_url = payload.get("next_url")
        while next_url:
            if pages >= max_pages:
                raise ShadowRunError(f"Massive pagination exceeded {max_pages} pages for {path}")
            payload = self.get(str(next_url))
            rows.extend(payload.get("results") or [])
            next_url = payload.get("next_url")
            pages += 1
        return [r for r in rows if isinstance(r, dict)]


def chunks(items: list[str], size: int = 30) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_disclosures(
    client: MassivePacer,
    tickers: list[str],
    start_date: str,
) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in chunks(tickers):
        tickers_filter = ",".join(group)
        for category in DISCLOSURE_CATEGORIES:
            rows = client.paged(
                "/stocks/filings/8-K/vX/disclosures",
                {
                    "tickers.any_of": tickers_filter,
                    "filing_date.gte": start_date,
                    "tertiary_category": category,
                    "limit": 1000,
                    "sort": "filing_date.desc",
                },
                max_pages=10,
            )
            for row in rows:
                for ticker in row.get("tickers") or []:
                    ticker = str(ticker).upper()
                    if ticker not in group:
                        continue
                    by[ticker].append(
                        {
                            "source": "massive_8k_disclosure",
                            "filing_date": row.get("filing_date"),
                            "category": row.get("tertiary_category"),
                            "supporting_text": " ".join(str(row.get("supporting_text") or "").split())[:2400],
                            "accession_number": row.get("accession_number"),
                        }
                    )
    for ticker in by:
        by[ticker].sort(key=lambda r: str(r.get("filing_date") or ""), reverse=True)
        by[ticker] = by[ticker][:10]
    return dict(by)


def classify_form4_row(row: dict[str, Any]) -> str:
    code = str(row.get("transaction_code") or "").upper()
    acquired = str(row.get("transaction_acquired_disposed") or "").upper()
    plan = row.get("aff_10b5_one") is True
    price = _finite(row.get("transaction_price_per_share")) or 0.0
    security_type = str(row.get("security_type") or "").lower()
    title = str(row.get("security_title") or "").lower()

    if code == "P" and acquired == "A" and price > 0 and "derivative" not in security_type:
        return "open_market_purchase"
    if code == "S" and acquired == "D" and price > 0:
        return "scheduled_sale_10b5_1" if plan else "discretionary_sale"
    if code == "F":
        return "tax_withholding"
    if code in {"A", "M"} or "restricted stock" in title or "rsu" in title:
        return "compensation_or_exercise"
    if code == "G":
        return "gift"
    return "other"


def fetch_form4(
    client: MassivePacer, tickers: list[str], start_date: str
) -> dict[str, dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for group in chunks(tickers):
        rows = client.paged(
            "/stocks/filings/vX/form-4",
            {
                "tickers.any_of": ",".join(group),
                "filing_date.gte": start_date,
                "limit": 5000,
                "sort": "filing_date.desc",
            },
            max_pages=10,
        )
        temp: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            rtickers = row.get("tickers") or []
            for ticker in rtickers:
                ticker = str(ticker).upper()
                if ticker in group:
                    temp[ticker].append(row)
        for ticker in group:
            cats: dict[str, int] = defaultdict(int)
            values: dict[str, float] = defaultdict(float)
            people: dict[str, set[str]] = defaultdict(set)
            for row in temp.get(ticker, []):
                cat = classify_form4_row(row)
                cats[cat] += 1
                v = _finite(row.get("transaction_value"))
                if v:
                    values[cat] += abs(v)
                owner = str(row.get("owner_name") or "").strip()
                if owner:
                    people[cat].add(owner)
            agg[ticker] = {
                "filings": len(temp.get(ticker, [])),
                "counts": dict(cats),
                "values_usd": {k: round(v, 2) for k, v in values.items()},
                "distinct_people": {k: len(v) for k, v in people.items()},
            }
    return agg


def fetch_short_interest(
    client: MassivePacer, tickers: list[str], start_date: str
) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in chunks(tickers):
        rows = client.paged(
            "/stocks/v1/short-interest",
            {
                "ticker.any_of": ",".join(group),
                "settlement_date.gte": start_date,
                "limit": 5000,
                "sort": "settlement_date.desc",
            },
            max_pages=10,
        )
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            if ticker in group:
                by[ticker].append(row)
    out = {}
    for ticker in tickers:
        rows = sorted(by.get(ticker, []), key=lambda r: str(r.get("settlement_date") or ""), reverse=True)
        latest = rows[0] if rows else None
        prev = rows[1] if len(rows) > 1 else None
        latest_si = _finite(latest.get("short_interest")) if latest else None
        prev_si = _finite(prev.get("short_interest")) if prev else None
        change = (
            100 * (latest_si / prev_si - 1)
            if latest_si is not None and prev_si not in (None, 0)
            else None
        )
        out[ticker] = {
            "latest_settlement_date": latest.get("settlement_date") if latest else None,
            "short_interest": latest_si,
            "short_interest_change_pct": change,
            "days_to_cover": _finite(latest.get("days_to_cover")) if latest else None,
            "prior_days_to_cover": _finite(prev.get("days_to_cover")) if prev else None,
        }
    return out


def fetch_short_volume(
    client: MassivePacer, tickers: list[str], start_date: str
) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in chunks(tickers):
        rows = client.paged(
            "/stocks/v1/short-volume",
            {
                "ticker.any_of": ",".join(group),
                "date.gte": start_date,
                "limit": 5000,
                "sort": "date.desc",
            },
            max_pages=10,
        )
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            if ticker in group:
                by[ticker].append(row)
    out = {}
    for ticker in tickers:
        rows = sorted(by.get(ticker, []), key=lambda r: str(r.get("date") or ""), reverse=True)
        ratios = [_finite(r.get("short_volume_ratio")) for r in rows[:5]]
        ratios = [r for r in ratios if r is not None]
        out[ticker] = {
            "latest_date": rows[0].get("date") if rows else None,
            "short_volume_ratio_5d_mean": statistics.fmean(ratios) if ratios else None,
            "observations": len(ratios),
        }
    return out


def clean_news(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "published_utc": d.get("published_utc"),
            "title": d.get("title"),
            "description": d.get("description"),
            "publisher": d.get("publisher"),
        }
        for d in documents[:6]
    ]


def jev_state(
    row: dict[str, Any],
    *,
    asof: str,
    news: list[dict[str, Any]],
    disclosures: list[dict[str, Any]],
    form4: dict[str, Any],
    short_interest: dict[str, Any],
    short_volume: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "universal-expectation-gap-state-v1",
        "ticker": row["ticker"],
        "as_of": asof,
        "research_cohort": row.get("research_cohort"),
        "market_expectation_context": {
            "expectation_load_pctile": row.get("expectation_load_pctile"),
            "expectation_load_method": "equal-weight research baseline; not validated for production",
            "rs21_percentile": row.get("rs21"),
            "rs63_percentile": row.get("rs63"),
            "rs189_percentile": row.get("rs189"),
            "return_21d_pct": row.get("ret21_pct"),
            "distance_from_52w_high_pct": row.get("distance_52w_high_pct"),
            "extension_from_50ma_pct": row.get("extension_50ma_pct"),
            "relative_volume": row.get("relative_volume"),
        },
        "company_context": {
            "sector": row.get("sector"),
            "subtheme": row.get("subtheme"),
            "market_cap_band": row.get("market_cap_band"),
        },
        "positioning": {
            "form4_summary": form4,
            "short_interest": short_interest,
            "short_volume": short_volume,
        },
        "evidence": {
            "recent_news": clean_news(news),
            "recent_8k_disclosures": disclosures[:10],
        },
        "instructions": [
            "Answer the typed questions in English.",
            "Use only the supplied evidence and structured context.",
            "Do not infer that an event is absent merely because it is not supplied.",
            "Price, relative strength, extension, and volume are market-expectation context, not proof of business quality.",
            "Do not predict the stock price. Assess underlying business change, novelty, persistence, and how much favorable information appears embedded in expectations.",
            "Do not treat RSU grants, vesting, option exercises, tax withholding, gifts, or Rule 10b5-1 scheduled sales as discretionary insider conviction.",
            "Do not interpret short volume alone as directional conviction.",
            "When evidence is weak or missing, explicitly use the insufficient/weak choices rather than inventing facts.",
        ],
    }


def evaluate_jev(
    session: requests.Session,
    url: str,
    secret: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    runs: int,
    timeout: int,
) -> dict[str, Any]:
    response = session.post(
        url,
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "state": state,
            "questions": questions,
            "runs": runs,
            "persist": False,
            "responseMode": "json",
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise ShadowRunError(f"Jev rejected {state['ticker']}: HTTP {response.status_code}")
    payload = response.json()
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ShadowRunError(f"Jev aggregate missing for {state['ticker']}")
    return {
        "aggregate": aggregate,
        "gateway_cost_usd": _finite(payload.get("gatewayCostUsd")),
        "duration_ms": safe_number(payload.get("durationMs")),
    }


def prob(agg: dict[str, Any], qid: str) -> float | None:
    row = agg.get(qid)
    return _finite(row.get("probabilityMean")) if isinstance(row, dict) else None


def choice(agg: dict[str, Any], qid: str) -> str | None:
    row = agg.get(qid)
    value = row.get("majorityChoice") if isinstance(row, dict) else None
    return str(value) if value is not None else None


def derive_label(expectation_load: float | None, agg: dict[str, Any]) -> str:
    quality = choice(agg, "EG08_evidence_quality")
    pos = prob(agg, "EG01_positive_business_change")
    neg = prob(agg, "EG02_negative_business_change")
    persist = prob(agg, "EG03_persistent_change")
    novelty = prob(agg, "EG04_information_novelty")
    embedded = prob(agg, "EG05_expectations_already_embedded")
    sell_news = prob(agg, "EG07_sell_the_news_risk")

    if quality in {"weak", "insufficient", None}:
        return "INSUFFICIENT_EVIDENCE"
    if neg is not None and neg >= 0.65 and (pos is None or neg > pos):
        return "NEGATIVE_CHANGE"
    if (
        pos is not None and pos >= 0.65
        and persist is not None and persist >= 0.55
        and novelty is not None and novelty >= 0.55
    ):
        if (
            (embedded is not None and embedded >= 0.65)
            or (sell_news is not None and sell_news >= 0.65)
            or (expectation_load is not None and expectation_load >= 70)
        ):
            return "POSITIVE_BUT_PRICED"
        if (
            embedded is not None and embedded <= 0.50
            and expectation_load is not None and expectation_load <= 50
        ):
            return "UNDERAPPRECIATED_POSITIVE"
        return "POSITIVE_WATCH"
    return "MIXED_OR_NEUTRAL"


def derived_features(agg: dict[str, Any]) -> dict[str, Any]:
    ids = (
        "EG01_positive_business_change",
        "EG02_negative_business_change",
        "EG03_persistent_change",
        "EG04_information_novelty",
        "EG05_expectations_already_embedded",
        "EG06_followthrough_potential",
        "EG07_sell_the_news_risk",
    )
    out = {qid: prob(agg, qid) for qid in ids}
    out.update(
        {
            "evidence_quality": choice(agg, "EG08_evidence_quality"),
            "business_direction": choice(agg, "EG09_business_direction"),
            "insider_signal": choice(agg, "EG10_insider_signal"),
            "positioning_asymmetry": choice(agg, "EG11_positioning_asymmetry"),
        }
    )
    return out


def report(payload: dict[str, Any]) -> str:
    cov = payload["coverage"]
    lines = [
        "# Universal Expectation Gap v1 — 2026-09-30",
        "",
        "Research shadow only. MC57/V38 production rules are unchanged.",
        "",
        "## Design",
        "- Python: deterministic cross-sectional Expectation Load, batching, labels, and future backtests.",
        "- Jev: English-only semantic interpretation of business change, novelty, persistence, and embedded expectations.",
        "- Massive: news, 8-K disclosure text, Form 4, short interest, and short volume.",
        "- No direct Jev stock-price forecast.",
        "",
        "## Current coverage",
        f"- Dashboard universe: {cov['dashboard_universe']}",
        f"- Deterministic eligible universe: {cov['expectation_load_eligible']}",
        f"- Stratified Jev candidates: {cov['selected_candidates']}",
        f"- Jev evaluated: {cov['jev_evaluated']}",
        f"- Candidates with recent news: {cov['with_news']}",
        f"- Candidates with recent 8-K evidence: {cov['with_8k']}",
        f"- Jev errors: {cov['jev_errors']}",
        "",
        "## Research labels",
    ]
    counts = payload.get("label_counts", {})
    for key in (
        "UNDERAPPRECIATED_POSITIVE",
        "POSITIVE_WATCH",
        "POSITIVE_BUT_PRICED",
        "NEGATIVE_CHANGE",
        "MIXED_OR_NEUTRAL",
        "INSUFFICIENT_EVIDENCE",
    ):
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines += [
        "",
        "## Important limits",
        "- Expectation Load v1 is an equal-weight baseline used only for stratification; weights are not validated.",
        "- The deprecated Massive financials endpoint is not a core dependency because it can enter HTTP 410 brownout.",
        "- Short volume is contextual only and is never treated as short-interest direction by itself.",
        "- Form 4 grants, RSUs, exercises, tax withholding, gifts, and 10b5-1 sales are separated from discretionary insider activity.",
        "- Combined labels must be backtested out-of-sample before any production use.",
        "",
        "## Next validation",
        "Freeze historical point-in-time snapshots, compute forward 5D/10D/20D returns by label and Expectation Load bucket, then compare English Jev semantics against held-out labeled event cases.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dashboard", default="source-mc57.html")
    ap.add_argument("--question-set", default="research/expectation_gap/question-set-en-v1.json")
    ap.add_argument("--output", default="research/expectation_gap/current-v1.json")
    ap.add_argument("--report", default="maintenance/universal-expectation-gap-v1-20260930.md")
    ap.add_argument("--max-candidates", type=int, default=60)
    ap.add_argument("--news-lookback-days", type=int, default=21)
    ap.add_argument("--disclosure-lookback-days", type=int, default=120)
    ap.add_argument("--form4-lookback-days", type=int, default=45)
    ap.add_argument("--short-lookback-days", type=int, default=75)
    ap.add_argument("--short-volume-lookback-days", type=int, default=12)
    ap.add_argument("--massive-min-interval", type=float, default=13.0)
    ap.add_argument("--jev-runs", type=int, default=3)
    ap.add_argument("--jev-timeout", type=int, default=180)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    api_key = os.getenv("MASSIVE_API_KEY") or os.getenv("MASSIVE_KEY") or os.getenv("POLYGON_API_KEY")
    jev_secret = os.getenv("JEV_API_SECRET")
    jev_url = os.getenv("JEV_API_URL") or DEFAULT_JEV_URL
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required")
    if not jev_secret:
        raise SystemExit("JEV_API_SECRET is required")

    html = (root / args.dashboard).read_text(encoding="utf-8")
    details = embedded_json(html, "DET")
    if not isinstance(details, dict):
        raise ShadowRunError("window.DET missing from dashboard")

    manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
    cutoff = parse_timestamp(manifest.get("generated_at"), field="latest-manifest.generated_at")
    asof = utc_iso(cutoff)
    qset = json.loads((root / args.question_set).read_text(encoding="utf-8"))
    questions = qset.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ShadowRunError("Expectation Gap question set is empty")
    if qset.get("language") != "en":
        raise ShadowRunError("Expectation Gap Jev question set must be English")

    all_rows = build_expectation_load(details)
    selected = select_stratified_candidates(all_rows, args.max_candidates)
    tickers = [r["ticker"] for r in selected]

    # News uses the existing market-window pagination path, with vendor text kept in memory only.
    news_by, news_meta = fetch_news_bulk(
        requests.Session(),
        tickers=tickers,
        api_key=api_key,
        start=cutoff - timedelta(days=args.news_lookback_days),
        cutoff=cutoff,
        limit=6,
        timeout=45,
        min_interval=args.massive_min_interval,
        page_size=1000,
        max_pages=50,
    )
    if args.massive_min_interval:
        time.sleep(args.massive_min_interval)

    massive = MassivePacer(api_key, args.massive_min_interval)
    disclosures = fetch_disclosures(
        massive,
        tickers,
        (cutoff.date() - timedelta(days=args.disclosure_lookback_days)).isoformat(),
    )
    form4 = fetch_form4(
        massive,
        tickers,
        (cutoff.date() - timedelta(days=args.form4_lookback_days)).isoformat(),
    )
    short_interest = fetch_short_interest(
        massive,
        tickers,
        (cutoff.date() - timedelta(days=args.short_lookback_days)).isoformat(),
    )
    short_volume = fetch_short_volume(
        massive,
        tickers,
        (cutoff.date() - timedelta(days=args.short_volume_lookback_days)).isoformat(),
    )

    jev = requests.Session()
    results = []
    errors = []
    total_cost = 0.0

    for row in selected:
        ticker = row["ticker"]
        state = jev_state(
            row,
            asof=asof,
            news=news_by.get(ticker, []),
            disclosures=disclosures.get(ticker, []),
            form4=form4.get(ticker, {}),
            short_interest=short_interest.get(ticker, {}),
            short_volume=short_volume.get(ticker, {}),
        )
        # Avoid paying Jev to rediscover complete absence of semantic evidence.
        semantic_evidence = bool(state["evidence"]["recent_news"] or state["evidence"]["recent_8k_disclosures"])
        if not semantic_evidence:
            results.append(
                {
                    **row,
                    "state_sha256": canonical_hash(state),
                    "semantic_evidence": False,
                    "research_label": "INSUFFICIENT_EVIDENCE",
                    "jev": None,
                    "positioning": state["positioning"],
                    "evidence_counts": {"news": 0, "8k": 0},
                }
            )
            continue
        try:
            evaluated = evaluate_jev(
                jev,
                jev_url,
                jev_secret,
                state,
                questions,
                args.jev_runs,
                args.jev_timeout,
            )
            total_cost += evaluated.get("gateway_cost_usd") or 0
            agg = evaluated["aggregate"]
            results.append(
                {
                    **row,
                    "state_sha256": canonical_hash(state),
                    "semantic_evidence": True,
                    "research_label": derive_label(row.get("expectation_load_pctile"), agg),
                    "jev": derived_features(agg),
                    "positioning": state["positioning"],
                    "evidence_counts": {
                        "news": len(state["evidence"]["recent_news"]),
                        "8k": len(state["evidence"]["recent_8k_disclosures"]),
                    },
                }
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "error": type(exc).__name__})
            results.append(
                {
                    **row,
                    "state_sha256": canonical_hash(state),
                    "semantic_evidence": True,
                    "research_label": "JEV_ERROR",
                    "jev": None,
                    "positioning": state["positioning"],
                    "evidence_counts": {
                        "news": len(state["evidence"]["recent_news"]),
                        "8k": len(state["evidence"]["recent_8k_disclosures"]),
                    },
                }
            )

    label_counts: dict[str, int] = defaultdict(int)
    for row in results:
        label_counts[row["research_label"]] += 1

    payload = {
        "schema_version": "universal-expectation-gap-v1",
        "status": "research_shadow",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "as_of": asof,
        "question_set_version": qset.get("version"),
        "jev_language": "en",
        "expectation_load": {
            "status": "UNVALIDATED_BASELINE",
            "components": list(DEFAULT_COMPONENTS),
            "method": "equal-weight mean of cross-sectional component percentiles, then re-ranked cross-sectionally",
            "production_use": False,
        },
        "coverage": {
            "dashboard_universe": len(details),
            "expectation_load_eligible": len(all_rows),
            "selected_candidates": len(selected),
            "jev_evaluated": sum(r.get("jev") is not None for r in results),
            "with_news": sum(bool(news_by.get(t)) for t in tickers),
            "with_8k": sum(bool(disclosures.get(t)) for t in tickers),
            "jev_errors": len(errors),
        },
        "massive_news": news_meta,
        "label_counts": dict(label_counts),
        "gateway_cost_usd": round(total_cost, 8),
        "errors": errors,
        "rows": results,
        "privacy": {
            "vendor_text_persisted": False,
            "raw_jev_runs_persisted": False,
            "stored": "derived features, structured positioning summaries, evidence counts, and state hashes only",
        },
    }

    out = root / args.output
    rep = root / args.report
    out.parent.mkdir(parents=True, exist_ok=True)
    rep.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    rep.write_text(report(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "coverage": payload["coverage"], "label_counts": payload["label_counts"], "cost": payload["gateway_cost_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
