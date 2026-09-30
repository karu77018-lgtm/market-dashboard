# Dilution hazard v2 — shelf readiness — 2026-09-30

## Holdout
2,130 rows, 89 dilution events in the following 60 calendar days.

| Model | Brier ↓ | ROC AUC | Avg Precision | Top-decile event rate | Lift |
|---|---:|---:|---:|---:|---:|
| constant | 0.04004 | 0.500 | 3.96% | 3.76% | 0.90x |
| history | 0.03908 | 0.584 | 9.27% | 10.33% | 2.47x |
| history_vol | 0.03914 | 0.655 | 9.80% | 10.80% | 2.58x |
| history_shelf | 0.03857 | 0.654 | 12.43% | 10.33% | 2.47x |
| history_shelf_424 | 0.03860 | 0.663 | 13.66% | 11.74% | 2.81x |
| history_shelf_vol | 0.03867 | 0.682 | 11.94% | 13.15% | 3.15x |

## Simple unconditional financing-readiness rates
- No shelf filing in prior 365D: 3.71% 60D dilution rate (n=7935)
- S-3/S-3ASR in prior 365D: 6.83% (n=2328)
- No 424B5 in prior 90D: 3.86% (n=9373)
- >=1 424B5 in prior 90D: 10.22% (n=890)

## Interpretation
- Shelf readiness is additive information beyond recent dilution history.
- The best probability calibration in this holdout is history+shelf.
- The best ROC ranking / top-decile concentration is history+shelf+vol.
- The best average precision is history+shelf+424B5.
- Do not collapse these post-holdout observations into a new production model without another matured validation window.
- 424B5 is semantically noisy because it includes debt as well as equity capital markets activity; future v3 should classify the filing type/content.

Financial-statement cash runway was not available on the current Massive entitlement.
