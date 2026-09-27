"""再点火凸 backtest parameters.

Values mirror the 2026-09-26 design document (moomoo demo settings). Anything
the document leaves ambiguous is marked INTERPRETATION and listed in the
report's deviation table.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUTPUT = HERE / "output"

# Free-tier history starts ~2 years back. Parameters are chosen on DEV only;
# HOLDOUT is opened once at the end. The live demo (2026-09-08..09-25) was
# used to design the rules, so it is reported separately, never as holdout.
PERIODS = {
    "dev": ("2024-10-01", "2025-09-30"),
    "validation": ("2025-10-01", "2026-03-31"),
    "holdout": ("2026-04-01", "2026-09-04"),
    "demo": ("2026-09-08", "2026-09-25"),
}


@dataclass(frozen=True)
class WatchlistRules:
    price_min: float = 0.5
    price_max: float = 20.0
    reignite_price_max: float = 50.0
    cap_total: int = 40
    # D3S
    d3s_day1_gain: float = 0.50
    d3s_day1_volume: float = 10_000_000
    d3s_day1_close_min: float = 0.10
    # 2日目
    day2_gain: float = 0.30
    # 再点火
    reignite_high_gain: float = 0.25
    reignite_vol_mult: float = 4.0
    reignite_median_days: int = 20
    reignite_max_daily_move: float = 0.20
    reignite_hold_frac: float = 0.30
    reignite_lookback: tuple[int, ...] = (1, 2, 3)
    # アフター急騰 (previous day's after-hours)
    after_gain: float = 0.20
    after_turnover: float = 300_000
    after_cap: int = 10
    # プレ発 (today's pre-market, only what is known before 09:30)
    pre_gain: float = 0.20
    pre_turnover: float = 200_000
    pre_cap: int = 10
    # Download pre-filter for the extended-hours nets (daily data has no
    # pre/after split). Only decides which minute files to fetch; the rule
    # itself is evaluated on minute bars. INTERPRETATION / coverage limit.
    ext_candidate_gap: float = 0.10
    ext_candidate_top_n: int = 15


@dataclass(frozen=True)
class SignalRules:
    min_change: float = 0.03          # 1-minute rise
    max_change: float = 0.25          # 上げすぎ除外
    min_turnover: float = 400_000     # $ traded in the signal minute
    min_vol_ratio: float = 3.0        # vs baseline
    baseline_minutes: int = 10
    # Baseline floor in $/minute. The document says "$30K 未満" of the
    # per-second turnover. Literally that is $1.8M/min; the likely intent
    # (a "no book" guard) is far lower. Reported as sensitivity variants.
    baseline_floor_per_min: float = 30_000 * 60
    first_signal_minute: str = "09:40"  # live bot cannot judge until ~09:40
    last_signal_minute: str = "15:59"
    redetect_gap_min: int = 15


@dataclass(frozen=True)
class ExecRules:
    notional: float = 1_000.0
    limit_markup: float = 0.01
    abandon_drop: float = 0.03        # cancel if -3% from signal before fill
    slippage: float = 0.01            # one-way, applied to every fill
    max_positions: int = 5
    reentry_gap_min: int = 45
    # exits
    tp_levels: tuple[float, ...] = (0.05, 0.10, 0.15)
    tp_fracs: tuple[float, ...] = (1 / 6, 2 / 3, 1 / 6)
    initial_stop: float = -0.08
    after_tp1_stop: float = 0.02
    ladder: tuple[tuple[float, float], ...] = ((0.05, 0.02), (0.10, 0.05), (0.15, 0.08), (0.20, 0.13))
    max_hold_min: int = 240
    flat_time: str = "15:50"


@dataclass(frozen=True)
class Config:
    watch: WatchlistRules = field(default_factory=WatchlistRules)
    signal: SignalRules = field(default_factory=SignalRules)
    exe: ExecRules = field(default_factory=ExecRules)

    def with_(self, **kw) -> "Config":
        parts = {"watch": self.watch, "signal": self.signal, "exe": self.exe}
        for key, value in kw.items():
            section, name = key.split("__")
            parts[section] = replace(parts[section], **{name: value})
        return Config(**parts)


SLIPPAGES = (0.005, 0.01, 0.02)
BASELINE_FLOORS = {
    "literal $30K/sec": 30_000 * 60,
    "$30K/min": 30_000,
    "$30K per 10min": 3_000,
}
