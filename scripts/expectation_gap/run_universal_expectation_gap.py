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
            r.get("p_run20_z", 50.0) - r.get("p_run63_z", 50.0), 4
        )
    return rows


def select_candidates(rows: list[dict[str, Any]], max_deep: int) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    def add(pool: list[dict[str, Any]], label: str, limit: int, key) -> None:
        for r in sorted(pool, key=key)[:limit]:
            item = selected.setdefault(r["ticker"], dict(r))
            item.setdefault("seed_labels", [])
            if label not in item["seed_labels"]:
                item["seed_labels"].append(label)

    add(
        [r for r in rows if r["trend_strength"] >= 70 and r["expectation_load"] <= 60],
        "underappreciated_strength_seed", max(8, max_deep // 2),
        lambda r: (-(r["trend_strength"] - r["expectation_load"]), -r["trend_strength"], r["ticker"]),
    )
    add(
        [r for r in rows if r["trend_strength"] >= 75 and r["expectation_load"] >= 82],
        "expectations_heavy_control", max(4, max_deep // 4),
        lambda r: (-r["expectation_load"], -r["trend_strength"], r["ticker"]),
    )
    add(
        [r for r in rows if r.get("p_ret63", 0) >= 80 and r.get("p_ret20", 100) <= 50],
        "cooled_leader_seed", max(4, max_deep // 4),
        lambda r: (r.get("p_ret20", 50), -r.get("p_ret63", 50), r["ticker"]),
    )
    ordered = sorted(
        selected.values(),
        key=lambda r: (
            0 if "underappreciated_strength_seed" in r["seed_labels"] else 1,
            -r["trend_strength"], r["expectation_load"], r["ticker"],
        ),
    )
    return ordered[:max_deep]


class MassiveClient:
    def __init__(self, api_key: str, min_interval: float):
        self.api_key = api_key
        self.min_interval = max(0.0, min_interval)
        self.session = requests.Session()
        self.last_call = 0.0
        self.calls = 0

    def get(self, path: str, params: dict[str, Any], *, allow_gone: bool = False) -> dict[str, Any]:
        remaining = self.min_interval - (time.monotonic() - self.last_call)
        if remaining > 0:
            time.sleep(remaining)
        q = dict(params)
        q["apiKey"] = self.api_key
        response = self.session.get(MASSIVE_BASE + path, params=q, timeout=45)
        self.last_call = time.monotonic()
        self.calls += 1
        if response.status_code == 410 and allow_gone:
            return {"status": "BROWNOUT_410", "results": []}
        if response.status_code == 429:
            retry = response.headers.get("Retry-After")
            time.sleep(float(retry) if retry and retry.isdigit() else 15.0)
            return self.get(path, params, allow_gone=allow_gone)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"results": []}


def nested_value(row: dict[str, Any] | None, *path: str) -> float | None:
    cur: Any = row
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, dict) and "value" in cur:
        cur = cur["value"]
    return safe_float(cur)


def financial_snapshot(client: MassiveClient, ticker: str) -> dict[str, Any]:
    try:
        payload = client.get(
            "/vX/reference/financials",
            {"ticker": ticker, "timeframe": "quarterly", "limit": 12, "sort": "filing_date", "order": "desc"},
            allow_gone=True,
        )
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}
    if payload.get("status") == "BROWNOUT_410":
        return {"status": "brownout_410"}
    rows = [r for r in (payload.get("results") or []) if isinstance(r, dict)]
    if not rows:
        return {"status": "no_data"}

    rows.sort(key=lambda r: str(r.get("filing_date") or ""), reverse=True)
    latest = rows[0]
    fy, fp = latest.get("fiscal_year"), latest.get("fiscal_period")
    prior = next((r for r in rows[1:] if isinstance(fy, int) and r.get("fiscal_year") == fy - 1 and r.get("fiscal_period") == fp), None)
    previous_q = rows[1] if len(rows) > 1 else None
    previous_q_prior = None
    if previous_q and isinstance(previous_q.get("fiscal_year"), int):
        previous_q_prior = next(
            (r for r in rows[2:] if r.get("fiscal_year") == previous_q["fiscal_year"] - 1 and r.get("fiscal_period") == previous_q.get("fiscal_period")),
            None,
        )

    def rev(r): return nested_value(r, "financials", "income_statement", "revenues")
    def op(r): return nested_value(r, "financials", "income_statement", "operating_income_loss")
    def ocf(r): return nested_value(r, "financials", "cash_flow_statement", "net_cash_flow_from_operating_activities")
    def eps(r): return nested_value(r, "financials", "income_statement", "diluted_earnings_per_share")

    revenue, revenue_prior = rev(latest), rev(prior)
    revenue_prev_q, revenue_prev_q_prior = rev(previous_q), rev(previous_q_prior)
    revenue_growth = pct_change(revenue, revenue_prior) if revenue is not None and revenue_prior is not None else None
    previous_growth = pct_change(revenue_prev_q, revenue_prev_q_prior) if revenue_prev_q is not None and revenue_prev_q_prior is not None else None
    revenue_accel = revenue_growth - previous_growth if revenue_growth is not None and previous_growth is not None else None

    op_now, op_prior = op(latest), op(prior)
    op_margin = 100 * op_now / revenue if revenue and op_now is not None else None
    op_margin_prior = 100 * op_prior / revenue_prior if revenue_prior and op_prior is not None else None
    op_margin_delta = op_margin - op_margin_prior if op_margin is not None and op_margin_prior is not None else None

    ocf_now, ocf_prior = ocf(latest), ocf(prior)
    ocf_margin = 100 * ocf_now / revenue if revenue and ocf_now is not None else None
    ocf_margin_prior = 100 * ocf_prior / revenue_prior if revenue_prior and ocf_prior is not None else None
    ocf_margin_delta = ocf_margin - ocf_margin_prior if ocf_margin is not None and ocf_margin_prior is not None else None

    eps_now, eps_prior = eps(latest), eps(prior)
    eps_signal = None
    if eps_now is not None and eps_prior is not None:
        if eps_prior <= 0 < eps_now:
            eps_signal = 100.0
        elif eps_now < 0 <= eps_prior:
            eps_signal = 0.0
        elif abs(eps_prior) > 1e-9:
            eps_signal = clamp(50.0 + 50.0 * math.tanh(((eps_now / eps_prior) - 1.0) / 0.5))

    components: list[tuple[float, float]] = []
    if revenue_growth is not None:
        components.append((0.30, clamp(50