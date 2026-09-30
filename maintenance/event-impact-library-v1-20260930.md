# Event impact library v1 — 2026-09-30

## Scope
- 9,407 SEC 8-K event records from Massive.
- 771 matched seasoned/liquid equity events after filters.
- Filters: >=200 prior sessions, prior close >= $5, DDV20 >= $10M, 30-calendar-day same-ticker/category cooldown.
- Reaction baseline: last close strictly before filing date.
- Horizon: close of the 5th / 20th regular session strictly after filing date.
- Vol-normalized impact = return / (pre-event 20D daily volatility × sqrt(horizon)).
- This library estimates **conditional impact only**, not event occurrence probability.

## Dilution composite
Pure dilution = public offering + private placement + PIPE + warrant/conversion. Underwriting is excluded because it mixes debt and equity underwriting.

- n5: 115; n20: 81
- 5D median: -2.48%
- 5D mean: -2.18%
- 5D P(negative): 64.3%
- 5D P(<= -10%): 20.9%
- 5D p10: -13.31%
- 20D median: -2.45%
- 20D P(negative): 61.7%
- normalized 5D median: -0.399
- normalized 5D p10: -1.567

## Selected categories
| Event | n5 | 5D median | 5D p10 | P(5D<0) | 20D median |
|---|---:|---:|---:|---:|---:|
| Public offering | 68 | -1.86% | -11.20% | 60.3% | -0.94% |
| Private placement | 27 | -1.64% | -12.94% | 66.7% | -12.04% |
| Warrant / conversion | 20 | -3.47% | -16.42% | 75.0% | -6.14% |
| Regulatory investigation | 12 | -3.44% | -15.29% | 75.0% | 0.17% |
| Buyback | 95 | 1.69% | -7.45% | 38.9% | 0.63% |
| Guidance update (mixed) | 110 | -2.72% | -11.68% | 60.0% | -1.00% |
| Regulatory decision (mixed) | 35 | -1.02% | -11.46% | 51.4% | -3.65% |
| Merger agreement (mixed) | 89 | -0.34% | -9.20% | 52.8% | 0.43% |

## Live scaling
For category e and current daily vol sigma:
- median conditional impact ≈ median(z5_e) × sigma × sqrt(5)
- adverse conditional impact ≈ p10(z5_e) × sigma × sqrt(5)
- event EV requires a separate occurrence probability.

## Semantic split required
These categories are not usable without reading the event direction:
- guidance: raise / reaffirm / cut / withdraw
- regulatory decision: approval / rejection / CRL / designation
- M&A: target / acquirer / financing role
- litigation: win / loss / filing / settlement
- partnership / contract: economics, size, and novelty

Jev should extract those facts. Python should own occurrence probability, conditional-impact scaling, and aggregation.
