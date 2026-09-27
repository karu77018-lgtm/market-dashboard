"""再点火凸 backtest entry point.

  python run.py fetch    --period dev          # download + cache (resumable)
  python run.py backtest --period dev          # simulate + write output/dev/
  python run.py backtest --period holdout --open-holdout   # once, at the very end
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import numpy as np
import pandas as pd

import data
import report
from config import BASELINE_FLOORS, CACHE, OUTPUT, PERIODS, SLIPPAGES, Config
from sim import simulate_day
from watchlist import build_panel, combine, daily_nets, ext_candidates, ext_nets

EARLIEST = "2024-09-30"   # first grouped-daily session on the free tier
LOOKBACK_DAYS = 45        # calendar days before the period for 20-day medians


def _bounds(period: str) -> tuple[str, str]:
    start, end = PERIODS[period]
    return start, end


def _panel(start: str, end: str) -> pd.DataFrame:
    lo = max(EARLIEST, str(dt.date.fromisoformat(start) - dt.timedelta(days=LOOKBACK_DAYS)))
    allowed, splits = data.load_reference()
    return build_panel(data.load_daily(lo, end), allowed, splits)


def _sessions(panel: pd.DataFrame, start: str, end: str) -> list[int]:
    cal = panel.attrs["calendar"]
    return [i for i, d in enumerate(cal) if start <= d <= end and i >= 4]


def fetch(period: str) -> None:
    start, end = _bounds(period)
    api = data.Massive()
    lo = max(EARLIEST, str(dt.date.fromisoformat(start) - dt.timedelta(days=LOOKBACK_DAYS)))
    data.fetch_daily(api, lo, end)
    data.fetch_reference(api, EARLIEST, end)
    panel = _panel(start, end)
    cal = panel.attrs["calendar"]
    cfg = Config()
    needs: dict[str, set[str]] = {}
    for i in _sessions(panel, start, end):
        day, prev = cal[i], cal[i - 1]
        base = daily_nets(panel, i, cfg.watch)[: cfg.watch.cap_total]
        for t, _ in base:
            needs.setdefault(t, set()).add(day)
        if len(base) < cfg.watch.cap_total:
            for t in ext_candidates(panel, i, cfg.watch):
                needs.setdefault(t, set()).update({day, prev})
    data.fetch_minutes(api, needs, cal)
    print(f"done: {api.calls} API calls this run", flush=True)


def backtest(period: str, open_holdout: bool) -> None:
    if period == "holdout":
        marker = CACHE / "holdout_opened.json"
        if not open_holdout:
            sys.exit("holdout is sealed: pass --open-holdout only once, after parameters are final")
        if marker.exists():
            print(f"WARNING: holdout was already opened at {json.loads(marker.read_text())['at']}")
        else:
            marker.write_text(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds")}))
    start, end = _bounds(period)
    panel = _panel(start, end)
    cal = panel.attrs["calendar"]
    base_cfg = Config()
    variants = [(slip, floor_name, from_open)
                for slip in SLIPPAGES for floor_name in BASELINE_FLOORS for from_open in (False, True)]
    rows, watch_log, missing = [], [], 0
    for i in _sessions(panel, start, end):
        day, prev = cal[i], cal[i - 1]
        y = panel[panel["ci"] == i - 1].set_index("ticker")
        prev_close = y["c"].to_dict()
        today = panel[panel["ci"] == i].set_index("ticker")
        split_today = (today["f"] / y["f"].reindex(today.index)).dropna()
        split_today = {t: 1 / r for t, r in split_today.items() if abs(r - 1) > 1e-9}
        base = daily_nets(panel, i, base_cfg.watch)[: base_cfg.watch.cap_total]
        ext = []
        if len(base) < base_cfg.watch.cap_total:
            ext = ext_nets(ext_candidates(panel, i, base_cfg.watch), prev_close, split_today,
                           data.load_minutes, day, prev, base_cfg.watch)
        watch = combine(base, ext, base_cfg.watch.cap_total)
        bars = {}
        for t, _ in watch:
            b = data.load_minutes(t, day)
            if b is None:
                missing += 1
            bars[t] = b
        watch_log += [{"date": day, "ticker": t, "net": n} for t, n in watch]
        for slip, floor_name, from_open in variants:
            cfg = base_cfg.with_(exe__slippage=slip, signal__baseline_floor_per_min=BASELINE_FLOORS[floor_name])
            for tr in simulate_day(day, watch, bars, cfg, from_open=from_open):
                rows.append(tr | {"slippage": slip, "floor": floor_name, "from_open": from_open})
    if missing:
        print(f"WARNING: {missing} watchlist ticker-days have no cached minute file (run fetch)")
    trades = pd.DataFrame(rows)
    market = data.load_daily(cal[0], end)
    market = market[market["ticker"].isin(["SPY", "IWM"])].pivot(index="date", columns="ticker", values="c")
    report.write(period, (start, end), trades, pd.DataFrame(watch_log), market.pct_change(),
                 OUTPUT / period, missing)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "backtest"])
    ap.add_argument("--period", choices=list(PERIODS), default="dev")
    ap.add_argument("--open-holdout", action="store_true")
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.period)
    else:
        backtest(a.period, a.open_holdout)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
