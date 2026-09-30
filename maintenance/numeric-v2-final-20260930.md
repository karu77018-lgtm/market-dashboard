# Numeric v2 strong-stock forecast study — final 2026-09-30

## Purpose
After rejecting Jev as a direct 5-day price-direction predictor, test whether the numeric stage-3 layer can be improved enough to support 5-session direction ranking or terminal-return ranges.

## Frozen population and split
- 330 cases, 11 origins, 30 cases/origin.
- Eligibility: Price >= $5, DDV20 >= $10M, SMA50>SMA200, Close>SMA200, RS63 percentile >=85, RS189 percentile >=85.
- Per origin: 15 highest-RS189 leaders plus 15 deterministic hash controls.
- Development: 2026-07-10 through 2026-08-14 (180 cases).
- Calibration: 2026-08-21 and 2026-08-28 (60 cases).
- Evaluation replay: 2026-09-04, 2026-09-14, 2026-09-21 (90 cases).
- No Jev, news or options were used.
- Research GitHub Actions were not used.

The evaluation dates had been inspected in earlier research, so this is a locked retrospective replay, not a pristine unseen holdout.

## Direction-model search
Eight predeclared logistic variants were compared with expanding chronological development folds:
- all 59 features vs compact robust features;
- raw vs same-day cross-sectional stock normalization;
- stock-only vs market-only subsets;
- fixed L2 strengths.

The development CV selected **market_raw_l10**:
- CV Brier 0.2589
- CV accuracy 44.4%

Calibration then chose probability shrinkage alpha = 0.25.

### Final 90-case evaluation
| Model | Accuracy | Balanced accuracy | Brier | AUC |
|---|---:|---:|---:|---:|
| Constant base-rate | 47.8% | 50.0% | **0.2510** | 0.500 |
| Numeric v2 frozen | 52.2% | 50.0% | 0.2517 | **0.440** |
| Numeric v2 expanding refit | 52.2% | 50.0% | 0.2512 | 0.419 |

The 52.2% raw accuracy is misleading: the frozen model predicted every evaluation case above 50%, so balanced accuracy remained 50%.

Cross-sectional ranking was worse:
- Frozen top quintile mean 5D return: -0.56%
- Frozen bottom quintile mean 5D return: +8.25%
- Top-minus-bottom spread: **-8.80 percentage points**
- Mean within-origin Spearman: **-0.191**

The expanding-refit variant had a +3.00pt top-bottom spread, but mean within-origin Spearman was -0.023 and AUC 0.419. This is not stable ranking evidence.

## Range-model search
Four Huber-ridge variants predicted 5D terminal return normalized by vol20*sqrt(5). Development CV selected compact relative features, lambda=30.

### Final 90-case range evaluation
| Model | MAE | Median AE | 80% coverage | Mean width | Interval score |
|---|---:|---:|---:|---:|---:|
| Robust regression + residual interval | 9.37% | 7.48% | 60.0% | 16.99% | 41.56 |
| **Volatility-only empirical baseline** | **7.41%** | **4.70%** | **66.7%** | 20.45% | **40.08** |

The fitted range model was narrower but missed too often and had worse point error and interval score.

## Missing dimensions
Across the 330 cases:
- VIX level/change: 330 missing
- 10Y yield level/change: 330 missing
- NH/NL252: 300 missing
- distance to 252-day high: 302 missing

These were left missing rather than fabricated. The selected direction model did not gain validated usefulness despite the other available market features.

## Decision
1. **Reject numeric v2 as a direct 5-day direction/ranking signal in the current design.**
2. **Reject the fitted robust-return model for 5D terminal ranges.**
3. Keep the simple empirical volatility distribution as the range reference until a stronger source (for example validated options expected move) beats it.
4. Do not show numeric-v2 probabilities as investment probabilities and do not feed them into allocation or ranking.
5. Preserve the existing V38 rule/ranking engine rather than replacing it with a weak forecast overlay.

The practical architecture remains:
- Rule/eligibility/ranking: existing V38 rules.
- Market restrictions: separate.
- Range reference: empirical volatility distribution.
- Materials/evidence: separate Jev research track.
- No predictive overlay is promoted to production from this study.
