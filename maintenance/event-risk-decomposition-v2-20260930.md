# Event risk decomposition v2 — 2026-09-30

This combines **occurrence probability** and **conditional price impact**. It does not collapse all risks into one opaque score.

## 5D event-EV formula
For daily volatility sigma (in percentage points) and 60D event probability p:

- downside EV = p × mean negative-part z × sigma × sqrt(5)
- upside EV = p × mean positive-part z × sigma × sqrt(5)
- net EV = p × mean z × sigma × sqrt(5)

## Occurrence hazard — holdout

| Family | Holdout event rate | ROC AUC (history+vol) | Avg Precision | Top10% event rate | Lift |
|---|---:|---:|---:|---:|---:|
| buyback | 3.94% | 0.605 | 5.57% | 5.16% | 1.31x |
| severe_downside | 0.56% | 0.627 | 5.68% | 1.41% | 2.50x |
| commercial_upside | 5.21% | 0.613 | 10.33% | 10.33% | 1.98x |
| regulatory_event | 1.36% | 0.656 | 3.71% | 2.82% | 2.07x |
| guidance_event | 4.37% | 0.775 | 40.04% | 24.88% | 5.70x |

Dilution uses the stronger shelf-readiness v2 model separately: AUC 0.682, top-decile event rate 13.15%, lift 3.15x.

## Conditional 5D impact components

| Family | n | Mean z | Downside component z | Upside component z | P(negative) |
|---|---:|---:|---:|---:|---:|
| severe_downside | 18 | -0.204 | -0.527 | 0.322 | 66.7% |
| commercial_upside | 137 | 0.294 | -0.422 | 0.716 | 45.3% |
| buyback | 95 | 0.482 | -0.307 | 0.789 | 38.9% |
| regulatory_event | 35 | 0.275 | -0.538 | 0.812 | 51.4% |
| guidance_event | 111 | -0.333 | -0.808 | 0.475 | 60.4% |
| dilution | 115 | -0.313 | -0.628 | +0.314 | 64.3% |

## Interpretation
- **Dilution** is the strongest production-candidate family because both occurrence and impact have usable evidence.
- **Guidance event** occurrence is highly rankable (AUC ~0.775) but direction is mixed. Jev must label raise/reaffirm/cut/withdraw before applying impact.
- **Regulatory event** occurrence is moderately rankable (AUC ~0.656) but outcome polarity is mandatory.
- **Commercial upside** occurrence is only moderate; the event family still contains weak/optical partnerships, so economics/size must be extracted before use.
- **Severe downside** is rare. It has some hazard lift but thin conditional-impact sample.
- **Buyback** has clean positive conditional skew but weak occurrence discrimination.

## Semantic layer
Jev is used only to extract:
- event type;
- polarity;
- stage;
- novelty;
- size/economics relative to market cap/revenue;
- whether already realized/priced.

Python owns occurrence probability, volatility scaling, EV math, and aggregation.
