# Event family 60D hazard pilot — 2026-09-30

## Holdout summary
| Family | Event rate | ROC AUC history | ROC AUC history+vol | Avg precision history+vol | Top10% event rate | Lift |
|---|---:|---:|---:|---:|---:|---:|
| buyback | 3.94% | 0.539 | 0.605 | 5.57% | 5.16% | 1.31x |
| severe_downside | 0.56% | 0.540 | 0.627 | 5.68% | 1.41% | 2.50x |
| commercial_upside | 5.21% | 0.557 | 0.613 | 10.33% | 10.33% | 1.98x |
| regulatory_event | 1.36% | 0.546 | 0.656 | 3.71% | 2.82% | 2.07x |
| guidance_event | 4.37% | 0.761 | 0.775 | 40.04% | 24.88% | 5.70x |

## Read
- Guidance-event recurrence is the strongest hazard signal, but direction is mixed.
- Regulatory-event recurrence is moderately rankable but polarity is mandatory.
- Commercial-upside recurrence has modest ranking value.
- Severe-downside recurrence has useful lift but very low absolute frequency.
- Buyback recurrence is only a weak standalone ranking signal.
- This is occurrence probability only. Conditional impact is maintained separately in event-risk-decomposition-v2.
