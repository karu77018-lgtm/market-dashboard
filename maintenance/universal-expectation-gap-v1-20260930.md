# Universal Expectation Gap v1 — 2026-09-30

Research shadow only. MC57/V38 production rules are unchanged.

## Design
- Python: deterministic cross-sectional Expectation Load, batching, labels, and future backtests.
- Jev: English-only semantic interpretation of business change, novelty, persistence, and embedded expectations.
- Massive: news, 8-K disclosure text, Form 4, short interest, and short volume.
- No direct Jev stock-price forecast.

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
- Combined labels must be backtested out-of-sample before any production use.

## Next validation
Freeze historical point-in-time snapshots, compute forward 5D/10D/20D returns by label and Expectation Load bucket, then compare English Jev semantics against held-out labeled event cases.
