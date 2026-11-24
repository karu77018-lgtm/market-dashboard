# Public TradingView scripts, entry gates and the TQQQ sleeve (2026-11, local research)

Run locally only (never on GitHub Actions). Panel and 本命 history as `../record-context-2026-11`
(current listings, the dashboard's 3,828 chart tickers, Yahoo daily bars 2013-01..2026-11-23; delisted names
missing). Engine: the production `scripts/track_portfolio.step` (`tp_x.py` = a copy with a pluggable exit and
pilot size), `prod3.py` / `runall.py`. Continuous run 2015-01-02..2026-11-13; "10月再現" = a fresh portfolio
started 2026-10-05 to 2026-11-13. Base: 68.0% a year (2015-20 57.3%, 2021-26 80.2%), max DD -29.9%, 10月再現 -22.5%.

Every port was checked against the published script on TradingView (AFRM / QQQ, same values to the
rounding): GreenStar HUD, Stage 4 Trendline (break dates and line value), Squeeze Momentum [LazyBear],
CM_Williams_Vix_Fix, Up/Dn Volume Ratio (CarusoInsights), Chandelier Exit V2, UT Bot, Supertrend.

## Kept (on the site from 2026-11-24)

1. **UD ratio on 本命** (`en1.py`-`en3.py`): skip 本命 whose 50-day up/down volume ratio is >= 1.4.
   Per signal (rule exit): ratio < 1.3 better in 11 of 13 years; month-block bootstrap of the mean difference
   at 1.4: 5-95% +1.0..+4.7 points, > 0 in 99.6%. Engine: 75.1% (59.6 / 94.0), max DD -30.0%; 12 random drops
   of the same share (46%): 61.9-69.8% (2015-20 53.9-62.9, 2021-26 67.2-83.5). Cuts 1.3-1.6 (50 days) and
   1.4-1.6 (30 days) all better; 65 days mild. Weak point: the 2015-20 gain is inside the random range.
   Breakout health keeps the unfiltered signals (as tested).
2. **TQQQ sleeve rises at most 25% a session** (`sl5.py`, `sl6.py`; 大底フル exempt): 67.9% (57.1 / 80.4),
   10月再現 -19.4%. Sleeve alone by year: 2020 -8, 2025 -14 points (V-shaped), 2022 +3, 2023 +5, 2026 +4.
   50% a session 68.2%; 25% every 2 sessions 66.6%.
   Together: **75.0%** (59.2 / 94.3), max DD -30.0%, 10月再現 -19.4%.

## Not kept

- GreenStar HUD colours on 本命 (`g1.py`-`g3.py`): extension, %MaxATRx, VCPT, STS — skipping reds 63.8-68.8%,
  inside random drops; VCPT / STS lower. Red extension and loose VCPT did better per signal (opposite of the HUD).
- Stage 4 trendline break (`s4run.py`, `s4eval.py`): -25% trailing average -1.9 / +6.7% vs any stage-4 day
  +1.4 / +10.8% and the bagger breakout +2.5 / +9.2%; with RS80 better only in 2020 and 2025.
- Squeeze released within 5 days: per signal worse in both halves, engine 69.0% (random 61.0-69.2).
- Exits instead of / with the 21-EMA of lows (`ex_lines.py`, `ex_grid.py`): Chandelier, UT Bot, Supertrend
  56-63% replacing; Chandelier OR 21EMA 69.9% at 22x3 but 57% at 22x2.5 (cliff).
- Vix Fix on QQQ -> TQQQ 100% for 10-30 days: max DD -74% or worse. QQQ Supertrend cap on the sleeve: 32-50%.
- Faster new-entry gates on top of the 200-day line (`gates.py`, `rungate.py`, 22 settings): 50-day line 68.0%,
  21EMA 60.1%, distribution days 49-60%, VIX/VIX3M 66-68%, 本命 stop clusters 57-66%, recent 本命 P&L 57-66%,
  SPHB/SPLV 60-71% depending on window. None stable.
- Not raising the sleeve in weak markets (`sl2.py`, 9 definitions) 63-67%; later HY-cap release (`sl3.py`,
  15 settings) 61-67%; price confirmation before lifting the HY cap (`sl4.py`) 64-67%.
- Pilot (half or third) first buys / -5%, -6% stops when QQQ is under its 40-60-day line (`pil.py`): 66-69%.
- Zweig Breadth Thrust: too few events since 2014 to test.

The October 2026 loss: with no stock buys at all the same start reads -13.2% (sleeve), so faster stock gates
can only remove a few points of it; at the October entries QQQ was still above its 40-60-day lines.
