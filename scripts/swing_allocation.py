"""Current normal-swing allocation, independent of entry/exit and sleeve rules.

2026-10-12: back to 6 names x 1/6.  The 5 x 20% change (2026-10-09) rested on a
backtest that bought at the signal-day close; with next-open fills (the only
price a reader can get, signals publish after the close) 6 x 1/6 is as good or
better in both halves of 2015-2026.
"""
RULE_ID = "swing-v5-max6-tqqq-sleeve"
MAX_NAMES = 6
INITIAL_WEIGHT = 1 / 6
INITIAL_LABEL = "1/6（約16.7%）"
EFFECTIVE_DATE = "2026-10-12"
