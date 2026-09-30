# Universal Expectation Gap v1 — 2026-09-30

Research shadow only. MC57/V38 production rules are unchanged.

## Design
- Core signal: deterministic only. Python owns Expectation Load, fundamental/price features, labels, and every backtest.
- Backtests: run in the assistant's local Python runtime, not GitHub Actions. GitHub stores code and frozen results only.
- Jev: optional research overlay only. It is not required for the core signal and is used only if an ablation test proves incremental out-of-sample value.
- Massive: raw evidence/data source for news, 8-K disclosure text, Form 4, short interest, short volume, and point-in-time inputs when entitled.
- No direct Jev stock-price forecast and no production dependency on Jev.

## Current coverage
- Dashboard universe: 3899
- Deterministic eligible universe: 2129
- Stratified Jev candidates: 60
- Jev evaluated: 0
- Candidates with recent news: 31
- Candidates with recent 8-K evidence: 20
- Jev errors: 41

## Research labels
- UNDERAPPRECIATED_POSITIVE: 0
- POSITIVE_WATCH: 0
- POSITIVE_BUT_PRICED: 0
- NEGATIVE_CHANGE: 0
- MIXED_OR_NEUTRAL: 0
- INSUFFICIENT_EVIDENCE: 19

## Important limits
- Expectation Load v1 is an equal-weight baseline used only for stratification; weights are not validated.
- The deprecated Massive financials endpoint is not a core dependency because it can enter HTTP 410 brownout.
- Short volume is contextual only and is never treated as short-interest direction by itself.
- Form 4 grants, RSUs, exercises, tax withholding, gifts, and 10b5-1 sales are separated from discretionary insider activity.
- The deterministic core must pass out-of-sample tests before any production use.
- Jev is added only in a separate A/B ablation after the deterministic core is frozen; if it does not improve held-out results, it is excluded.

## Next validation
Freeze historical point-in-time snapshots and run local Python backtests of forward 5D/10D/20D returns by Expectation Load bucket. Only after the deterministic baseline is validated should an optional English-Jev overlay be tested for incremental held-out lift.
