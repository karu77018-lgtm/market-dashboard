from __future__ import annotations

import bisect
import json
import math
import statistics
from pathlib import Path
from typing import Any


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    x = (len(s) - 1) * p
    lo = math.floor(x)
    hi = math.ceil(x)
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def percentile_map(values: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted((float(v), k) for k, v in values.items() if isinstance(v, (int, float)) and math.isfinite(float(v)))
    if not valid:
        return {k: None for k in values}
    # Mid-rank for ties. Return 0..100.
    by_value: dict[float, list[str]] = {}
    for value, key in valid:
        by_value.setdefault(value, []).append(key)
    ordered_values = sorted(by_value)
    out: dict[str, float | None] = {k: None for k in values}
    cursor = 0
    n = len(valid)
    for value in ordered_values:
        keys = by_value[value]
        first = cursor
        last = cursor + len(keys) - 1
        rank = (first + last) / 2
        pct = 50.0 if n == 1 else 100.0 * rank / (n - 1)
        for key in keys:
            out[key] = pct
        cursor += len(keys)
    return out


def load_series(root: Path) -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    chart = root / "chart-data"
    index = json.loads((chart / "index.json").read_text())
    result: dict[str, list[tuple[str, float, float, float, float, float]]] = {}
    shard_ids = sorted(set(v for v in (index.get("ticker_to_shard") or {}).values() if isinstance(v, int)))
    for shard_id in shard_ids:
        payload = json.loads((chart / f"shard-{shard_id:02d}.json").read_text())
        for ticker, rows in payload.items():
            clean = []
            for r in rows or []:
                try:
                    clean.append((str(r[0])[:10], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
                except (TypeError, ValueError, IndexError):
                    continue
            if clean:
                result[str(ticker).upper()] = clean
    return result


def index_on_or_before(rows: list[tuple], date: str) -> int | None:
    dates = [r[0] for r in rows]
    i = bisect.bisect_right(dates, date) - 1
    return i if i >= 0 else None


def index_strictly_before(rows: list[tuple], date: str) -> int | None:
    dates = [r[0] for r in rows]
    i = bisect.bisect_left(dates, date) - 1
    return i if i >= 0 else None


def returns(rows: list[tuple], i: int, horizon: int) -> float | None:
    if i < horizon or rows[i - horizon][4] <= 0:
        return None
    return (rows[i][4] / rows[i - horizon][4] - 1.0) * 100.0


def forward_return(rows: list[tuple], i: int, horizon: int) -> float | None:
    if i + horizon >= len(rows) or rows[i][4] <= 0:
        return None
    return (rows[i + horizon][4] / rows[i][4] - 1.0) * 100.0


def ddv20(rows: list[tuple], i: int) -> float | None:
    if i < 19:
        return None
    vals = [rows[j][4] * rows[j][5] for j in range(i - 19, i + 1) if rows[j][4] > 0 and rows[j][5] >= 0]
    return median(vals)


def daily_returns(rows: list[tuple], start: int, end: int) -> list[float]:
    vals = []
    for j in range(max(1, start), end + 1):
        prev = rows[j - 1][4]
        if prev > 0:
            vals.append((rows[j][4] / prev - 1.0) * 100.0)
    return vals


def raw_price_features(rows: list[tuple], i: int) -> dict[str, float | None]:
    if i < 189:
        return {}
    ret5 = returns(rows, i, 5)
    ret20 = returns(rows, i, 20)
    ret63 = returns(rows, i, 63)
    ret189 = returns(rows, i, 189)
    high63 = max(rows[j][2] for j in range(i - 62, i + 1))
    dist_high63 = (rows[i][4] / high63 - 1.0) * 100.0 if high63 > 0 else None

    dv20 = [rows[j][4] * rows[j][5] for j in range(i - 19, i + 1)]
    dv_prev43 = [rows[j][4] * rows[j][5] for j in range(i - 62, i - 19)]
    med20 = median(dv20)
    med_prev = median(dv_prev43)
    volume_attention = med20 / med_prev if med20 and med_prev and med_prev > 0 else None

    up_gaps = 0
    abs_gaps = []
    for j in range(i - 19, i + 1):
        prev = rows[j - 1][4] if j > 0 else None
        if prev and prev > 0:
            gap = (rows[j][1] / prev - 1.0) * 100.0
            abs_gaps.append(abs(gap))
            if gap >= 2.0:
                up_gaps += 1

    vol20 = stdev(daily_returns(rows, i - 19, i))
    vol63 = stdev(daily_returns(rows, i - 62, i))
    vol_ratio = vol20 / vol63 if vol20 and vol63 and vol63 > 0 else None

    return {
        "price": rows[i][4],
        "ret5_pct": ret5,
        "ret20_pct": ret20,
        "ret63_pct": ret63,
        "ret189_pct": ret189,
        "distance_63d_high_pct": dist_high63,
        "volume_attention_20v43": volume_attention,
        "up_gap_count_20d": float(up_gaps),
        "median_abs_gap_20d_pct": median(abs_gaps),
        "vol20_pct": vol20,
        "vol_ratio_20v63": vol_ratio,
        "ddv20": ddv20(rows, i),
    }


def eligible_price_row(features: dict[str, Any]) -> bool:
    return bool(
        features
        and isinstance(features.get("price"), (int, float))
        and features["price"] >= 5
        and isinstance(features.get("ddv20"), (int, float))
        and features["ddv20"] >= 10_000_000
    )


def load_band(score: float | None) -> str | None:
    if score is None:
        return None
    if score < 30:
        return "low"
    if score < 70:
        return "mid"
    if score < 90:
        return "high"
    return "extreme"
