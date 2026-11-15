# What kind of decline is this? (2026-11, local research)

Run locally only (never on GitHub Actions). Sources: Yahoo (^NDX, ^GSPC, ^RUT, ^SOX, ^VIX, sector
SPDRs, rates, dollar, yen, gold, oil), FRED (Baa spread, yields, fed funds, unemployment, CPI,
NFCI, retail money funds, recessions), multpl (S&P 500 PE / CAPE / EPS), AAII sentiment survey,
FINRA margin statistics, CBOE put/call archives.

Question: when the Nasdaq-100 is 10% off its high, can the decline be broken into factors,
matched to a past year, and does any of that say what comes next?

Method
- `epi.py`: every first close 10% or more below the 252-session closing high since 1990
  (re-armed once back within 4%): 43 episodes including the running one.
- `epi4.py`, `epi6.py`: about 70 factors measured from the high to that day (shape, fear, what
  was sold, rates and credit, cycle, other assets, position, earnings, valuation, sentiment, flows).
- `epi5.py`: types, nearest episodes, and a two-halves screen of every factor against what followed.
- `hz.py`: the same screen at 10 / 20 / 60 / 120 / 250 / 500 sessions.
- `export_ref.py`: writes `scripts/decline_reference.py` (the card's reference table).

Findings
- Description works. Four types by driver: credit stress (credit spread +15bp and 10y -20bp),
  rising rates (10y +20bp), tech-only (S&P 500 ahead of the Nasdaq-100 by 5 points or more), broad.
- "The nearest year" does not forecast: nearest-neighbour predictions of the next 60 / 120
  sessions were worse than the plain average of all episodes (mean abs error 8.4 vs 7.1, 14.8 vs 12.6).
- The big divider is a recession within 12 months (known only afterwards): 6 episodes, median
  further decline -20.9% against -4.8% for the other 34.
- Of 284 factor x outcome tests, 19 agreed in both halves (about 17 expected by chance). The
  ones that stand out:
  - margin debt +20% a year or more at the high: 47% fell a further 10% or more, against 13%
    (both halves; Spearman -0.58 with the further decline, -0.54 / -0.62 with the 250 / 500
    session return; survives leaving out 1998-2000);
  - CAPE 30 or more: 42% against 10% (both halves);
  - retail money funds +15% a year or more: better 120 / 250 session returns in both halves.
- Earnings growth and the AAII survey showed no stable relation to what followed.
- Horizon matters: "heat" factors (CAPE, prior run-up, small caps leading, sectors holding
  above their 50-day lines) go with stronger 20-120 session rebounds and weaker 500 session
  returns. Without the 1998-2000 episodes the CAPE / run-up / small-cap reversals mostly
  disappear; margin debt and money funds remain.

Limits: about 40 episodes, overlapping long windows, many factors tried. Sector data starts in
1999, margin debt in 1997. Not available: fund flows (ICI), estimate revisions, NAAIM, daily
put/call after 2019.

Shown on the Market tab by `scripts/decline_anatomy.py` (display only; no order, rule or
ledger changes). The live card uses QQQ and ETFs from the refresh's own market inputs; the
reference table is index based.
