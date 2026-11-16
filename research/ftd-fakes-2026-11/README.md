# Follow-through days that fail quickly, and how to enter after one (2026-11, local research)

Run locally only. Yahoo daily OHLCV for QQQ (1999-) and SPY (1993-); VIX, VIX3M, IWM, RSP,
sector SPDRs, HYG / IEF / TLT, dollar index; FRED Baa and 10y; AAII; CBOE put/call archives;
FINRA margin debt; multpl CAPE; the local stock panel (2013-) for breadth and leaders.

Rules: `ftd.py` replays the site's `build_ftd` (build_dashboard_4) over the whole history:
correction = close below the 50-day line or 8% off the 252-session high, Day1 = first up close
after the low (an intraday undercut restarts the count), FTD = Day4 or later, +1.25% on higher
volume than the day before. Fake = a close below the FTD-day low within 25 sessions.

Results (239 FTDs: QQQ 129, SPY 110; QQQ and SPY often fire together, so not 239 independent cases)
- 56% are fakes (46% within 10 sessions). 60 sessions later: +7.1% median for the others, +1.6% for fakes.
- On the FTD day only the day count is consistent (both indices, both halves):
  Day4 70% fakes, 5 55%, 6-7 58%, 8-10 40%, 11-15 33%, 16+ 66%.
  About 55 other factors (gain, volume, close position, gap, depth, VIX, 200-day line, other
  index, credit, breadth, 90% days, sector breadth, leaders' breakouts, AAII, put/call, margin
  debt, CAPE, calendar) were not consistent. A score of factors chosen on 1993-2009 split fakes
  40/55/72% there and 55/51/62% in 2010-2026; the day count alone kept working (66% vs 35%).
- Two weaker factors held with cuts fixed on 1993-2009: long bonds down on the FTD day
  (62% vs 47%, 2010-: 62% vs 50%) and the dollar up over the prior 20 sessions (68% vs 43%,
  2010-: 61% vs 52%).
- After the FTD (FTDs not yet broken at that point):
  next day down 70% vs 40%; a distribution day within 3 sessions 62% vs 34%; no close above the
  FTD close within 3 sessions 73% vs 39%; down after 5 sessions 66% vs 29% (all four slices
  the same way). Day4-7 or 16+ with a down next day: 77% (2010-: 90%); Day8-15 with an up next
  day: 32%. Day 3: none of (next day down, distribution day) 31%, one 48%, both 74%.

Entry (`ftd_entry.py`, the index that gave the signal, at most 60 sessions, exit at the close
below the FTD-day low; per FTD, on full capital):
| style | mean | 1993-2009 | 2010- | worst |
| buy all on the FTD close, no stop | +2.1% | -0.5% | +4.7% | -40.3% |
| buy all on the FTD close, stop | +1.3% | +0.7% | +1.9% | -12.6% |
| half, rest if the next day is up | +0.9% | +0.2% | +1.6% | -14.2% |
| all if the next day is up | +0.6% | -0.3% | +1.4% | -15.8% |
| all on day 3 if no warning | +0.3% | -0.4% | +1.1% | -12.4% |
| half on Day4-7/16+, all otherwise, stop | +1.1% | +0.6% | +1.7% | -12.6% (2010-: -5.6%) |
Waiting for confirmation cuts losses but costs more of the gain. Sizing by day count keeps most
of the return with 31% average exposure against 46% (return per exposure 3.6 vs 2.8). At 3x
(TQQQ-like): stop +4.1% (worst -36%), no stop +6.1% (worst -84%).
Swing candidates (本命, 2015-, `ftd_stock.py`) in the 10 sessions after a QQQ FTD did not
differ consistently with the warnings (the sign flipped between 2015-20 and 2021-26), so the
warnings are not a filter for stock entries.

Shown under the FTD card by `scripts/ftd_check.py` (display only).
