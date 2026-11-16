# Is the live record inside the backtest's range? (2026-11, local research)

Run locally only (never on GitHub Actions). Current listings (the dashboard's 3,823 chart tickers),
Yahoo daily bars 2013-01..2026-11-13, no fees or taxes; delisted names are missing.

Question: the model record started 2026-10-05 and stood at -25.2% after 29 sessions (QQQ -10.1%).
Is that inside what the rule did in the past, and where did the loss come from?

Method
- `fetch.py` / `panel.py`: bars and the date x ticker panel.
- `sig.py`: 本命 history with the dashboard's own rule code (as `../adds-2026-10/fullrule_signals.py`).
- `tq.py`: the TQQQ-rule sleeve with `scripts/tqqq_rule.py` (HY OAS is only public from 2023-11; the
  Baa-10y spread, scaled, stands in before that; without the HY cap the conclusions are the same).
- `sim.py`: breakout health (latest reading -5.8% 不調 = the published value).
- `prod.py`: the production engine `scripts/track_portfolio.step` with the current rule on every
  session. Continuous run 2015-01..2026-10-28: 68.8% a year, max DD -29.9% (site: 73.2% / -30.0%).
- `fresh.py`: a NEW portfolio on every second session, 250 sessions each (1,482 starts).
- `an_fresh.py`, `an_attr.py`: the tables below.

Results (starts 2015-01-02..2026-08-28, 1,466 of them; later starts are the running record itself)
- After 29 sessions: median +2.7%, 5th percentile -8.1%, worst -24.5% (start 2019-04-25).
  The live -25.2% is below every past start. A fresh start on 2026-10-06 in this engine reads
  -22.1% after 28 sessions, so the engine reproduces the live loss: the rule behaved as tested and
  the start fell on its worst window so far.
- Starts at -10% or worse after 30 sessions (47 starts, 13 episodes): median -8.0% after 60
  sessions (32% back above the starting capital), -2.5% after 125 (49%), +71.5% after 250 (85%,
  worst -14.2%).
- Stops in the first 10 sessions: 4 or more in 1.5% of starts; the live record had 8.
- 30-session losses of 10% or more in the continuous run (17 episodes to 2026-08): stocks -8.1
  points, idle-money sleeve -6.6 points on average; the sleeve lost more in 8, nothing in 6.
  Live: stocks -13.3, sleeve -11.9.

Used by `scripts/backtest_summary.py` (START_ENVELOPE, START_BAD, LOSS_SPLIT) and shown on the
成績 tab by `scripts/track_record.py` (display only; no order, rule or ledger changes).
