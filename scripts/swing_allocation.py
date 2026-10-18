"""Current normal-swing allocation, independent of entry/exit and sleeve rules.

2026-10-12: back to 6 names x 1/6.  The 5 x 20% change (2026-10-09) rested on a
backtest that bought at the signal-day close; with next-open fills (the only
price a reader can get, signals publish after the close) 6 x 1/6 is as good or
better in both halves of 2015-2026.

2026-10-13 (v6): stocks are capped at 80% of total assets (no new buys or adds
that would go above it; nothing is sold to get under it) and 60% of the idle
money goes to the TQQQ-rule sleeve normally (100% when breakout health is weak
and QQQ is above its 200-day line).  Next-open backtest 2015-01..2026-08:
55.0% a year, max DD -35.9% (v5: 53.4%, -36.3%), not worse in either half.
"""
RULE_ID = "swing-v6-max6-cap80-sleeve60"
PREVIOUS_RULE_IDS = ("swing-v5-max6-tqqq-sleeve",)  # same sizing; a running model continues under v6
MAX_NAMES = 6
INITIAL_WEIGHT = 1 / 6
INITIAL_LABEL = "1/6（約16.7%）"
STOCK_CAP = 0.80
STOCK_CAP_LABEL = "80%"
SLEEVE_NORMAL = 60
SLEEVE_WEAK = 100
SLEEVE_SHARES = (0, 50, SLEEVE_NORMAL, SLEEVE_WEAK)  # 50 = sessions published before v6
EFFECTIVE_DATE = "2026-10-13"

# 2026-10-18 additions (same rule id; orders from the 2026-10-19 session on):
# 守りモード: VIX/VIX3M >= 0.95 and QQQ under its 50-day line at the close -> no new
# 本命 and the stocks are cut to 40% of equity at the next open (pro rata; not while
# the TQQQ rule's 大底フル is on).  利益保護: a close 15% under the highest close since
# entry sells at the next open.  Local test 2015-01..2026-10 (v6 + 大底フル):
# 65.8% / max DD -44.9% / yearly DD mean -25.2%, median -23.5%  ->
# 66.2% / -39.4% / -24.2%, -22.2% (2015-20 47.2 -> 47.8%, 2021-26 87.6 -> 87.6%).
GUARD_DATE = "2026-10-19"
GUARD_TS = 0.95
GUARD_MA = 50
GUARD_STOCK = 0.40
TRAIL = 0.15
