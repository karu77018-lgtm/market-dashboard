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

Entry when the FTD close cannot be traded (`ftd_entry2.py`): orders go in after the close, so
entries are at a later open; exits at the next open after a close below the FTD-day low, or a
stop order at the FTD-day low.
| style (close-based exit) | mean | 1993-2009 | 2010- | worst |
| FTD close (reference) | +1.2% | +0.8% | +1.7% | -11.0% |
| next open, no stop | +2.1% | -0.4% | +4.6% | -39.3% |
| next open, all | +1.2% | +0.8% | +1.6% | -11.6% |
| next open, half on Day4-7/16+ | +1.1% | +0.7% | +1.5% | -11.6% |
| half next open, rest the open after if the next day is up | +0.9% | +0.3% | +1.4% | -12.6% |
| all the open after if the next day is up | +0.6% | -0.2% | +1.3% | -13.6% |
| day-4 open if no warning at day 3 | +0.3% | -0.4% | +1.0% | -14.1% |
The next open is on average where the FTD closed (gap mean +0.04%), so the ranking is unchanged
(QQQ and SPY alike). Stop order at the FTD-day low, next open, all: +1.1%, worst 2010- -4.3%.
3x: next open with exit +3.8% (worst -34%), no exit +5.9% (worst -83%).

Shown under the FTD card by `scripts/ftd_check.py` (display only).

Choosing entries with the fakes' factors (`ftd_entry3.py`; next open, close-based exit). Headwinds
known by the next open: Day4-7/16+, long bonds -0.07% or worse on the FTD day, dollar index +0.45% or
more over the prior 20 sessions (both cuts fixed on 1993-2009).
| headwinds | FTDs | mean | 1993-2009 | 2010- |
| 0 | 17 | +6.9% | +4.2% | +9.8% |
| 1 | 88 | +2.4% | +1.5% | +3.7% |
| 2 | 101 | -0.3% | 0.0% | -0.5% |
| 3 | 33 | -0.5% | -1.2% | +0.1% |
Skipping 2+ headwinds: +1.38% per FTD (all: +1.20%), 1993-2009 +0.96% (+0.82%), 2010- +1.81% (+1.60%),
worst 2010- -5.0% (-9.7%), exposure 26% (46%); 3x +4.4% (+3.8%), worst 2010- -16% (-28%).
0-1 beat 2-3 in 7 of 8 five-year blocks. Half size instead of skipping: +1.29%. Sizing in steps by
the count: +1.05%. Exits on post-entry warnings added almost nothing (+1.22%). About ten styles
were tried, so the best one is somewhat flattered; QQQ and SPY FTDs often coincide. Skipped big
winners: QQQ 2012-01-03 (+19%), QQQ 2002-10-11 (+18%), SPY 2009-03-12 (+24%; QQQ 2009-03-18 was taken).
