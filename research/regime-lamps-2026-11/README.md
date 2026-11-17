# How to use F1-F3 (2026-11, local research)

Run locally only. Local stock panel 2013-2026 (about 3,800 names; not the site's exact universe),
F1-F3 with the card's definitions (`scripts/regime_history.series`), QQQ and SPY. Halves 2013-19 / 2020-26.

Kept (same direction in both halves, QQQ and SPY, neighbouring cuts):
- QQQ under its 200-day line and F3 >= 60%: a 10% drop within 60 sessions 22% / 30% of days (baseline 13% / 20%),
  but +9.1% / +11.3% after 60 sessions (baseline +3.8% / +5.0%). A volatile bottom zone, not a sell signal.
  Above the 200-day line F3 >= 60% is about ordinary.
- F3 back to <= 35% within 20 sessions of >= 60%: +5.3% / +6.7% after 60 sessions, 10% drops 11% / 16%;
  本命 win rate 39% vs 34% and 38% vs 29%. Raising the TQQQ sleeve to 100% for 20 sessions after it
  did not help the production engine (66.5% -> 65.0% a year).
- All three calm (F1 < 20%, F2 < 25%, F3 < 40%): QQQ +0.1% / +0.3% after 60 sessions, 本命 PF 0.39 / 0.60
  (others 1.63 / 1.77). 130 days in 36 months. Pausing new entries and the sleeve on those days in the
  production engine: 66.5% -> 67.9% a year, same max drawdown.

Not kept: F1 and F2 levels (index and 本命 results flip between the halves; 本命 PF with F2 in warning
0.91 vs 3.39), F1 high near the index high, fast rises of any lamp, F2 low (index weaker in both halves
but 本命 flips).

Shown in the レジーム警戒灯 card by `scripts/regime_history.py` (display only).
