#!/usr/bin/env python3
"""Backtest the deterministic Expectation Load baseline without Jev.

Uses only repository chart-data and point-in-time price history.
Research caveat: the cached symbol universe can contain survivorship/coverage bias.

Snapshots are spaced 21 trading sessions apart to reduce overlap for the 20D horizon.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def q(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    x = (len(s) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def pct_map(vals: dict[str, float]) -> dict[str, float]:
    ordered = sorted((v, k) for k, v in vals.items())
    n = len(ordered)
    out: dict[str, float] = {}
    if not n:
        return out
    i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][0] == ordered[i][0]:
            j += 1
        mid = (i + j - 1) / 2
        pct = 50.0 if n == 1 else 100.0 * mid / (n - 1)
        for _, k in ordered[i:j]:
            out[k] = pct
        i = j
    return out


def norm(rows: list[list[Any]]) -> list[tuple[str, float, float, float, float, float]]:
    out = []
    for r in rows:
        try:
            out.append((str(r[0])[:10], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
        except (IndexError, TypeError, ValueError):
            pass
    return out


def load_series(root: Path) -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    idx = json.loads((root / "chart-data/index.json").read_text())
    out: dict[str, list[tuple[str, float, float, float, float, float]]] = {}
    for sh in sorted(set(idx.get("ticker_to_shard", {}).values())):
        if not isinstance(sh, int):
            continue
        p = root / f"chart-data/shard-{sh:02d}.json"
        data = json.loads(p.read_text())
        for ticker, rows in data.items():
            rr = norm(rows)
            if rr:
                out[ticker] = rr
    return out


def at_index(rows, date: str) -> int:
    dates = [r[0] for r in rows]
    return bisect.bisect_right(dates, date) - 1


def snapshot_features(series, date: str) -> dict[str, dict[str, float]]:
    base: dict[str, dict[str, float]] = {}
    r21: dict[str, float] = {}
    r63: dict[str, float] = {}
    r189: dict[str, float] = {}
    highprox: dict[str, float] = {}
    ext50: dict[str, float] = {}
    rv: dict[str, float] = {}

    for ticker, rows in series.items():
        i = at_index(rows, date)
        if i < 252 or i + 20 >= len(rows):
            continue
        close = rows[i][4]
        if close < 5:
            continue
        ddv = statistics.median(rows[j][4] * rows[j][5] for j in range(i - 19, i + 1))
        if ddv < 1e7:
            continue
        sma50 = statistics.fmean(rows[j][4] for j in range(i - 49, i + 1))
        avgvol20 = statistics.fmean(rows[j][5] for j in range(i - 19, i + 1))
        high252 = max(rows[j][2] for j in range(i - 251, i + 1))
        if min(sma50, avgvol20, high252) <= 0:
            continue
        r21[ticker] = (close / rows[i - 21][4] - 1) * 100
        r63[ticker] = (close / rows[i - 63][4] - 1) * 100
        r189[ticker] = (close / rows[i - 189][4] - 1) * 100
        highprox[ticker] = (close / high252 - 1) * 100
        ext50[ticker] = (close / sma50 - 1) * 100
        rv[ticker] = rows[i][5] / avgvol20
        base[ticker] = {"i": i, "close": close, "ddv20": ddv}

    rs21 = pct_map(r21)
    rs63 = pct_map(r63)
    rs189 = pct_map(r189)
    accel = pct_map({t: rs21[t] - rs63[t] for t in base if t in rs21 and t in rs63})
    hp = pct_map(highprox)
    e50 = pct_map(ext50)
    rvp = pct_map(rv)

    raw = {}
    for t in base:
        vals = [rs21.get(t), accel.get(t), hp.get(t), e50.get(t), rvp.get(t)]
        vals = [v for v in vals if v is not None]
        if len(vals) < 4:
            continue
        raw[t] = statistics.fmean(vals)
        base[t].update({
            "rs21": rs21.get(t),
            "rs63": rs63.get(t),
            "rs189": rs189.get(t),
            "rs_accel_pctile": accel.get(t),
            "high_proximity_pctile": hp.get(t),
            "extension50_pctile": e50.get(t),
            "relative_volume_pctile": rvp.get(t),
        })
    load = pct_map(raw)
    return {t: {**base[t], "expectation_load_pctile": load[t]} for t in load}


def bucket(load: float, mode: str) -> str:
    if mode == "tertile":
        return "low" if load < 33.333 else "mid" if load < 66.667 else "high"
    if load < 20:
        return "Q1_low"
    if load < 40:
        return "Q2"
    if load < 60:
        return "Q3"
    if load < 80:
        return "Q4"
    return "Q5_high"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"n": len(rows)}
    for h in (5, 10, 20):
        vals = [r[f"ret{h}"] for r in rows if r.get(f"ret{h}") is not None]
        ex = [r[f"excess{h}"] for r in rows if r.get(f"excess{h}") is not None]
        out[f"ret{h}"] = {
            "mean": statistics.fmean(vals) if vals else None,
            "median": q(vals, .5),
            "p10": q(vals, .1),
            "win_rate": statistics.fmean([v > 0 for v in vals]) if vals else None,
        }
        out[f"excess{h}"] = {
            "mean": statistics.fmean(ex) if ex else None,
            "median": q(ex, .5),
            "win_rate": statistics.fmean([v > 0 for v in ex]) if ex else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--step", type=int, default=21)
    ap.add_argument("--output", default="research/expectation_gap/expectation-load-backtest-v1.json")
    ap.add_argument("--report", default="maintenance/expectation-load-backtest-v1-20260930.md")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    series = load_series(root)
    qqq = series.get("QQQ")
    if not qqq:
        raise SystemExit("QQQ missing from chart-data")
    qdates = [r[0] for r in qqq]
    start_i = max(252, bisect.bisect_left(qdates, args.start))
    end_i = len(qdates) - 21
    snapshot_dates = qdates[start_i:end_i:args.step]

    observations = []
    snapshot_counts = []
    for date in snapshot_dates:
        feats = snapshot_features(series, date)
        qi = at_index(qqq, date)
        if qi < 0 or qi + 20 >= len(qqq):
            continue
        qfwd = {h: (qqq[qi + h][4] / qqq[qi][4] - 1) * 100 for h in (5, 10, 20)}
        leaders = 0
        for ticker, x in feats.items():
            if (x.get("rs63") or 0) < 70 or (x.get("rs189") or 0) < 70:
                continue
            rows = series[ticker]
            i = int(x["i"])
            obs = {
                "date": date,
                "ticker": ticker,
                "expectation_load_pctile": x["expectation_load_pctile"],
                "rs21": x.get("rs21"),
                "rs63": x.get("rs63"),
                "rs189": x.get("rs189"),
            }
            for h in (5, 10, 20):
                ret = (rows[i + h][4] / rows[i][4] - 1) * 100
                obs[f"ret{h}"] = ret
                obs[f"excess{h}"] = ret - qfwd[h]
            observations.append(obs)
            leaders += 1
        snapshot_counts.append(leaders)

    by_tertile = {}
    by_quintile = {}
    for b in ("low", "mid", "high"):
        by_tertile[b] = summarize([r for r in observations if bucket(r["expectation_load_pctile"], "tertile") == b])
    for b in ("Q1_low", "Q2", "Q3", "Q4", "Q5_high"):
        by_quintile[b] = summarize([r for r in observations if bucket(r["expectation_load_pctile"], "quintile") == b])

    payload = {
        "version": "expectation-load-backtest-v1",
        "method": {
            "snapshot_spacing_sessions": args.step,
            "start": args.start,
            "filters": ["price >= $5", "DDV20 >= $10M", ">=252 prior sessions", "RS63 >=70", "RS189 >=70"],
            "components": ["RS21 percentile", "RS21-RS63 acceleration percentile", "52w-high proximity percentile", "50MA extension percentile", "relative-volume percentile"],
            "load": "equal-weight component mean, cross-sectionally re-ranked",
            "benchmark": "QQQ",
            "warning": "research baseline; current cached universe can introduce survivorship/coverage bias",
        },
        "snapshots": len(snapshot_dates),
        "observations": len(observations),
        "median_leaders_per_snapshot": statistics.median(snapshot_counts) if snapshot_counts else 0,
        "by_tertile": by_tertile,
        "by_quintile": by_quintile,
    }
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")

    lines = [
        "# Expectation Load backtest v1 — 2026-09-30",
        "",
        "Deterministic price-only baseline. Jev is not used in this backtest.",
        "",
        f"- Snapshots: {payload['snapshots']} (every {args.step} sessions)",
        f"- Leader observations: {payload['observations']}",
        f"- Median leaders / snapshot: {payload['median_leaders_per_snapshot']}",
        "",
        "## Tertiles",
        "",
        "| Load | n | 5D median | 5D excess | 10D median | 10D excess | 20D median | 20D excess |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in ("low", "mid", "high"):
        s = by_tertile[b]
        def ff(x):
            return "—" if x is None else f"{x:.2f}%"
        lines.append(
            f"| {b} | {s['n']} | {ff(s['ret5']['median'])} | {ff(s['excess5']['median'])} | "
            f"{ff(s['ret10']['median'])} | {ff(s['excess10']['median'])} | "
            f"{ff(s['ret20']['median'])} | {ff(s['excess20']['median'])} |"
        )
    lines += [
        "",
        "## Interpretation guard",
        "- This tests whether the deterministic expectation-load concept has useful separation before adding Jev semantics.",
        "- It is not a production signal and is not sufficient to set weights.",
        "- Survivorship/coverage bias must be addressed before final adoption.",
        "",
    ]
    rep = root / args.report
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(lines))
    print(json.dumps({"ok": True, "snapshots": payload["snapshots"], "observations": payload["observations"], "by_tertile": by_tertile}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
