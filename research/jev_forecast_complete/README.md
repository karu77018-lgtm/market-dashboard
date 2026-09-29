# Corrected six-month Jev forecast study

## Problem -> cause -> correction -> impact
The pilot extrapolated standardized log returns with Student-t tail support then exponentiated them. That made the expected arithmetic return tail-sensitive and produced extreme expectations. This version does NOT delete BATL or any observed extreme: it uses native arithmetic percentage outcomes, recency/volatility-similarity weights, and finite-mean Gaussian/half-Gaussian support with physical downside boundaries. Expected return is a probability-weighted mean of explicit bin means. This changes the research estimator, not any sell rule. Old pilot results remain immutable evidence and are superseded for forecasting.

The fixed prior uses 401 quadrature midpoints and ten effective observations. This is a model, not an empirical guarantee. Calibration adjusts interval endpoints separately; do not claim that the uncalibrated mean/probability becomes calibrated merely because the band was adjusted.

## Frozen schedule and scope
All 26 forecast dates in the original March30-September28 calendar are processed, every five QQQ sessions, with twelve cases per date (six prior-RS63 leaders and six deterministic controls). Three real Jev runs each. Main forecasts use actual percent intervals, not opaque standardized-Z labels. Both technical-only and identical-data-plus-news variants run. Before each development origin, only fully matured previous development forecast errors are summarized as feedback. Feedback is frozen at July31 thereafter.

Development: March30-July31. Calibration: August3-August28. Held-out origins: August31-September28. Development fitting excludes targets completing after July31. Calibration excludes targets completing after August28. No test outcome adjusts prompts, blending, or interval coefficients. Terminal 80% and separate path marginal 90% intervals are evaluated. The last origins still receive forecasts even where future outcomes are not yet available; those labels stay null and are reported, not dropped invisibly.

On development data only, choose the Jev blending coefficient from {0,.25,.5,.75,1} using Brier plus 0.1 times volatility-normalized interval score. Zero is allowed: do not force a claim that Jev adds value. Numerical baseline, raw Jev, and frozen hybrid all remain visible. Interval expansion coefficients are fitted from calibration residuals only. This is approximate calibration with time/cross-sectional dependence, not distribution-free conditional coverage.

Current research lists: Top20 among 40 technical discovery candidates and Top20 among at most40 currently named candidates. This is a screened pool, NOT proof of finding the best20 of the entire market. Full evaluation records remain saved. A current options snapshot entitlement probe is isolated; no current option data is ever inserted into historical state, and this study does not claim a historical options comparison.

All matured five-day news-model direction/interval errors receive a batched, evidence-linked Jev association review after holdout outputs are frozen. This analysis never updates the held-out model. Unknown is an allowed answer. It is not causal identification.

## Cost, privacy, execution
Additional inference ceiling US$0.35, within the preceding US$0.40 public daily allocation after the pilot's US$0.04175766. No automatic topup. Maximum250 HTTP evaluations, three runs each, sequential requests. Actual Gateway cost is read, unknown cost stops further calls. Stored successful responses can be replayed without charging again when restoring a prior run's private call JSON files.

No holdings, orders, production schema, main, jev-prod, or dashboard are changed. The public pipeline only uses public candidate identities. Vendor material and raw requests/responses remain AES-GCM encrypted using the pre-existing archive key; numerical derived evidence is exported for independent arithmetic verification. The existing private Drive helper is reused.

Local tests:25 passed before this commit, including the pilot BATL volatility scale, finite means, no observed-value clipping, label-boundary purges, future data mutation invariance, and separate calibration of intervals rather than means.

Known remaining limitations: current-universe survivor bias; retrospective news versions and model-memory contamination; historical sector/option/MC57/F1-F3 not supplied. A completed study can legitimately conclude that the requested predictive quality was not achieved. Completion is not a promise of profitable forecasting.
