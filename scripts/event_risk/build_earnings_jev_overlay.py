#!/usr/bin/env python3
"""Build a point-in-time earnings Jev semantic overlay.

This script only extracts semantic features. It does NOT calculate performance,
fit thresholds, rank outcomes, or run a backtest. Those steps are intentionally
performed in the assistant's local Python runtime.

Inputs:
- frozen earnings Expectation Load event rows;
- Massive 8-K text and news available by the event cutoff;
- Jev minimal English question set v2.

Outputs:
- derived Jev probabilities/classes and audit hashes only;
- no vendor article text or raw Jev runs are persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from scripts.run_jev_live_shadow import (
        ShadowRunError,
        fetch_news_bulk,
        parse_timestamp,
        safe_number,
        utc_iso,
    )
    from scripts.run_expectation_gap_shadow import MassivePacer, chunks
except ModuleNotFoundError:
    from run_jev_live_shadow import (
        ShadowRunError,
        fetch_news_bulk,
        parse_timestamp,
        safe_number,
        utc_iso,
    )
    from run_expectation_gap_shadow import MassivePacer, chunks


DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _event_cutoff_utc(filing_date: str) -> datetime:
    # July-September 2026 is U.S. daylight-saving time. Using 13:29 UTC on the
    # next calendar day conservatively includes after-hours release coverage
    # while excluding news published after the next regular-session open.
    day = datetime.fromisoformat(filing_date + "T00:00:00+00:00")
    return day + timedelta(days=1, hours=13, minutes=29)


def fetch_8k_text(
    client: MassivePacer,
    tickers: list[str],
    start_date: str,
    end_date: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for group in chunks(tickers, 25):
        rows = client.paged(
            "/stocks/filings/8-K/vX/text",
            {
                "ticker.any_of": ",".join(group),
                "filing_date.gte": start_date,
                "filing_date.lte": end_date,
                "limit": 100,
                "sort": "filing_date.asc",
            },
            max_pages=20,
        )
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            accession = str(row.get("accession_number") or "")
            if ticker and accession:
                out[(ticker, accession)] = {
                    "filing_date": row.get("filing_date"),
                    "items_text": " ".join(str(row.get("items_text") or "").split())[:7000],
                }
    return out


def event_news(
    docs: list[dict[str, Any]],
    filing_date: str,
) -> list[dict[str, Any]]:
    start = datetime.fromisoformat(filing_date + "T00:00:00+00:00") - timedelta(days=2)
    cutoff = _event_cutoff_utc(filing_date)
    selected: list[tuple[datetime, dict[str, Any]]] = []
    for doc in docs:
        try:
            published = parse_timestamp(doc.get("published_utc"), field="published_utc")
        except ShadowRunError:
            continue
        if start <= published <= cutoff:
            selected.append(
                (
                    published,
                    {
                        "published_utc": utc_iso(published),
                        "title": str(doc.get("title") or "")[:500],
                        "description": str(doc.get("description") or "")[:1800],
                    },
                )
            )
    selected.sort(key=lambda x: x[0])
    return [x[1] for x in selected[-8:]]


def evaluate_jev(
    session: requests.Session,
    url: str,
    secret: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    response = session.post(
        url,
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "state": state,
            "questions": questions,
            "runs": 1,
            "persist": False,
            "responseMode": "json",
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise ShadowRunError(f"Jev HTTP {response.status_code}: {response.text[:300]}")
    payload = response.json()
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ShadowRunError("Jev aggregate missing")
    return {
        "aggregate": aggregate,
        "duration_ms": safe_number(payload.get("durationMs")),
        "gateway_cost_usd": _finite(payload.get("gatewayCostUsd")),
    }


def prob(aggregate: dict[str, Any], qid: str) -> float | None:
    row = aggregate.get(qid)
    return _finite(row.get("probabilityMean")) if isinstance(row, dict) else None


def choice(aggregate: dict[str, Any], qid: str) -> str | None:
    row = aggregate.get(qid)
    value = row.get("majorityChoice") if isinstance(row, dict) else None
    return str(value) if value is not None else None


def choice_probability(
    aggregate: dict[str, Any], qid: str, option: str
) -> float | None:
    row = aggregate.get(qid)
    dist = row.get("choiceDistribution") if isinstance(row, dict) else None
    return _finite(dist.get(option)) if isinstance(dist, dict) else None


def derived(aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_business_change": prob(aggregate, "JEV01_material_business_change"),
        "persistent_change": prob(aggregate, "JEV02_persistent_change"),
        "information_novelty": prob(aggregate, "JEV03_information_novelty"),
        "surprise_class": choice(aggregate, "JEV04_surprise_vs_prior_expectations"),
        "positive_surprise_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "positive_surprise"
        ),
        "negative_surprise_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "negative_surprise"
        ),
        "broadly_expected_probability": choice_probability(
            aggregate, "JEV04_surprise_vs_prior_expectations", "broadly_expected"
        ),
        "evidence_quality": choice(aggregate, "JEV05_evidence_quality"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument(
        "--events",
        default="research/event_risk/earnings-expectation-load-core-v1.json",
    )
    ap.add_argument(
        "--questions",
        default="research/expectation_gap/question-set-en-v2.json",
    )
    ap.add_argument(
        "--output",
        default="research/event_risk/earnings-jev-overlay-v1.json",
    )
    ap.add_argument("--massive-min-interval", type=float, default=13.0)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    api_key = (
        os.getenv("MASSIVE_API_KEY")
        or os.getenv("MASSIVE_KEY")
        or os.getenv("POLYGON_API_KEY")
    )
    jev_secret = os.getenv("JEV_API_SECRET")
    jev_url = os.getenv("JEV_API_URL") or DEFAULT_JEV_URL
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required")
    if not jev_secret:
        raise SystemExit("JEV_API_SECRET is required")

    event_payload = json.loads((root / args.events).read_text(encoding="utf-8"))
    rows = [
        r for r in event_payload.get("rows", [])
        if isinstance(r, dict)
        and r.get("ticker")
        and r.get("filing_date")
        and r.get("accession_number")
    ]
    if not rows:
        raise SystemExit("No earnings event rows")

    qset = json.loads((root / args.questions).read_text(encoding="utf-8"))
    questions = qset.get("questions")
    if not isinstance(questions, dict) or len(questions) != 5:
        raise SystemExit("Expected five Jev v2 questions")

    tickers = sorted({str(r["ticker"]).upper() for r in rows})
    start_date = min(str(r["filing_date"]) for r in rows)
    end_date = max(str(r["filing_date"]) for r in rows)

    start = datetime.fromisoformat(start_date + "T00:00:00+00:00") - timedelta(days=2)
    final_cutoff = _event_cutoff_utc(end_date)

    news_by, news_meta = fetch_news_bulk(
        requests.Session(),
        tickers=tickers,
        api_key=api_key,
        start=start,
        cutoff=final_cutoff,
        limit=100,
        timeout=45,
        min_interval=args.massive_min_interval,
        page_size=1000,
        max_pages=80,
    )
    if args.massive_min_interval:
        time.sleep(args.massive_min_interval)

    massive = MassivePacer(api_key, args.massive_min_interval)
    text_by = fetch_8k_text(massive, tickers, start_date, end_date)

    session = requests.Session()
    outputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    cost = 0.0

    for row in rows:
        ticker = str(row["ticker"]).upper()
        filing_date = str(row["filing_date"])
        accession = str(row["accession_number"])
        news = event_news(news_by.get(ticker, []), filing_date)
        filing = text_by.get((ticker, accession), {})
        evidence = {
            "disclosure_supporting_text": " ".join(
                str(row.get("supporting_text") or "").split()
            )[:2400],
            "eight_k_items_text": filing.get("items_text"),
            "event_window_news": news,
        }
        state = {
            "schema_version": "earnings-jev-overlay-state-v1",
            "ticker": ticker,
            "event_date": filing_date,
            "pre_event_market_context": {
                "pre20_return_pct": row.get("pre20_return_pct"),
                "pre20_excess_qqq_pct": row.get("pre20_excess_qqq_pct"),
                "rs63_change_20d": row.get("rs63_change_20d"),
                "distance_to_63d_high_pct": row.get("dist_high63_pct"),
            },
            "company_specific_evidence": evidence,
            "instructions": [
                "Use only the supplied evidence.",
                "The market metrics are prior-expectation context, not proof of business quality.",
                "Do not predict the stock price or use any post-event return.",
                "If the evidence does not contain actual operating information, mark evidence quality weak or insufficient.",
            ],
        }

        try:
            result = evaluate_jev(
                session, jev_url, jev_secret, state, questions, args.timeout
            )
            cost += result.get("gateway_cost_usd") or 0.0
            outputs.append(
                {
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "state_sha256": canonical_hash(state),
                    "evidence_counts": {
                        "news": len(news),
                        "has_8k_items_text": bool(filing.get("items_text")),
                    },
                    "jev": derived(result["aggregate"]),
                    "duration_ms": result.get("duration_ms"),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    payload = {
        "version": "earnings-jev-overlay-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_set_version": qset.get("version"),
        "runs_per_event": 1,
        "event_count": len(rows),
        "jev_success_count": len(outputs),
        "jev_error_count": len(errors),
        "gateway_cost_usd": round(cost, 8),
        "news_fetch": news_meta,
        "privacy": {
            "vendor_text_persisted": False,
            "raw_jev_runs_persisted": False,
        },
        "rows": outputs,
        "errors": errors,
    }
    path = root / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "event_count": len(rows),
                "jev_success_count": len(outputs),
                "jev_error_count": len(errors),
                "gateway_cost_usd": payload["gateway_cost_usd"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
