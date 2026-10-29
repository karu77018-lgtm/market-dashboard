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

2026-10-30 (same rule id; publications from the 2026-10-30 session on): breakout health
decides the sleeve alone -> 好調 0% (idle money stays cash), 不調 100% whatever the QQQ
200-day line (大底フル still 100%).  37 health gauges were compared and the current one
(本命 10-day mean, 63 sessions) stayed best; what changed is how it is used.  Local test
2015-01..2026-10-28, medians over neighbouring gauge settings: 67.0% / max DD -37.0% ->
70.1% / -30.0% (2015-20 51.3 -> 56.5%, 2021-26 84.7 -> 85.2%); over TQQQ-rule jitter
66.3% / -38.0% -> 72.4% / -30.0%.  Better in 93% of all 3-year windows.  A 好調 sleeve
share from 50% down to 0% kept the CAGR flat and the max DD fell steadily.
"""
RULE_ID = "swing-v6-max6-cap80-sleeve60"
PREVIOUS_RULE_IDS = ("swing-v5-max6-tqqq-sleeve",)  # same sizing; a running model continues under v6
MAX_NAMES = 6
INITIAL_WEIGHT = 1 / 6
INITIAL_LABEL = "1/6（約16.7%）"
STOCK_CAP = 0.80
STOCK_CAP_LABEL = "80%"
SLEEVE_NORMAL = 0    # 2026-10-30: idle money stays cash while breakout health is 好調
SLEEVE_V6 = 60       # publications 2026-10-13 .. 2026-10-28
SLEEVE_V7 = 50       # publication 2026-10-29
SLEEVE_50_FROM = "2026-10-29"  # first publication with the 50% normal share
SLEEVE_0_FROM = "2026-10-30"   # first publication with 0% when 好調 and 100% when 不調 whatever the QQQ 200-day line
SLEEVE_WEAK = 100
SLEEVE_SHARES = (0, SLEEVE_V7, SLEEVE_V6, SLEEVE_WEAK)  # 50 = v5 and 2026-10-29, 60 = 2026-10-13 .. 2026-10-28
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
    if session and str(session) < SLEEVE_0_FROM:
        return SLEEVE_V7
    return SLEEVE_NORMAL


def momentum_rule_v8(session: str | None) -> bool:
    """True for publications that use the 2026-10-30 rule (好調 0% / 不調 100% regardless of the 200-day line)."""
    return not session or str(session) >= SLEEVE_0_FROM
