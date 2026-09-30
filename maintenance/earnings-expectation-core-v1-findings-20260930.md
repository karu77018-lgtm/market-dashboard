# Earnings Expectation Load Core v1 — findings

Date: 2026-09-30  
Status: **PROMISING / NOT ADOPTED**

## Coverage

- Massive `quarterly_earnings` disclosures: 744
- Event-study eligible: 196
- Core complete: 194
- Usable event dates: 2026-07-07 to 2026-09-16
- Options Expected Move / analyst revisions / estimate revisions: not included

## What actually carried the signal

Pearson correlation with 5-session post-event return:

| Factor | corr(5D) |
|---|---:|
| 20D stock run-up | -0.240 |
| 20D excess return vs QQQ | -0.199 |
| Equal-weight Core | -0.141 |
| RS63 percentile change | -0.037 |
| Distance to 63D high | -0.034 |

The first pilot therefore does **not** justify assuming that all four components
deserve equal weight. The run-up / excess-return block is doing most of the
directional work.

## All-sample Core buckets

| Core | n | 5D median | 5D mean | z5 median |
|---|---:|---:|---:|---:|
| 0-20 | 28 | -0.12% | +0.95% | +0.03σ |
| 20-40 | 46 | +0.34% | -0.08% | +0.08σ |
| 40-60 | 39 | -0.48% | -0.95% | -0.16σ |
| 60-80 | 54 | -2.15% | -3.59% | -0.65σ |
| 80-100 | 27 | -1.57% | -1.48% | -0.31σ |

The relationship is not monotonic at the very top. Therefore the current score is
a research feature, not a production sell-the-news rule.

## Jul-Aug calibration -> September holdout

To avoid using September's distribution to score September, component empirical
percentiles were fitted on Jul-Aug only and frozen for the September holdout.

| OOS Core | n | 5D median | 5D mean | P(5D<0) | z5 median |
|---|---:|---:|---:|---:|---:|
| <60 | 44 | -2.60% | -3.22% | 61.4% | -0.58σ |
| >=60 | 12 | -11.10% | -12.51% | 83.3% | -1.65σ |

This is a large separation and it survives volatility normalization. It is still
only one partial month with n=12 in the high-load bucket, so it is **not adopted**.

## Decision

Keep:
- 20D run-up;
- 20D excess vs QQQ;
- RS-rank change and high proximity as research features;
- fixed Core vs Enhanced separation;
- no missing-input reweighting.

Do not do yet:
- production hard gate;
- production score weighting;
- price-direction prediction by Jev;
- treating 60 as a validated universal cutoff.

Next evidence required:
1. longer point-in-time earnings history;
2. separate validation of run-up / excess factors;
3. ATM straddle Expected Move if historical option pricing is entitled;
4. analyst / estimate revisions only after data entitlement exists.
