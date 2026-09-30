# Dilution hazard v1 — 2026-09-30

## Target
Probability of at least one public offering / private placement / PIPE / warrant-conversion 8-K disclosure in the next 60 calendar days.

## Population
- 12,393 snapshot rows across 6 historical snapshots.
- >=100 prior sessions, price >= $5, DDV20 >= $10M.
- Development: 8,126 rows.
- Calibration: 2,137 rows.
- Holdout: 2,130 rows; 89 positives (4.18%).

## Main result
Recent dilution history is predictive out of sample.

| Prior 90D dilution count | Train n | Train 60D event rate |
|---|---:|---:|
| 0 | 9556 | 3.48% |
| 1 | 544 | 14.52% |
| 2+ | 163 | 25.15% |

### Holdout
| Model | Brier ↓ | ROC AUC | Avg precision | Top-decile event rate | Lift |
|---|---:|---:|---:|---:|---:|
| Constant | 0.04004 | 0.500 | 3.96% | 3.76% | 0.90x |
| History | 0.03908 | 0.584 | 9.27% | 10.33% | 2.47x |
| History + vol band | 0.03914 | **0.655** | **9.80%** | **10.80%** | **2.58x** |

## Selected empirical rates (history × vol)
- 0|low: n=3165, raw 2.43%, shrunk 2.45%
- 0|high: n=3098, raw 6.00%, shrunk 5.99%
- 0|mid: n=3293, raw 2.13%, shrunk 2.14%
- 1|high: n=282, raw 14.18%, shrunk 13.39%
- 2plus|mid: n=38, raw 7.89%, shrunk 6.51%
- 2plus|high: n=95, raw 32.63%, shrunk 26.75%
- 1|mid: n=125, raw 9.60%, shrunk 8.74%
- 1|low: n=137, raw 19.71%, shrunk 17.35%
- 2plus|low: n=30, raw 23.33%, shrunk 14.73%

## Next layer
Add point-in-time financing need/capacity:
- cash runway / cash burn;
- free cash flow;
- shelf / ATM / 424B5 / S-3 readiness;
- shares outstanding / float and warrant/convertible overhang.

Conditional price impact is supplied separately by event-impact-library-v1.
