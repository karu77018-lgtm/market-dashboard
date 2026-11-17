# Market phase, industry strength and earnings around 本命 entries (2026-11, local research)

Run locally only. Local stock panel 2014-2026, the 本命 signals (`honmei.pkl`, 2,867 signals), the production
engine (`prod.py`). Industry and sector labels from Yahoo profiles (today's labels; 3,808 of 3,823 names),
past earnings dates from Yahoo for the 124 signal tickers. Halves 2014-19 / 2020-26.

1. Pausing new entries by the market phase (`fh.py`, 局面チェック replayed on the Nasdaq-100)
   | variant | 2015-26 | 2015-20 | 2021-26 |
   | current rule | 66.5% | 57.5% | 76.8% |
   | no new entries while the bounce has 0 signs | 68.1% | 61.6% | 75.6% |
   | none during the decline before +5% | 66.3% | 57.2% | 76.8% |
   | none during any 10%+ decline | 66.7% | 62.0% | 72.3% |
   (a year; max drawdown -29.9% in all). Not consistent between the halves: not kept.

2. Industry / sector strength (`fi.py`; median 63-day return of the industry's names, ranked across industries)
   Signals from the hottest industries and sectors did worse in both halves:
   industry top third PF 1.25 / 1.05 vs 1.86 / 2.59; sector top half PF 1.30 / 0.90 vs 2.06 / 3.91;
   worse in 10 of 13 years (industry) and 11 of 13 (sector).
   In the engine (`fj.py`, `fk.py`): skipping sector-top-half signals 78.1% a year (2015-20 62.6%, 2021-26 97.2%,
   max drawdown -27.0%) against the current 66.5%. Dropping the same share (66%) of signals at random, 8 seeds:
   63.2% on average (55-74%), 2015-20 61.1% (55-66%), 2021-26 66.7% (53-85%). The sector filter beats random
   drops clearly in 2021-26 but not in 2015-20 (fewer stock trades leave more cash in the TQQQ sleeve in both).
   Industry-top skips: 2015-20 better, 2021-26 worse. Promising but not adopted; a rule change is the owner's call.
   Caveat: labels are today's, not point-in-time.

3. Earnings (`fi.py`): signals within 20 sessions after earnings PF 2.82 / 2.37 vs 1.32 / 1.56, but better in only
   5 of 13 years; within 5 sessions before earnings PF 4.66 / 2.04 (n 62 / 113). Not kept.
