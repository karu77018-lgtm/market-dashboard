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
