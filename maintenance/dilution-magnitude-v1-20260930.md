# Dilution magnitude v1 — 2026-09-30

This is the first magnitude-aware layer on top of the validated 60D dilution hazard.
Production MC57/V38 logic is unchanged.

## Coverage
- Impact-qualified dilution events: 112
- 8-K supporting text matched: 112
- Basic dilution % available: 13
- Financing / market cap available: 16
- Offer discount available: 10
- Secondary-only offerings identified: 4
- Historical Float Shock: intentionally unavailable until point-in-time float exists.

## Basic dilution × realized return

| Basic dilution | n | Gap median | 1D median | 5D median | 5D p10 | 20D median |
|---|---:|---:|---:|---:|---:|---:|
| <2% | 1 | 4.72% | 9.01% | 2.62% | 2.62% | — |
| 2-5% | 2 | 3.36% | 3.64% | -2.87% | -4.59% | 2.67% |
| 5-10% | 5 | 0.91% | 1.73% | 4.76% | -1.96% | 1.41% |
| 10-20% | 3 | -1.03% | -0.75% | -3.42% | -19.42% | 2.68% |
| 20%+ | 0 | — | — | — | — | — |

## Interpretation rules
- Do not treat dilution % as the price impact itself.
- Offer discount and financing/market-cap are separate explanatory variables.
- Selling-shareholder-only offerings are excluded from primary dilution bins.
- Net proceeds are tagged as such; when exact gross proceeds are unavailable, the amount basis is preserved.
- Missing text/terms stay missing; the parser does not fabricate a value.

## Next layer
Join cash runway / burn when a point-in-time financial source is entitled, then add Expected Move + pre-earnings Expectation Load.
