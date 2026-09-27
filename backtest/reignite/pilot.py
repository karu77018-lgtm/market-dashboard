"""Limited pilot: 20 random dev-period days, nets 2日目 + プレ発 only.

Data arrives through the Massive connector (free tier) as saved tool-result
text files; this script ingests them, plans which ticker-days still need
minute bars, and runs the same simulator/report as the full backtest.

  python pilot.py ingest    # copy connector results into pilot/ and cache/minute
  python pilot.py plan      # list ticker-days whose minute bars are missing
  python pilot.py run       # simulate + write output/pilot/
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import data
import report
from config import BASELINE_FLOORS, OUTPUT, SLIPPAGES, Config
from sim import simulate_day
from watchlist import combine, ext_nets

HERE = Path(__file__).resolve().parent
PILOT = HERE / "pilot"
RESULTS = Path("/root/.claude/projects/-home-user-market-dashboard") / "b9ddc942-2824-53b8-877e-cf9d5b7690d6" / "tool-results"
ET = ZoneInfo("America/New_York")
DAY2_TOP, PRE_TOP = 4, 8
NON_COMMON = re.compile(r"^[A-Z]{4}[WRU]$|[.\-p]")  # warrants / rights / units / preferred
ETFS = {"SOXL", "SOXS", "TQQQ", "SQQQ", "LABU", "LABD", "TZA", "TNA", "UVXY", "SVXY", "VXX", "UVIX", "SVIX",
        "NVDL", "NVDS", "NVDQ", "TSLL", "TSLQ", "TSLZ", "TSLS", "MSTU", "MSTZ", "CONL", "BITX", "SPXS", "SPXU",
        "SDOW", "UDOW", "YANG", "YINN", "FAZ", "FAS", "DRIP", "GUSH", "BOIL", "KOLD", "UCO", "SCO", "ZSL",
        "AGQ", "JDST", "JNUG", "NUGT", "DUST", "SOXS", "TECS", "TECL", "WEBS", "FNGD", "BERZ", "HIBS", "SPDN",
        "SH", "PSQ", "SDS", "QID", "DXD", "ETHU", "ETHD", "SBIT", "BITI", "MSTX", "AMDL", "PLTD", "NVD", "TSLT"}


def _rows(text: str, ncols: int) -> list[str]:
    return [l for l in text.splitlines() if l.count(",") == ncols - 1 and not l.startswith("...")]


def ingest() -> None:
    (PILOT / "grouped").mkdir(parents=True, exist_ok=True)
    for f in sorted(RESULTS.glob("mcp-Massive-get_grouped_daily-*.txt")) + sorted((PILOT / "inline").glob("grouped_*.txt")):
        text = f.read_text()
        m = re.match(r"date=(\d{4}-\d{2}-\d{2})", text)
        if not m:
            continue
        rows = _rows(text, 10)
        if rows and rows[0].startswith("ticker,") and len(rows) > 50:
            (PILOT / "grouped" / f"{m.group(1)}.csv").write_text("\n".join(rows) + "\n")
    n = 0
    for f in sorted(RESULTS.glob("mcp-Massive-get_bars-*.txt")) + sorted((PILOT / "inline").glob("bars_*.txt")):
        text = f.read_text()
        m = re.match(r"(\S+) 1minute (\d{4}-\d{2}-\d{2})\.\.", text)
        if not m:
            continue
        ticker, day = m.groups()
        rows = _rows(text, 7)
        df = pd.read_csv(io.StringIO("\n".join(rows))) if rows else pd.DataFrame(columns=["time"])
        if not df.empty:
            ts = pd.to_datetime(df["time"].str.rstrip("Z"), utc=True).dt.tz_convert(ET)
            df = df.assign(day=ts.dt.strftime("%Y-%m-%d"), m=ts.dt.hour * 60 + ts.dt.minute)
            df = df[df["day"] == day].rename(columns={"open": "o", "high": "h", "low": "l", "close": "c",
                                                     "volume": "v", "vwap": "vw"})
            # a truncated last line could only affect a later day; the first day is complete
        out = data.minute_path(ticker, day)
        out.parent.mkdir(parents=True, exist_ok=True)
        (df[data.MINUTE_COLS] if not df.empty else pd.DataFrame(columns=data.MINUTE_COLS)).to_parquet(out, index=False)
        n += 1
    print(f"grouped days: {len(list((PILOT / 'grouped').glob('*.csv')))}, minute files ingested: {n}")


def _grouped(day: str) -> pd.DataFrame | None:
    p = PILOT / "grouped" / f"{day}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df = df[~df["ticker"].str.contains(NON_COMMON) & ~df["ticker"].isin(ETFS)]
    splits = _splits()
    df = df[~df["ticker"].isin(splits.get(day, set()))]
    return df.assign(gap=df["open"] / df["prev_close"] - 1)


def _splits() -> dict[str, set[str]]:
    p = PILOT / "splits.csv"
    if not p.exists():
        return {}
    s = pd.read_csv(p)
    return s.groupby("date")["ticker"].agg(set).to_dict()


def watch_for(day: str, prev: str, cfg: Config) -> tuple[list[tuple[str, str]], list[str], pd.DataFrame, pd.DataFrame]:
    w = cfg.watch
    y, t = _grouped(prev), _grouped(day)
    day2 = y[(y["change_pct"] >= w.day2_gain * 100) & y["close"].between(w.price_min, w.price_max)]
    day2_list = [(x, "2日目") for x in day2.sort_values("dollar_volume", ascending=False)["ticker"].head(DAY2_TOP)]
    taken = {x for x, _ in day2_list}
    c = t[(t["gap"] >= w.ext_candidate_gap) & t["open"].between(w.price_min, w.price_max) & ~t["ticker"].isin(taken)]
    pre_cands = list(c.sort_values("gap", ascending=False)["ticker"].head(PRE_TOP))
    return day2_list, pre_cands, y, t


def plan() -> None:
    cfg = Config()
    days = pd.read_csv(PILOT / "days.csv")
    need = []
    for r in days.itertuples():
        if _grouped(r.day) is None or _grouped(r.prev) is None:
            print(f"{r.day}: grouped missing ({r.prev} / {r.day})")
            continue
        d2, pre, _, _ = watch_for(r.day, r.prev, cfg)
        for x in [a for a, _ in d2] + pre:
            if not data.minute_path(x, r.day).exists():
                need.append((x, r.day))
    print(f"missing minute ticker-days: {len(need)}")
    for x, d in need:
        print(x, d)


def run() -> None:
    base_cfg = Config()
    days = pd.read_csv(PILOT / "days.csv")
    rows, watch_log, missing = [], [], 0
    for r in days.itertuples():
        d2, pre, y, t = watch_for(r.day, r.prev, base_cfg)
        prev_close = t.set_index("ticker")["prev_close"].to_dict()
        pre_list = ext_nets(pre, prev_close, {}, lambda x, d: data.load_minutes(x, d) if d == r.day else None,
                            r.day, r.prev, base_cfg.watch)
        watch = combine(d2, pre_list, base_cfg.watch.cap_total)
        bars = {x: data.load_minutes(x, r.day) for x, _ in watch}
        missing += sum(b is None for b in bars.values())
        watch_log += [{"date": r.day, "ticker": x, "net": n} for x, n in watch]
        for slip in SLIPPAGES:
            for floor_name, floor in BASELINE_FLOORS.items():
                for from_open in (False, True):
                    cfg = base_cfg.with_(exe__slippage=slip, signal__baseline_floor_per_min=floor)
                    for tr in simulate_day(r.day, watch, bars, cfg, from_open=from_open):
                        rows.append(tr | {"slippage": slip, "floor": floor_name, "from_open": from_open})
    market = []
    for d in sorted(set(days["day"])):
        g = pd.read_csv(PILOT / "grouped" / f"{d}.csv")
        g = g[g["ticker"].isin(["SPY", "IWM"])].set_index("ticker")["change_pct"] / 100
        market.append(g.rename(d))
    report.write("pilot", (days["day"].min(), days["day"].max()), pd.DataFrame(rows), pd.DataFrame(watch_log),
                 pd.DataFrame(market), OUTPUT / "pilot", missing)


if __name__ == "__main__":
    np.seterr(all="ignore")
    {"ingest": ingest, "plan": plan, "run": run}[sys.argv[1]]()
