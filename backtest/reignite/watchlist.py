"""Daily watchlists built only from information available before the open.

D3S / 2日目 / 再点火 use daily bars up to the previous close. アフター急騰 uses
the previous day's 16:00-20:00 minute bars, プレ発 today's 04:00-09:29 bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import WatchlistRules

NETS = ("D3S", "2日目", "再点火", "アフター", "プレ発")


def build_panel(daily: pd.DataFrame, allowed: set[str], splits: pd.DataFrame) -> pd.DataFrame:
    """Split-adjusted daily panel with previous-day fields on consecutive sessions."""
    df = daily[daily["ticker"].isin(allowed)].copy()
    calendar = sorted(df["date"].unique())
    df["ci"] = df["date"].map({d: i for i, d in enumerate(calendar)})
    # price factor: bars before a split's execution date are scaled to the post-split basis
    df["f"] = 1.0
    rows_by_ticker = df.groupby("ticker").indices
    for s in splits.itertuples():
        idx = rows_by_ticker.get(s.ticker)
        if idx is not None and s.split_to and s.split_from:
            before = idx[df["date"].to_numpy()[idx] < s.date]
            df.loc[df.index[before], "f"] *= s.split_from / s.split_to
    for col in ("o", "h", "l", "c"):
        df[col + "_a"] = df[col] * df["f"]
    df["v_a"] = df["v"] / df["f"]
    df = df.sort_values(["ticker", "ci"]).reset_index(drop=True)
    g = df.groupby("ticker", sort=False)
    consecutive = g["ci"].diff() == 1
    df["pc_a"] = g["c_a"].shift().where(consecutive)
    df["chg"] = df["c_a"] / df["pc_a"] - 1
    df["hi_chg"] = df["h_a"] / df["pc_a"] - 1
    df["med20"] = g["v_a"].transform(lambda s: s.shift().rolling(20, min_periods=20).median())
    df["dollar"] = df["c"] * df["v"]
    df.attrs["calendar"] = calendar
    return df


def _price_ok(close: pd.Series, rules: WatchlistRules, hi: float | None = None) -> pd.Series:
    return close.between(rules.price_min, hi or rules.price_max)


def daily_nets(panel: pd.DataFrame, i: int, rules: WatchlistRules) -> list[tuple[str, str]]:
    """Ordered (ticker, net) for session index i, using sessions <= i-1 only."""
    by_ci = {k: panel[panel["ci"] == i - k].set_index("ticker") for k in range(1, 5)}
    y = by_ci[1]
    out: list[tuple[str, str]] = []

    # D3S: Day1 = i-2 (+50%, 10M shares, close >= $0.10), Day2 = i-1 closes below Day1
    d1 = by_ci[2]
    d1 = d1[(d1["chg"] >= rules.d3s_day1_gain) & (d1["v"] >= rules.d3s_day1_volume)
            & (d1["c"] >= rules.d3s_day1_close_min)]
    both = y.join(d1[["c_a"]], rsuffix="_d1", how="inner")
    both = both[(both["pc_a"].notna()) & (both["c_a"] < both["c_a_d1"]) & _price_ok(both["c"], rules)]
    out += [(t, "D3S") for t in both.sort_values("dollar", ascending=False).index]

    # 2日目
    day2 = y[(y["chg"] >= rules.day2_gain) & _price_ok(y["c"], rules)]
    out += [(t, "2日目") for t in day2.sort_values("dollar", ascending=False).index]

    # 再点火: spike 1-3 sessions ago, then calm days that keep >= 30% of the spike
    hits: dict[str, float] = {}
    for k in rules.reignite_lookback:
        s = by_ci.get(k)
        if s is None or s.empty:
            continue
        s = s[(s["hi_chg"] >= rules.reignite_high_gain) & (s["v_a"] >= rules.reignite_vol_mult * s["med20"])]
        for t, row in s.iterrows():
            if t not in y.index or not _price_ok(pd.Series([y.at[t, "c"]]), rules, rules.reignite_price_max).iat[0]:
                continue
            after = [by_ci[j].at[t, "chg"] if t in by_ci[j].index else np.nan for j in range(1, k)]
            if any(not np.isfinite(a) or abs(a) > rules.reignite_max_daily_move for a in after):
                continue
            base = row["pc_a"]
            keep = base + rules.reignite_hold_frac * (row["h_a"] - base)
            if y.at[t, "c_a"] >= keep:
                hits[t] = max(hits.get(t, 0.0), y.at[t, "dollar"])
    out += [(t, "再点火") for t in sorted(hits, key=hits.get, reverse=True)]

    seen: set[str] = set()
    unique = []
    for t, net in out:
        if t not in seen:
            seen.add(t)
            unique.append((t, net))
    return unique


def ext_candidates(panel: pd.DataFrame, i: int, rules: WatchlistRules) -> list[str]:
    """Tickers whose minute bars are downloaded to test アフター/プレ発 for session i.

    Uses session i's open only to choose downloads (a coverage filter); the
    rules themselves are evaluated on pre-09:30 minute bars.
    """
    today = panel[panel["ci"] == i]
    today = today.assign(gap=today["o_a"] / today["pc_a"] - 1)
    c = today[(today["gap"] >= rules.ext_candidate_gap) & today["pc_a"].notna()]
    return list(c.sort_values("gap", ascending=False)["ticker"].head(rules.ext_candidate_top_n))


def _first_trigger(bars: pd.DataFrame, ref: float, lo: int, hi: int, gain: float, turnover: float,
                   rules: WatchlistRules) -> int | None:
    b = bars[(bars["m"] >= lo) & (bars["m"] < hi)]
    if b.empty or not ref > 0:
        return None
    cum = (b["v"] * b["vw"]).cumsum()
    ok = (b["c"] / ref - 1 >= gain) & (cum >= turnover) & b["c"].between(rules.price_min, rules.price_max)
    return int(b.loc[ok, "m"].iloc[0]) if ok.any() else None


def ext_nets(cands: list[str], prev_close_raw: dict[str, float], split_ratio_today: dict[str, float],
             load, day: str, prev_day: str, rules: WatchlistRules) -> list[tuple[str, str]]:
    after, pre = [], []
    for t in cands:
        ref = prev_close_raw.get(t)
        if ref is None:
            continue
        pbars = load(t, prev_day)
        if pbars is not None and not pbars.empty:
            m = _first_trigger(pbars, ref, 16 * 60, 20 * 60, rules.after_gain, rules.after_turnover, rules)
            if m is not None:
                after.append((m, t))
        tbars = load(t, day)
        if tbars is not None and not tbars.empty:
            ref_today = ref * split_ratio_today.get(t, 1.0)
            m = _first_trigger(tbars, ref_today, 4 * 60, 9 * 60 + 30, rules.pre_gain, rules.pre_turnover, rules)
            if m is not None:
                pre.append((m, t))
    return ([(t, "アフター") for _, t in sorted(after)[: rules.after_cap]]
            + [(t, "プレ発") for _, t in sorted(pre)[: rules.pre_cap]])


def combine(daily_list: list[tuple[str, str]], ext_list: list[tuple[str, str]], cap: int) -> list[tuple[str, str]]:
    seen, out = set(), []
    for t, net in daily_list + ext_list:
        if t not in seen:
            seen.add(t)
            out.append((t, net))
    return out[:cap]
