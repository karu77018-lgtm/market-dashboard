#!/usr/bin/env python3
"""Universal Expectation Gap research pipeline.

Research-only and deliberately separate from MC57/V38 production logic.

Stage A scans the full chart-data universe and computes deterministic market
expectation-load features. Stage B deep-enriches only a bounded candidate set
with Massive fundamentals, Form 4, short interest, and news. Stage C asks Jev,
in English only, to interpret evidence versus embedded expectations. Python
owns every numeric transformation, rank, and score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

MASSIVE_BASE = "https://api.massive.com"
DEFAULT_JEV_URL = "https://jev-investment-engine.vercel.app/api/jev"
QUESTION_PATH = "research/expectation_gap/ueg-jev-en-v1.json"


class ResearchError(RuntimeError):
    pass


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def pct_change(a: float, b: float) -> float | None:
    return (a / b - 1.0) * 100.0 if b and math.isfinite(a) and math.isfinite(b) else None


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Average-tie percentile ranks in [0,100]."""
    pairs = sorted((v, k) for k, v in values.items() if math.isfinite(v))
    n = len(pairs)
    if not n:
        return {}
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and pairs[j][0] == pairs[i][0]:
            j += 1
        rank = (i + j - 1) / 2.0
        pct = 50.0 if n == 1 else 100.0 * rank / (n - 1)
        for _, ticker in pairs[i:j]:
            out[ticker] = pct
        i = j
    return out


def normalize_rows(rows: list[list[Any]]) -> list[tuple[str, float, float, float, float, float]]:
    out = []
    for r in rows:
        try:
            out.append((
                str(r[0])[:10], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])
            ))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def compute_market_row(ticker: str, rows: list[list[Any]]) -> dict[str, Any] | None:
    rr = normalize_rows(rows)
    if len(rr) < 200:
        return None
    d, o, h, l, c, v = rr[-1]
    if c < 5:
        return None
    ddv20 = median([x[4] * x[5] for x in rr[-20:]])
    if not ddv20 or ddv20 < 10_000_000:
        return None

    closes = [x[4] for x in rr]
    volumes = [x[5] for x in rr]
    daily = [(closes[i] / closes[i - 1] - 1.0) * 100.0 for i in range(1, len(closes))]
    vol20 = stdev(daily[-20:])
    vol63 = stdev(daily[-63:])
    if not vol20 or vol20 <= 0 or not vol63 or vol63 <= 0:
        return None

    ret5 = pct_change(closes[-1], closes[-6])
    ret20 = pct_change(closes[-1], closes[-21])
    ret63 = pct_change(closes[-1], closes[-64])
    high63 = max(x[2] for x in rr[-63:])
    high252 = max(x[2] for x in rr[-252:])
    high63_proximity = 100.0 * c / high63 if high63 > 0 else None
    high252_proximity = 100.0 * c / high252 if high252 > 0 else None

    prev_vol = volumes[-80:-20]
    recent_median = median(volumes[-20:])
    previous_median = median(prev_vol)
    vol_ratio = (
        recent_median / previous_median
        if recent_median and previous_median and previous_median > 0
        else 1.0
    )
    vol_expansion = vol20 / vol63 if vol63 > 0 else 1.0

    positive_gap_intensity = 0.0
    for i in range(max(1, len(rr) - 20), len(rr)):
        gap = (rr[i][1] / rr[i - 1][4] - 1.0) * 100.0
        positive_gap_intensity += max(gap, 0.0)
    run20_z = (ret20 or 0.0) / (vol20 * math.sqrt(20))
    run63_z = (ret63 or 0.0) / (vol63 * math.sqrt(63))

    return {
        "ticker": ticker, "as_of": d, "price": c, "ddv20": ddv20,
        "ret5_pct": ret5, "ret20_pct": ret20, "ret63_pct": ret63,
        "vol20_pct": vol20, "vol63_pct": vol63,
        "volume_ratio_20_vs_prev60": vol_ratio,
        "vol_expansion_20_vs_63": vol_expansion,
        "high63_proximity_pct": high63_proximity,
        "high252_proximity_pct": high252_proximity,
        "positive_gap_intensity_20": positive_gap_intensity,
        "run20_z": run20_z, "run63_z": run63_z,
    }


def load_market_universe(root: Path) -> list[dict[str, Any]]:
    index = json.loads((root / "chart-data/index.json").read_text())
    rows: list[dict[str, Any]] = []
    for shard in range(int(index["shard_count"])):
        payload = json.loads((root / f"chart-data/shard-{shard:02d}.json").read_text())
        for ticker, series in payload.items():
            row = compute_market_row(str(ticker), series)
            if row:
                rows.append(row)

    rank_fields = {
        "run20_z": "p_run20_z",
        "run63_z": "p_run63_z",
        "volume_ratio_20_vs_prev60": "p_volume_ratio",
        "high63_proximity_pct": "p_high63_proximity",
        "positive_gap_intensity_20": "p_positive_gap",
        "ret20_pct": "p_ret20",
        "ret63_pct": "p_ret63",
        "vol_expansion_20_vs_63": "p_vol_expansion",
    }
    by_ticker = {r["ticker"]: r for r in rows}
    for source, target in rank_fields.items():
        ranked = percentile_ranks({
            r["ticker"]: float(r[source]) for r in rows if safe_float(r.get(source)) is not None
        })
        for ticker, pct in ranked.items():
            by_ticker[ticker][target] = pct

    for r in rows:
        r["expectation_load"] = round(
            0.35 * r.get("p_run20_z", 50.0)
            + 0.25 * r.get("p_run63_z", 50.0)
            + 0.15 * r.get("p_volume_ratio", 50.0)
            + 0.15 * r.get("p_high63_proximity", 50.0)
            + 0.10 * r.get("p_positive_gap", 50.0), 4,
        )
        r["trend_strength"] = round(
            0.45 * r.get("p_ret20", 50.0) + 0.55 * r.get("p_ret63", 50.0), 4
        )
        r["expectation_acceleration"] = round(
            r.get("p_run20_z", 50.0) - r.g