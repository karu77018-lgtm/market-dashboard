# Earnings Expectation Load — local validation 2026-10-01

Status: **LOCAL REPRODUCED / NOT ADOPTED**

Computation source:
- Event rows: frozen research dataset `earnings-expectation-load-core-v1.json`
- Computation: assistant local Python runtime, not GitHub Actions
- Jev: not used
- Calibration: July-August 2026 only
- Holdout: September 2026 only
- Holdout observations: 56

## Frozen-calibration OOS result

| Score | n | 5D median | 5D mean | P(5D<0) | z5 median |
|---|---:|---:|---:|---:|---:|
| Core <60 | 44 | -2.60% | -3.22% | 61.4% | -0.58σ |
| Core >=60 | 12 | -11.10% | -12.51% | 83.3% | -1.65σ |

The local calculation exactly reproduces the previously stored OOS split.

## Simpler baseline check

The four-factor Core is not yet justified as the minimum sufficient model.

| Frozen Jul-Aug score, Sep holdout | High-load n | High-load 5D median | High-load 5D mean | P(5D<0) |
|---|---:|---:|---:|---:|
| Four-factor Core >=60 | 12 | -11.10% | -12.51% | 83.3% |
| 20D run-up + QQQ excess >=60 | 12 | -11.41% | -13.25% | 91.7% |
| 20D stock run-up >=60 | 14 | -8.95% | -10.01% | 78.6% |
| 20D QQQ excess >=60 | 12 | -11.41% | -13.25% | 91.7% |
| RS63-change >=60 | 13 | -7.40% | -9.52% | 76.9% |

Distance-to-63D-high did not improve separation in this holdout.

## Uncertainty check

For the Core >=60 versus <60 split, the observed mean-return difference is -9.29 percentage points.
A fixed-seed 20,000-resample bootstrap gives an approximate 95% interval of -16.47 to -2.25 points for the mean difference.
The median-difference interval still crosses zero, reflecting the small high-load sample (n=12).

## Decision

1. Jev is not required for the core signal.
2. Backtests will be run locally; GitHub stores code and frozen outputs only.
3. Start with the simplest deterministic baseline: 20D run-up / 20D excess versus QQQ.
4. The four-factor composite must beat the simpler baseline before it is kept.
5. Jev may only return as an optional semantic overlay after the deterministic model is frozen, and only if it improves held-out results.
6. No production MC57/V38 rule change yet.
