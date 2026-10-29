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

2026-10-29 (same rule id, so the running model and its ledger carry on; publications from
the 2026-10-29 session on): normal sleeve share 60% -> 50% (40-60% gave the same CAGR,
lower shares a shallower DD), 守りモード retired (no robust effect), TQQQ rule simplified
(tqqq_rule.py).  Local next-open backtest 2015-01..2026-10-28: 65.1% / max DD -41.1% (10/18
settings) -> 68.1% / -37.0%; with every TQQQ-rule parameter and the trail jittered +-25%
(40 draws) the median went 63.1% / -41.4% -> 66.9% / -37.1%.
"""
RULE_ID = "swing-v6-max6-cap80-sleeve60"
PREVIOUS_RULE_IDS = ("swing-v5-max6-tqqq-sleeve",)  # same sizing; a running model continues under v6
MAX_NAMES = 6
INITIAL_WEIGHT = 1 / 6
INITIAL_LABEL = "1/6（約16.7%）"
STOCK_CAP = 0.80
STOCK_CAP_LABEL = "80%"
SLEEVE_NORMAL = 50   # 2026-10-29 (60 for the publications 2026-10-13 .. 2026-10-28, 50 before)
SLEEVE_V6 = 60
SLEEVE_50_FROM = "2026-10-29"  # first publication with the 50% normal share
SLEEVE_WEAK = 100
SLEEVE_SHARES = (0, SLEEVE_NORMAL, SLEEVE_V6, SLEEVE_WEAK)  # 60 = publications 2026-10-13 .. 2026-10-28
EFFECTIVE_DATE = "2026-10-13"

# 2026-10-18 additions (same rule id; orders from the 2026-10-19 session on):
# 守りモード: VIX/VIX3M >= 0.95 and QQQ under its 50-day line at the close -> no new
# 本命 and the stocks are cut to 40% of equity at the next open (pro rata; not while
# the TQQQ rule's 大底フル is on).  利益保護: a close 15% under the highest close since
# entry sells at the next open.  Local test 2015-01..2026-10 (v6 + 大底フル):
# 65.8% / max DD -44.9% / yearly DD mean -25.2%, median -23.5%  ->
# 66.2% / -39.4% / -24.2%, -22.2% (2015-20 47.2 -> 47.8%, 2021-26 87.6 -> 87.6%).
GUARD_DATE = "2026-10-19"
# 2026-10-29: 守りモード retired.  Across 36 neighbouring settings (VIX/VIX3M 0.90-1.05, 20-100
# day line, cut to 20-60%) it raised the CAGR in 42% and cut the max DD in 47% -> no robust
# effect (its one gain was April 2025).  A guard flag published on or after this session is
# ignored.  利益保護 stays (it cut the max DD in 5 of 6 neighbouring trail widths).
GUARD_OFF_FROM = "2026-10-29"
GUARD_TS = 0.95
GUARD_MA = 50
GUARD_STOCK = 0.40
TRAIL = 0.15


def normal_share(session: str | None) -> int:
    """The normal TQQQ-sleeve share published for ``session`` (v5 50% / v6 60% / 2026-10-29 50%)."""
    if session and str(session) < EFFECTIVE_DATE:
        return 50
    if session and str(session) < SLEEVE_50_FROM:
        return SLEEVE_V6
    return SLEEVE_NORMAL
