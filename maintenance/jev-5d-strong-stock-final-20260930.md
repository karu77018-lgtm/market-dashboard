# Jev 5D strong-stock validation — final 2026-09-30

## Scope
- 140 frozen cases: development 80, untouched scoring cohort 60.
- 5-session direction only.
- Eligibility: Price >= $5, DDV20 >= $10M, SMA50>SMA200, Close>SMA200, RS63 percentile >=85, RS189 percentile >=85.
- Each origin: 10 RS189 leaders + 10 deterministic hash controls.
- Jev input: 59 numeric features only, no news. Each case was evaluated independently 3 times to remove the earlier batch-collapse confound.
- Research GitHub Actions: not used. Production: not changed.

## Development 80
| Model | Accuracy | Brier |
|---|---:|---:|
| Constant | 53.75% | 0.2486 |
| Numeric L2 | 70.00% | 0.1843 |
| Jev single-case | 40.00% | 0.3495 |

Development-only selection chose Jev shrinkage = 0, hybrid Jev weight = 0, and challenger override rate = 0.

Pre-specified groups did not rescue Jev:
- Leader 40: 40.0%, Brier 0.3490.
- Hash-control 40: 40.0%, Brier 0.3500.
- Jev accuracy by origin: 55%, 30%, 25%, 50%.

## Holdout 60
| Model | Accuracy | Brier |
|---|---:|---:|
| Constant | 50.00% | 0.2514 |
| Numeric L2 | 46.67% | 0.3735 |
| Jev single-case | 50.00% | 0.2811 |

Jev vs numeric disagreements: Jev-only correct 15, numeric-only correct 13; exact McNemar p=0.851.

The pre-specified leader subgroup showed 60% Jev accuracy in holdout versus 46.7% numeric, but this did not reproduce in development (40% Jev in development leaders), so it is not adopted.

Three-run stability had some diagnostic value but not enough to create an edge:
- Lower-half run std: 56.7% accuracy, Brier 0.2677.
- Upper-half run std: 43.3% accuracy, Brier 0.2944.
These cuts were inspected after the fact and are not a production rule.

## Decision
**Reject Jev as a direct 5-day price-direction predictor in the current design.**

Do not use it for ranking, allocation, or a displayed calibrated probability. Do not revive the earlier 20-case RS-gate result; the 140-case test failed to confirm it.

Jev may still be useful in a separate material/evidence-reading layer. That is a different task and must not be mixed with the rejected direct price-direction forecast.
