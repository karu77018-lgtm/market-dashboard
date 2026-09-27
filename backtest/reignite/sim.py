"""One-day event simulation on 1-minute bars (the live bot judges every 5 s).

Timeline per minute m (bar m = [m, m+1) ET): pending orders try to fill on bar
m, open positions are managed on bar m, then bar m's close is checked for new
signals whose orders go to bar m+1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import Config

DAY_START, DAY_END = 4 * 60, 20 * 60
N = DAY_END - DAY_START


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@dataclass
class Grid:
    """Bars on a fixed 04:00-20:00 minute grid; NaN where no trade printed."""
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    turnover: np.ndarray   # 0 where missing
    last: np.ndarray       # forward-filled close (last trade seen)

    @classmethod
    def from_bars(cls, bars: pd.DataFrame) -> "Grid":
        arr = {k: np.full(N, np.nan) for k in "ohlc"}
        tv = np.zeros(N)
        if bars is not None and not bars.empty:
            b = bars[(bars["m"] >= DAY_START) & (bars["m"] < DAY_END)]
            i = b["m"].to_numpy() - DAY_START
            for k in "ohlc":
                arr[k][i] = b[k].to_numpy()
            tv[i] = (b["v"] * b["vw"]).to_numpy()
        last = pd.Series(arr["c"]).ffill().to_numpy()
        return cls(arr["o"], arr["h"], arr["l"], arr["c"], tv, last)


@dataclass
class Position:
    ticker: str
    net: str
    sig_m: int
    sig_px: float
    entry_m: int
    entry_px: float          # cost per share, includes slippage
    basis: float             # fill price before slippage; TP/stop levels key off this
    shares: int
    tiers: list[int]
    tier_done: list[bool]
    tp1: bool = False
    peak: float = 0.0        # highest high since entry (raw price)
    remaining: int = 0
    proceeds: float = 0.0
    fills: list = field(default_factory=list)


def _signals(g: Grid, m: int, cfg: Config, from_open: bool) -> bool:
    s = cfg.signal
    i = m - DAY_START
    if math.isnan(g.c[i]):
        return False
    lo = i - s.baseline_minutes
    if not from_open:
        lo = max(lo, hm("09:30") - DAY_START)       # live bot drops history at 09:30
        if i - lo < s.baseline_minutes:
            return False
    prev = g.last[i - 1] if i > 0 else np.nan
    if not prev > 0:
        return False
    chg = g.c[i] / prev - 1
    if not (s.min_change <= chg <= s.max_change):
        return False
    if g.turnover[i] < s.min_turnover:
        return False
    base = g.turnover[lo:i].sum() / s.baseline_minutes
    if base < s.baseline_floor_per_min:
        return False
    return g.turnover[i] >= s.min_vol_ratio * base


def _stop_level(p: Position, cfg: Config) -> float:
    e = cfg.exe
    lvl = e.initial_stop
    if p.tp1:
        lvl = max(lvl, e.after_tp1_stop)
    gain = p.peak / p.basis - 1
    for reach, stop in e.ladder:
        if gain >= reach:
            lvl = max(lvl, stop)
    return lvl


def _sell(p: Position, m: int, qty: int, px: float, reason: str, slip: float) -> None:
    fill = px * (1 - slip)
    p.proceeds += qty * fill
    p.remaining -= qty
    p.fills.append((m, qty, round(fill, 6), reason))


def simulate_day(day: str, watch: list[tuple[str, str]], bars: dict[str, pd.DataFrame], cfg: Config,
                 from_open: bool = False) -> list[dict]:
    e, s = cfg.exe, cfg.signal
    grids = {t: Grid.from_bars(bars.get(t)) for t, _ in watch}
    nets = dict(watch)
    first_sig = hm("09:30") if from_open else hm(s.first_signal_minute)
    last_sig, flat = hm(s.last_signal_minute), hm(e.flat_time)
    last_detect: dict[str, int] = {}
    last_exit: dict[str, int] = {}
    pending: dict[str, tuple[int, float]] = {}
    open_pos: dict[str, Position] = {}
    trades: list[dict] = []

    def close_out(p: Position, m: int, reason: str) -> None:
        cost = p.shares * p.entry_px
        trades.append({
            "date": day, "ticker": p.ticker, "net": p.net, "sig_time": _clock(p.sig_m),
            "entry_time": _clock(p.entry_m), "exit_time": _clock(m), "sig_px": p.sig_px,
            "entry_px": round(p.entry_px, 6), "shares": p.shares, "cost": round(cost, 2),
            "pnl": round(p.proceeds - cost, 2), "pnl_pct": (p.proceeds - cost) / cost,
            "peak_pct": p.peak / p.basis - 1, "exit_reason": reason, "fills": p.fills,
        })
        last_exit[p.ticker] = m
        del open_pos[p.ticker]

    for m in range(hm("09:30"), DAY_END):
        i = m - DAY_START
        # 1) pending buy orders placed on bar m-1
        for t, (sig_m, sig_px) in list(pending.items()):
            del pending[t]
            g = grids[t]
            if math.isnan(g.o[i]):                       # no print: halt / nothing traded
                continue
            if g.o[i] <= sig_px * (1 - e.abandon_drop):  # already -3% when the order would work
                continue
            limit = sig_px * (1 + e.limit_markup)
            if g.l[i] > limit:                           # never came back to the limit
                continue
            shares = int(e.notional // sig_px)
            if shares < 1:
                continue
            q1 = int(shares * e.tp_fracs[0])
            q2 = int(shares * (e.tp_fracs[0] + e.tp_fracs[1])) - q1
            tiers = [q1, q2, shares - q1 - q2]
            base = max(g.o[i], limit)                    # pessimistic: never better than the limit
            p = Position(t, nets[t], sig_m, sig_px, m, base * (1 + e.slippage), base, shares, tiers,
                         [q == 0 for q in tiers], peak=base, remaining=shares)
            open_pos[t] = p
            # fill bar: only the stop can act (order of high/low inside the bar is unknown)
            stop_px = base * (1 + e.initial_stop)
            if g.l[i] <= stop_px:
                _sell(p, m, p.remaining, stop_px, "stop", e.slippage)
                close_out(p, m, "stop")

        # 2) manage open positions on bar m
        for t, p in list(open_pos.items()):
            if p.entry_m == m:
                continue
            g = grids[t]
            if math.isnan(g.o[i]):
                if m == DAY_END - 1:
                    _sell(p, m, p.remaining, g.last[i], "eod", e.slippage)
                    close_out(p, m, "eod")
                continue
            if m >= flat or m - p.entry_m >= e.max_hold_min:
                _sell(p, m, p.remaining, g.o[i], "time", e.slippage)
                close_out(p, m, "time")
                continue
            stop_px = p.basis * (1 + _stop_level(p, cfg))
            if g.l[i] <= stop_px:                        # stop wins ties with take-profit
                _sell(p, m, p.remaining, min(g.o[i], stop_px), "stop", e.slippage)
                close_out(p, m, "stop")
                continue
            for k, lvl in enumerate(e.tp_levels):
                px = p.basis * (1 + lvl)
                if p.tier_done[k] or g.h[i] < px:
                    continue
                qty = p.remaining if k == len(e.tp_levels) - 1 else min(p.tiers[k], p.remaining)
                # resting limit sell: fills at its price, or at the open if the bar gaps above it
                _sell(p, m, qty, max(px, g.o[i]), f"tp{k + 1}", e.slippage)
                p.tier_done[k] = True
                p.tp1 = p.tp1 or k == 0
            p.peak = max(p.peak, g.h[i])
            if p.remaining <= 0:
                close_out(p, m, "tp3")

        # 3) signals on bar m -> orders for bar m+1
        if first_sig <= m <= last_sig:
            for t, _ in watch:
                if t in open_pos or t in pending:
                    continue
                if m - last_detect.get(t, -10_000) < s.redetect_gap_min:
                    continue
                if not _signals(grids[t], m, cfg, from_open):
                    continue
                last_detect[t] = m
                if m - last_exit.get(t, -10_000) < e.reentry_gap_min:
                    continue
                if len(open_pos) + len(pending) >= e.max_positions:
                    continue
                pending[t] = (m, grids[t].c[i])
    return trades


def _clock(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"
