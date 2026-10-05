# Same-amount adds: how much is too much? (2026-10, local research)

Run locally only (never on GitHub Actions). Data and caveats as in `../setups-2026-10/`
(current listings, Yahoo daily bars). `fullrule_signals.py` rebuilds the 本命 history with the
dashboard's own rule code (`scripts/swing_screener.py`, `scripts/breakout_health.py`);
`fullrule_sim.py` runs the 6-slot portfolio (1/6 first buy, same-amount adds at +10/+20%,
-8% stop, close below the 21-EMA of lows, idle money 50% QQQ / 100% when breakout health is
weak and QQQ is above its 200-day line).

Replication check (2015-01 to 2026-08): stocks only 30.9% a year, max DD -30.2%; with the QQQ
switch 40.7%, -31.6% (Rules tab: 32.1% / -31.2% and 42.4% / -30.3%).

| adds | CAGR | max DD | stocks only | worst single-name loss | 2015-20 | 2021-26 |
|---|---|---|---|---|---|---|
| none | 29.2% | -25.9% | 19.9% | -2.8% | 24.0% | 35.3% |
| same x2, cap 40% (current) | **40.7%** | -31.6% | 30.9% | -4.5% | 24.1% | 60.7% |
| same x2, cap 33% | 38.2% | -31.6% | 29.3% | -4.5% | 25.3% | 52.5% |
| same x2, cap 30% | 36.6% | -30.9% | 27.0% | -4.1% | 24.6% | 49.4% |
| same x2, cap 25% | 34.0% | -28.7% | 24.7% | -3.0% | 24.8% | 44.1% |
| same x2, cap 20% | 30.3% | -26.7% | 21.0% | -2.8% | 24.2% | 37.6% |
| half x2, cap 40% | 36.9% | -31.1% | 27.3% | -2.9% | 25.0% | 50.2% |
| same x2, stop to average cost after the 2nd add | 35.5% | -31.6% | 26.1% | -4.5% | 23.6% | 49.8% |

Worst single-name loss is measured against equity at entry. The current rule has the best
CAGR / max DD (1.29). The adds earn their keep in 2021-26 (strong leaders); in 2015-20 every
scheme is about 24%. `addsim.py` is the earlier proxy (selection only, no form/SAR conditions)
whose cap-25% result did not hold on the real rule.
