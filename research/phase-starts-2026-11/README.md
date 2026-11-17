# Starts of declines and rallies, and what kind of rally (2026-11, local research)

Run locally only. Nasdaq-100 (1990-2026) with the S&P 500 as a check; Yahoo indices, sector SPDRs,
VIX, rates, dollar, FRED Baa; CAPE, FINRA margin debt, money funds, AAII (as in the decline study).
Halves: 1990-2007 / 2008-2026.

Definitions (`ud.py`)
- Down start: first close 5% below the 252-session closing high (re-armed back within 2%).
  Outcome: reached -10% before getting back within 2%.
- Up start: during a decline of 10% or more, the first close 5% above the lowest close so far
  (a new low re-arms it). Outcome "real bottom": back within 2% of the high before closing below that low.
- Rally (`ud4.py`): the same at +10%.

Findings
- Up start (Nasdaq-100, 105 decided): 42% real bottoms. Three signs split it by 10+ points in both halves:
  above the 50-day line (79% / 83% vs 29% / 37%), took 4+ sessions (72% / 60% vs 26% / 31%),
  no day up 3.7%+ (69% / 48% vs 17% / 36%). Signs present: 0 -> 20% (8% / 35%), 1-2 -> 51% (62% / 40%),
  3 -> 91% (86% / 100%). Violent bounces are usually bear-market rallies. The S&P 500's own starts
  are fewer (45) and the score is not clear there.
- Rally at +10% (53 decided): 62% real. Same three signs (11+ sessions, no day up 4%+):
  3 -> 95% (100% / 88%), 0 -> 30% (15% / 57%). FTD during the rise 65% vs 29% (2000-).
  Types (credit relief, falling rates, tech-led, small/cyclical-led, broad) describe the rally;
  their later results flip between halves, so they are not used to predict.
- Down start: the Nasdaq-100 could not be split by anything (42% reach -10%). S&P 500 (65 decided):
  VIX 23 or more on the -5% day -> 44% reached -10% (43% / 45%), below 23 -> 6% (5% / 10%).
- CAPE, margin debt, money funds, AAII: nothing consistent at the starts.

Limits: about 50-100 events per question, overlapping, many factors tried. The card uses QQQ / SPY
from the refresh's inputs; the study used the indices.

Shown on the Market tab by `scripts/phase_check.py` (display only).

Second round (`ud5.py`, `fg.py`, 2026-11-17)
- New factors, each split at its own median in two halves of the events it covers. Held on the Nasdaq-100,
  the S&P 500 and the +10% rallies alike: financial conditions (Chicago Fed NFCI, change over the 4 weeks before,
  as known a week earlier) not tightening. +5% bounces: 68% real (17/25; 67% / 71% by half) vs 34% (27/80);
  inside the 1-2 sign band 67% vs 42%. +10%: 94% vs 46%. Shown as a fourth sign; the big number uses the
  sign band x NFCI cell when it has 10+ events.
- Credit-type declines (decline card's type) bounce less: 9% / 35% real vs 63% / 50% for the other types.
- Not kept: net liquidity (Fed assets - TGA - reverse repo, 13 weeks), jobless claims vs their 26-week low,
  USD/JPY 20 days, CFTC leveraged-fund and asset-manager positioning (z, 2010-), option-expiry week,
  presidential cycle, Sep-Oct, NFCI level (Nasdaq-100 down starts held, S&P 500 not by 10 points).
  Breadth of the local panel (share above the 50/200-day line, new highs - lows, 10-day thrust) held for
  Nasdaq-100 rally starts but has only 2013- (~30 events) and flips on the S&P 500 down starts: not used.
- Combinations: an FTD inside the sign bands added nothing (lower, if anything); F3 recovery at rally starts:
  5 events. Production engine with the TQQQ sleeve set by the signs: 3-4 signs -> 100% no change
  (66.5% -> 66.6% a year), 0-1 signs -> 0% much worse (66.5% -> 50.1%): the signs stay display only.

Third round (2026-11-17): TradingView S5FI (S&P 500 share above the 50-day line, weekly closes from 2006-12-29 in
`s5fi_weekly_close_2006-12-29.txt`). Nasdaq-100 rally starts: level above 25% 55% / 50% vs 36% / 33%; 4-week change
above -17 points 58% / 54% vs 31% / 31% (halves split 2018-12); inside the 1-2 sign band 53% (17) vs 11% (9).
S&P 500 rally starts: no consistent split. S&P 500 decline starts: higher breadth and a smaller 4-week drop went
with more -10% outcomes (n 5-11 per cell). About 50 events since 2007: not kept, worth rechecking later.
