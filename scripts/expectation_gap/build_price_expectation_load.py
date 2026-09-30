#!/usr/bin/env python3
"""Build a universal price-expectation load for the liquid US universe.

This is a descriptive "how much enthusiasm is already visible in price/flow" layer,
not a buy/sell score. It uses only point-in-time market data and transparent equal
weights, then reports forward-return calibration separately.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from scripts.expectation_gap.common import (
    eligible_price_row,
    forward_return,
    index_on_or_before,
    index_strictly_before,
    load_band,
    load_series,
    mean,
    percentile_map,
    quantile,
    raw_price_features,
)


COMPONENTS = (
    "ret5_pct",
    "excess20_pct",
    "ret63_pct",
    "near_high63",
    "volume_attention_20v43",
    "up_gap_count_20d",
)
COMMERCIAL_EVENT_CATEGORIES = {
    "share_repurchase_program",
    "significant_contract_award",
    "partnership_or_collaboration",
}


def snapshot(series: dict[str, list[tuple]], date: str) -> dict[str, dict[str, Any]]:
    qqq = series.get("QQQ")
    qi = index_on_or_before(qqq, date) if qqq else None
    qqq20 = None
    if qqq and qi is not None:
        qf = raw_price_features(qqq, qi)
        qqq20 = qf.get("ret20_pct") if qf else None

    raw: dict[str, dict[str, Any]] = {}
    for ticker, rows in series.items():
        i = index_on_or_before(rows, date)
        if i is None:
            continue
        f = raw_price_features(rows, i)
        if not eligible_price_row(f):
            continue
        f["as_of"] = rows[i][0]
        f["index"] = i
        f["excess20_pct"] = (
            f["ret20_pct"] - qqq20
            if isinstance(f.get("ret20_pct"), (int, float)) and isinstance(qqq20, (int, float))
            else None
        )
        f["near_high63"] = (
            -float(f["distance_63d_high_pct"])
            if isinstance(f.get("distance_63d_high_pct"), (int, float))
            else None
        )
        raw[ticker] = f

    pct_by_component = {
        component: percentile_map({ticker: row.get(component) for ticker, row in raw.items()})
        for component in COMPONENTS
    }
    rs21 = percentile_map({ticker: row.get("ret20_pct") for ticker, row in raw.items()})
    rs63 = percentile_map({ticker: row.get("ret63_pct") for ticker, row in raw.items()})
    rs189 = percentile_map({ticker: row.get("ret189_pct") for ticker, row in raw.items()})

    for ticker, row in raw.items():
        component_pcts = {
            component: pct_by_component[component].get(ticker)
            for component in COMPONENTS
        }
        valid = [v for v in component_pcts.values() if isinstance(v, (int, float))]
        score = mean(valid)
        row["component_percentiles"] = component_pcts
        row["expectation_load_score"] = score
        row["expectation_load_band"] = load_band(score)
        row["rs21_percentile"] = rs21.get(ticker)
        row["rs63_percentile"] = rs63.get(ticker)
        row["rs189_percentile"] = rs189.get(ticker)
        row.pop("index", None)
        row.pop("near_high63", None)
    return raw


def stats(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": mean(values),
        "p10": quantile(values, 0.10),
        "median": quantile(values, 0.50),
        "p90": quantile(values, 0.90),
        "p_positive": mean([v > 0 for v in values]) if values else None,
    }


def calibrate_unconditional(series: dict[str, list[tuple]], qqq_dates: list[str]) -> dict[str, Any]:
    rows = []
    for date in qqq_dates:
        snap = snapshot(series, date)
        qqq = series.get("QQQ")
        qi = index_on_or_before(qqq, date) if qqq else None
        q5 = forward_return(qqq, qi, 5) if qqq and qi is not None else None
        q20 = forward_return(qqq, qi, 20) if qqq and qi is not None else None
        for ticker, f in snap.items():
            ticker_rows = series[ticker]
            ti = index_on_or_before(ticker_rows, f["as_of"])
            if ti is None:
                continue
            r5 = forward_return(ticker_rows, ti, 5)
            r20 = forward_return(ticker_rows, ti, 20)
            rows.append({
                "band": f["expectation_load_band"],
                "score": f["expectation_load_score"],
                "fwd5_excess": r5 - q5 if r5 is not None and q5 is not None else None,
                "fwd20_excess": r20 - q20 if r20 is not None and q20 is not None else None,
            })
    out = {}
    for band in ("low", "mid", "high", "extreme"):
        rr = [r for r in rows if r["band"] == band]
        out[band] = {
            "n": len(rr),
            "fwd5_excess_pct": stats([r["fwd5_excess"] for r in rr if r["fwd5_excess"] is not None]),
            "fwd20_excess_pct": stats([r["fwd20_excess"] for r in rr if r["fwd20_excess"] is not None]),
        }
    return {"snapshots": qqq_dates, "bands": out}


def event_study(root: Path, series: dict[str, list[tuple]]) -> dict[str, Any]:
    path = root / "research/event_risk/event-metadata-20260930.json"
    if not path.exists():
        return {"status": "unavailable", "reason": "event_metadata_missing"}
    meta = json.loads(path.read_text())
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    seen: dict[tuple[str, str], dt.date] = {}
    rows = []
    qqq = series.get("QQQ")
    for e in sorted(meta.get("events", []), key=lambda x: (x.get("filing_date", ""), x.get("ticker", ""), x.get("category", ""))):
        cat = e.get("category")
        ticker = e.get("ticker")
        filing = e.get("filing_date")
        if cat not in COMMERCIAL_EVENT_CATEGORIES or not ticker or not filing or ticker not in series:
            continue
        day = dt.date.fromisoformat(filing)
        key = (ticker, cat)
        if key in seen and (day - seen[key]).days < 30:
            continue
        seen[key] = day

        rows_t = series[ticker]
        ti = index_strictly_before(rows_t, filing)
        if ti is None or ti < 189:
            continue
        as_of = rows_t[ti][0]
        if as_of not in cache:
            cache[as_of] = snapshot(series, as_of)
        f = cache[as_of].get(ticker)
        if not f:
            continue
        q5 = None
        if qqq:
            qi = index_on_or_before(qqq, as_of)
            q5 = forward_return(qqq, qi, 5) if qi is not None else None
        r5 = forward_return(rows_t, ti, 5)
        if r5 is None:
            continue
        rows.append({
            "ticker": ticker,
            "filing_date": filing,
            "category": cat,
            "as_of": as_of,
            "load_score": f["expectation_load_score"],
            "band": f["expectation_load_band"],
            "ret5_pct": r5,
            "ret5_excess_qqq_pct": r5 - q5 if q5 is not None else None,
        })

    bands = {}
    for band in ("low", "mid", "high", "extreme"):
        rr = [r for r in rows if r["band"] == band]
        bands[band] = {
            "n": len(rr),
            "ret5_pct": stats([r["ret5_pct"] for r in rr]),
            "ret5_excess_qqq_pct": stats([r["ret5_excess_qqq_pct"] for r in rr if r["ret5_excess_qqq_pct"] is not None]),
        }
    return {
        "status": "pilot",
        "timing_caveat": "8-K filing date can lag first public disclosure; this study is directional until publication timestamps are aligned.",
        "categories": sorted(COMMERCIAL_EVENT_CATEGORIES),
        "n": len(rows),
        "bands": bands,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", default="research/expectation_gap/price-expectation-load-v1.json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    series = load_series(root)
    qqq = series.get("QQQ")
    if not qqq:
        raise SystemExit("QQQ missing from chart-data")
    current_date = qqq[-1][0]
    current = snapshot(series, current_date)

    # One snapshot every ~21 trading sessions over roughly the last year, leaving
    # 20 sessions for forward calibration.
    end_i = len(qqq) - 21
    start_i = max(189, end_i - 252)
    snap_idx = list(range(start_i, end_i + 1, 21))
    snap_dates = [qqq[i][0] for i in snap_idx]

    rows = []
    for ticker, f in current.items():
        rows.append({
            "ticker": ticker,
            **{k: v for k, v in f.items() if k != "as_of"},
        })
    rows.sort(key=lambda r: (-(r.get("expectation_load_score") or -1), -(r.get("rs189_percentile") or -1), r["ticker"]))

    underappreciated = [
        r for r in rows
        if (r.get("rs189_percentile") or 0) >= 85
        and (r.get("rs63_percentile") or 0) >= 85
        and (r.get("expectation_load_score") or 100) < 60
    ]
    underappreciated.sort(key=lambda r: (-(r.get("rs189_percentile") or 0), r.get("expectation_load_score") or 100, r["ticker"]))

    payload = {
        "version": "price-expectation-load-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "as_of": current_date,
        "definition": {
            "purpose": "descriptive estimate of how much positive expectation is already visible in price/flow; not a trade score",
            "components": list(COMPONENTS),
            "weighting": "equal weight across cross-sectional component percentiles",
            "bands": {"low": "<30", "mid": "30-<70", "high": "70-<90", "extreme": ">=90"},
        },
        "eligible_n": len(rows),
        "unconditional_calibration": calibrate_unconditional(series, snap_dates),
        "commercial_event_pilot": event_study(root, series),
        "underappreciated_strong_candidates": underappreciated[:100],
        "rows": rows,
    }
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "ok": True,
        "version": payload["version"],
        "as_of": current_date,
        "eligible_n": len(rows),
        "underappreciated_strong_n": len(underappreciated),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
