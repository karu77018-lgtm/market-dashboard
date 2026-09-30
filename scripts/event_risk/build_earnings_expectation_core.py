#!/usr/bin/env python3
"""Build a leak-free pre-earnings Expectation Load core.

Core v1 intentionally uses only data available in the current stack:
- Massive 8-K quarterly_earnings event detection
- repository point-in-time daily prices
- QQQ benchmark
- cross-sectional RS63 percentile and 20-session RS-rank change

Options Expected Move, analyst revisions and estimate revisions are separate enhanced
layers. Missing entitlement never causes silent reweighting of the core score.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any

try:
    from scripts.event_risk.build_dilution_magnitude import MassiveClient, _norm_price_rows
except ModuleNotFoundError:  # direct script execution: repo root is not sys.path[0]
    from build_dilution_magnitude import MassiveClient, _norm_price_rows

COMPONENTS = (
    "pre20_return_pct",
    "pre20_excess_qqq_pct",
    "rs63_change_20d",
    "dist_high63_pct",
)


class UniversePrices:
    def __init__(self, repo_root: Path):
        root = repo_root / "chart-data"
        idx = json.loads((root / "index.json").read_text())
        self.series: dict[str, list[tuple[str, float, float, float, float, float]]] = {}
        for shard in sorted(set(idx.get("ticker_to_shard", {}).values())):
            if not isinstance(shard, int):
                continue
            obj = json.loads((root / f"shard-{shard:02d}.json").read_text())
            for ticker, rows in obj.items():
                norm = _norm_price_rows(rows)
                if norm:
                    self.series[ticker] = norm
        self._dates = {k: [r[0] for r in v] for k, v in self.series.items()}
        self._rank_cache: dict[str, dict[str, float]] = {}

    def at_or_before(self, ticker: str, date: str) -> int | None:
        dates = self._dates.get(ticker)
        if not dates:
            return None
        i = bisect.bisect_right(dates, date) - 1
        return i if i >= 0 else None

    def strictly_before(self, ticker: str, date: str) -> int | None:
        dates = self._dates.get(ticker)
        if not dates:
            return None
        i = bisect.bisect_left(dates, date) - 1
        return i if i >= 0 else None

    def strictly_after_indices(self, ticker: str, date: str) -> list[int]:
        dates = self._dates.get(ticker)
        if not dates:
            return []
        start = bisect.bisect_right(dates, date)
        return list(range(start, len(dates)))

    def rs63_percentiles(self, date: str) -> dict[str, float]:
        if date in self._rank_cache:
            return self._rank_cache[date]
        values: list[tuple[str, float]] = []
        for ticker, rows in self.series.items():
            i = self.at_or_before(ticker, date)
            if i is None or i < 63:
                continue
            close = rows[i][4]
            if close < 5:
                continue
            # Keep the ranking universe liquid enough to match the event-study population.
            if i >= 19:
                ddv20 = statistics.median(rows[j][4] * rows[j][5] for j in range(i - 19, i + 1))
                if ddv20 < 1e7:
                    continue
            ret63 = rows[i][4] / rows[i - 63][4] - 1
            if math.isfinite(ret63):
                values.append((ticker, ret63))
        values.sort(key=lambda x: x[1])
        out: dict[str, float] = {}
        n = len(values)
        if n == 1:
            out[values[0][0]] = 50.0
        elif n > 1:
            for rank, (ticker, _) in enumerate(values):
                out[ticker] = 100.0 * rank / (n - 1)
        self._rank_cache[date] = out
        return out


def fetch_earnings_disclosures(client: MassiveClient, start: str, end: str) -> list[dict[str, Any]]:
    params = {
        "tertiary_category": "quarterly_earnings",
        "filing_date.gte": start,
        "filing_date.lte": end,
        "limit": 1000,
        "sort": "filing_date.asc",
    }
    payload = client.get("/stocks/filings/8-K/vX/disclosures", params)
    rows = list(payload.get("results") or [])
    next_url = payload.get("next_url")
    while next_url:
        payload = client.get(next_url)
        rows.extend(payload.get("results") or [])
        next_url = payload.get("next_url")
    return rows


def _ticker_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [str(x) for x in v if x]
        except json.JSONDecodeError:
            return [raw]
    return []


def _pct_rank_map(rows: list[dict[str, Any]], field: str) -> dict[int, float]:
    vals = [(i, float(r[field])) for i, r in enumerate(rows) if r.get(field) is not None and math.isfinite(float(r[field]))]
    vals.sort(key=lambda x: x[1])
    n = len(vals)
    if n == 0:
        return {}
    if n == 1:
        return {vals[0][0]: 50.0}
    return {idx: 100.0 * rank / (n - 1) for rank, (idx, _) in enumerate(vals)}


def _q(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    x = (len(s) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def _reaction_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"n": len(rows)}
    for field in ("gap_pct", "ret1_pct", "ret5_pct", "ret20_pct"):
        vals = [float(r[field]) for r in rows if r.get(field) is not None and math.isfinite(float(r[field]))]
        out[field] = {
            "n": len(vals),
            "mean": statistics.fmean(vals) if vals else None,
            "p10": _q(vals, 0.10),
            "median": _q(vals, 0.50),
            "p90": _q(vals, 0.90),
            "p_negative": statistics.fmean([v < 0 for v in vals]) if vals else None,
        }
    return out


def build(repo_root: Path, client: MassiveClient, start: str, end: str) -> dict[str, Any]:
    prices = UniversePrices(repo_root)
    qqq = prices.series.get("QQQ") or []
    qqq_dates = [r[0] for r in qqq]
    disclosures = fetch_earnings_disclosures(client, start, end)

    # One company/event record. Multi-ticker funds/warrants are ignored unless the common
    # stock ticker exists in the price universe. Same ticker/accession is deduplicated.
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for d in disclosures:
        for ticker in _ticker_list(d.get("tickers")):
            key = (ticker, str(d.get("accession_number") or ""))
            if key in seen or ticker not in prices.series:
                continue
            seen.add(key)
            events.append(
                {
                    "ticker": ticker,
                    "filing_date": str(d.get("filing_date") or "")[:10],
                    "accession_number": d.get("accession_number"),
                    "supporting_text": d.get("supporting_text") or "",
                    "filing_url": d.get("filing_url"),
                }
            )
    events.sort(key=lambda r: (r["filing_date"], r["ticker"]))

    rows: list[dict[str, Any]] = []
    last_event: dict[str, dt.date] = {}
    for event in events:
        ticker, date = event["ticker"], event["filing_date"]
        if not date:
            continue
        day = dt.date.fromisoformat(date)
        if ticker in last_event and (day - last_event[ticker]).days < 45:
            continue
        series = prices.series[ticker]
        pi = prices.strictly_before(ticker, date)
        future = prices.strictly_after_indices(ticker, date)
        if pi is None or pi < 199 or len(future) < 5:
            continue
        close0 = series[pi][4]
        if close0 < 5:
            continue
        ddv20 = statistics.median(series[j][4] * series[j][5] for j in range(pi - 19, pi + 1))
        if ddv20 < 1e7:
            continue
        last_event[ticker] = day

        pre20 = 100.0 * (close0 / series[pi - 20][4] - 1)
        prior20_date = series[pi - 20][0]
        high63 = max(series[j][2] for j in range(pi - 62, pi + 1))
        dist_high63 = 100.0 * (close0 / high63 - 1)

        qi = bisect.bisect_right(qqq_dates, series[pi][0]) - 1
        q20 = None
        if qi >= 20:
            q20 = 100.0 * (qqq[qi][4] / qqq[qi - 20][4] - 1)
        excess20 = pre20 - q20 if q20 is not None else None

        rank_now = prices.rs63_percentiles(series[pi][0]).get(ticker)
        rank_then = prices.rs63_percentiles(prior20_date).get(ticker)
        rank_change = rank_now - rank_then if rank_now is not None and rank_then is not None else None

        fi = future[0]
        ret1 = 100.0 * (series[fi][4] / close0 - 1)
        ret5 = 100.0 * (series[future[4]][4] / close0 - 1)
        ret20 = 100.0 * (series[future[19]][4] / close0 - 1) if len(future) >= 20 else None

        rows.append(
            {
                **event,
                "baseline_session": series[pi][0],
                "pre_close": close0,
                "ddv20": ddv20,
                "pre20_return_pct": pre20,
                "qqq_pre20_return_pct": q20,
                "pre20_excess_qqq_pct": excess20,
                "rs63_percentile": rank_now,
                "rs63_percentile_20d_ago": rank_then,
                "rs63_change_20d": rank_change,
                "dist_high63_pct": dist_high63,
                "gap_pct": 100.0 * (series[fi][1] / close0 - 1),
                "ret1_pct": ret1,
                "ret5_pct": ret5,
                "ret20_pct": ret20,
                # Enhanced-only fields. Do not silently substitute realized vol.
                "option_expected_move_pct": None,
                "realized_expected_move_ratio": None,
                "analyst_pt_revision_momentum": None,
                "estimate_revision_momentum": None,
                "option_skew": None,
            }
        )

    pct_maps = {field: _pct_rank_map(rows, field) for field in COMPONENTS}
    for i, row in enumerate(rows):
        component_scores = {field: pct_maps[field].get(i) for field in COMPONENTS}
        usable = [v for v in component_scores.values() if v is not None]
        row["expectation_load_core_components"] = component_scores
        row["expectation_load_core_coverage"] = len(usable)
        row["expectation_load_core"] = statistics.fmean(usable) if len(usable) == len(COMPONENTS) else None
        row["expectation_load_enhanced"] = None
        row["enhanced_status"] = "BLOCKED_BY_CURRENT_DATA_ENTITLEMENT"

    bins = {
        "0-20": [r for r in rows if r.get("expectation_load_core") is not None and r["expectation_load_core"] < 20],
        "20-40": [r for r in rows if r.get("expectation_load_core") is not None and 20 <= r["expectation_load_core"] < 40],
        "40-60": [r for r in rows if r.get("expectation_load_core") is not None and 40 <= r["expectation_load_core"] < 60],
        "60-80": [r for r in rows if r.get("expectation_load_core") is not None and 60 <= r["expectation_load_core"] < 80],
        "80-100": [r for r in rows if r.get("expectation_load_core") is not None and r["expectation_load_core"] >= 80],
    }

    return {
        "version": "earnings-expectation-load-core-v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_range": [start, end],
        "event_source": "Massive 8-K disclosure taxonomy: quarterly_earnings",
        "timing_rule": "baseline is the last regular-session close strictly before filing_date; conservative and leak-free when exact release time is unavailable",
        "core_definition": {
            "pre20_return_pct": "20-session stock run-up percentile across eligible earnings events",
            "pre20_excess_qqq_pct": "20-session stock return minus QQQ return, then percentile across eligible earnings events",
            "rs63_change_20d": "change in cross-sectional 63-session RS percentile over the prior 20 sessions",
            "dist_high63_pct": "distance to 63-session high; closer to high maps to higher percentile",
            "score": "equal-weight mean of all four component percentiles; no missing-component reweighting",
        },
        "enhanced_definition": {
            "option_expected_move_pct": "(ATM call + ATM put) / stock price using pre-event option prices",
            "realized_expected_move_ratio": "absolute realized event move / option expected move",
            "analyst_pt_revision_momentum": "future layer; currently not entitled",
            "estimate_revision_momentum": "future layer; currently not entitled",
            "option_skew": "future layer; current IV/Greeks chain snapshot not entitled",
            "status": "Enhanced score is deliberately null until required inputs are available.",
        },
        "coverage": {
            "raw_disclosures": len(disclosures),
            "eligible_events": len(rows),
            "core_complete": sum(r.get("expectation_load_core") is not None for r in rows),
            "option_expected_move": 0,
            "analyst_revision": 0,
            "estimate_revision": 0,
        },
        "reaction_by_core_load": {name: _reaction_stats(group) for name, group in bins.items()},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-09-21")
    ap.add_argument("--sleep", type=float, default=13.0)
    ap.add_argument("--output", default="research/event_risk/earnings-expectation-load-core-v1.json")
    args = ap.parse_args()
    key = os.getenv("MASSIVE_API_KEY") or os.getenv("MASSIVE_KEY") or os.getenv("POLYGON_API_KEY")
    if not key:
        raise SystemExit("MASSIVE_API_KEY is required")
    root = Path(args.repo_root).resolve()
    payload = build(root, MassiveClient(key, args.sleep), args.start, args.end)
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"ok": True, "version": payload["version"], "coverage": payload["coverage"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
