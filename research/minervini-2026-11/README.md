# Minervini checks and "indicator-free" chart reading (2026-11-26..27, run locally)

Kept: 本命 needs the close at least 2x the 52-week low (+100% off the low), live from the 2026-11-27 判定.
Not kept: VCP rules as entry conditions, 200-day line rising 3 months, a new 52-week high within 6 months,
more slots, and the chart-reading gauges below as stock signals.

## 1. Chart reading as numbers (`chart-features/`)

`universe.py` (chart-data, 50-day dollar volume >= $30M and price >= $10 today: 1,536 names) -> `dl.py` (Yahoo daily
from 2015) -> `features.py` (no look-ahead: pivots used 5 bars after they form) -> `runall.py` -> `evaluate.py`
(next-open entry, 20-day return minus the same day's median) and `market.py` (QQQ next 20/60 days by bucket).

- Stocks: market structure (HH/HL, break of structure, change of character), tested resistance breaks, volume
  profile (overhead supply, POC), anchored VWAP from the 52-week high/low, UD ratio, distribution days, close
  location, VCP-style squeeze breaks, pocket pivots, liquidity. Rank IC all under ~0.02; no event beat its own
  group's average (trend-template names). Overhead supply is mostly distance from the high (rank corr 0.85).
  Liquidity looks "small is better" but that is survivorship from picking today's liquid names.
- Market: net liquidity (WALCL - WTREGEN - RRP, one week lag) 13-week change: top fifth QQQ +8.4% / 60 days,
  median dip -2.6%; bottom fifth +2.4% / -4.6%; same order in 2016-20 and 2021-26. QQQ distribution days: more
  days = deeper dips (0-2: -2.6%, 7+: -5.2%) but no lower 60-day return. Breadth washouts helped only 2016-20.
- Results page: Claude Data artifact "インジに出ない要素の数値化と検証" (`build_data.py` writes its files).

## 2. Minervini setup as written (`chart-features/vcp.py`, `vcp_eval.py`)

Contraction depth = 1 - swing low / swing high, each shallower than the last; buy stop above the last swing high;
stop 2 x ATR20 capped at 10%; exit on a close under the 50-day line (or 60 days). Text filters (200-day up 3 months,
+100% off the low, new high within 126 days) vs the book template (200-day up 1 month, +30%).

Text filters, per trade: buying every Friday +1.82%, 20-day high break +2.99%, VCP (2+ contractions) +2.25%,
3+ contractions +0.99%, the full text set +2.99% on 144 trades. Win rate about 30% everywhere (not 50%), wins
3.5-4x losses. The book template: Friday buys +0.93%. "Price >= $30" cannot be tested on split-adjusted prices.

## 3. On the production engine (`engine/`)

Rebuilt the engine of `record-context-2026-11` (fetch, panel, sig, tq, sim) and `scripts-2026-11` (prod3, runall,
x2, tp_x) with fresh prices for the 3,828 chart tickers. Same rule with the UD filter: 72.2% a year here vs 75.1% on
the site (fresh data); the UD filter's lift matches (+7.2 vs +7.1). `strict.py` writes `sig_feat.pkl` first.

| added to 本命 (UD filter on) | kept | a year | 2015-20 | 2021-26 | max DD |
|---|---|---|---|---|---|
| none | 100% | 72.2% | 56.9% | 90.9% | -30.4% |
| 200-day up 3 months | 96% | 70.8% | 58.4% | 86.1% | -30.4% |
| new 52-week high within 126 days | 98% | 70.9% | 57.1% | 87.7% | -30.5% |
| **+100% off the 52-week low** | 51% | **80.3%** | 67.6% | 96.0% | -30.7% |
| all three | 49% | 78.6% | 67.8% | 92.0% | -30.8% |

- Cuts +75%..+200%: 75.6-81.9%. Without the UD filter: 65.0 -> 72.1%.
- Random drops of the same share (`strict2.py`, 20): 59.2-75.5%. Same-day same-count random keeps
  (`matched_random.py`, 20, same time in stocks): 72.4-78.4% (median 75.6): about 3.4 points come from holding fewer
  stocks (more money in the TQQQ sleeve), about 4.7 from the selection. RS189 top half only: 76.0%.
- `decompose.py`: bought 278 -> 174; the dropped 121 trades averaged +1.0% (36% winners), the kept ones +6.4%.
  Stocks alone (no sleeve): 22.0% either way, on 19% vs 28% average stock weight. 2015-20 stocks alone 7.1 -> 5.5%.
- `persig.py` (next open, -8% stop, close under the 21-EMA of lows or -15% from the high close): +5.4 points a trade,
  month-block bootstrap > 0 in 99%; both halves better; 6 of 11 years.
- 2026 本命: 99% pass, so no change to today's picks. The lift sits in years when leaders are less extended.
- `slots.py`: 4/5/6/7/8/10/12 slots at 1/N: 69.2/-/72.2/72.7/72.5/71.1/69.2% (UD rule); 8 or 10 slots at 1/6 = 6 slots
  (the 80% stock cap binds first). `skipped.py`: of unbought 本命, 835 were already held, 151 under the entry stop,
  157 full / cap / data. Not kept.

Caveats: today's listings only (no delisted names), no costs or taxes, Yahoo prices refetched 2026-11-26.
