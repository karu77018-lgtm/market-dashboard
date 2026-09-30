# Dilution magnitude v1 — 2026-09-30

This is the first magnitude-aware layer on top of the validated 60D dilution hazard.
Production MC57/V38 logic is unchanged.

## Coverage
- Impact-qualified dilution events: 112
- 8-K supporting text matched: 112
- Basic dilution % available: 12
- Financing / market cap available: 17
- Offer discount available: 16
- Secondary-only offerings identified: 4
- Counterparty-issuer mismatches excluded: 1
- Timing-ambiguous rows excluded from curves: 15
- Basic curve eligible after quality guards: 6
- Historical Float Shock: intentionally unavailable until point-in-time float exists.

## Basic dilution × realized return

| Basic dilution | n | Gap median | 1D median | 5D median | 5D p10 | 20D median |
|---|---:|---:|---:|---:|---:|---:|
| <2% | 0 | — | — | — | — | — |
| 2-5% | 1 | 2.83% | 0.26% | -0.72% | -0.72% | — |
| 5-10% | 3 | -1.86% | -1.34% | 1.39% | -3.07% | 1.37% |
| 10-20% | 2 | -0.30% | -3.72% | -13.42% | -21.43% | -3.59% |
| 20%+ | 0 | — | — | — | — | — |

## Interpretation rules
- Do not treat dilution % as the price impact itself.
- Offer discount and financing/market-cap are separate explanatory variables.
- Selling-shareholder-only offerings are excluded from primary dilution bins.
- Counterparty issuances (the filer is the buyer, not issuer) are excluded.
- Rows whose transaction date predates filing are withheld from impact curves until public/tradable time is resolved.
- Net proceeds are tagged as such; when exact gross proceeds are unavailable, the amount basis is preserved.
- Missing text/terms stay missing; the parser does not fabricate a value.

## Next layer
Join cash runway / burn when a point-in-time financial source is entitled, then add Expected Move + pre-earnings Expectation Load.
