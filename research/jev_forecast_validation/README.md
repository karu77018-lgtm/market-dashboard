# Jev return/range validation: development pilot

## Scope and pre-change impact
Problem: news is archived, but no forward direction/range forecasts have been executed.
Cause: the existing production questions classify textual events, not forward outcomes.
Change: add a bounded research runner, frozen protocol and offline tests on this branch.
Impact: no production API/schema/site/trading changes; no holdings access; no new Massive
calls. Use the existing authenticated /api/jev with custom questions and persist=false.
Raw requests, responses and outcomes are preserved in authenticated encrypted research
archives instead of pretending they were inserted into the production question registry.

## Freeze before any evaluation
Development 2026-03-30..2026-07-31; calibration 2026-08-03..2026-08-28;
holdout 2026-08-31..2026-09-28. Every fifth observed QQQ session is a forecast origin.
This first run evaluates only the FIRST THREE development origins, eight stocks each.
Four trailing-RS63 leaders plus four reproducible hash controls are selected using only
pre-origin price/liquidity data. This is a pipeline-development sample, not a final Top20
ranking or historical universe reconstruction. Current-universe survivorship remains.

Forecast horizons 5/10 sessions, next-session open to end-session close; path high/low
are separate targets. Historical labels used for the benchmark end on/before origin.
Monthly phases are never shuffled. Calibration and holdout are NOT scored in this run.
Raw outcome records are held outside model input. Before a new origin, one fully matured
previous five-session error can be classified. These diagnoses are recorded, NOT fed as
proven causal laws and NOT used to rewrite questions during this pilot. A final set of
matured development errors is also classified after the forecasts are saved.

## Three matched comparisons
1. Numeric baseline: mature own-history standardized outcomes with 20 effective prior
   samples from fixed Student-t(df5) support.
2. Jev technical: prices, QQQ and reconstructed market breadth, same benchmark support.
3. Jev news: identical numeric state plus archived company and market-tagged news.
Jev returns seven-bin probability distributions for each horizon and target (terminal,
up excursion, down excursion). Three real runs; raw distributions retained. Tiny rounded
sum differences (up to 0.04) are explicitly normalized for calculations; missing or badly
formed distributions fail, never become zero. Expected return and quantiles are computed
from reweighted empirical/prior support within bins. This within-bin modelling assumption
is explicit and must not be presented as Jev directly outputting a calibrated dollar price.

Score direction, Brier, end-price 80% coverage AND interval width/interval score, mean
error, plus separate upside90/downside90 coverage. The latter are not claimed to be a
calibrated joint path band. No stops/partial sales or trading P&L are simulated.

News is retrospective: published time <= cutoff, version availability unverified.
Provider insights are excluded. No external article instructions are followed. News
budgets and clipping are recorded, not disguised as exhaustive evidence. Historical
sector, options, MC57 and F1-F3 are absent rather than fabricated from present values.
Ticker names are excluded from numeric state, but news may identify an issuer and the
model's latent knowledge cannot be proven point-in-time. No clean-holdout claim is made.

## Existing data / protection
News artifact11038219065 verified and AES-GCM decrypted only inside runner. Optional
long OHLCV comes from previously saved encrypted artifact10962334101, not a vendor
redownload. Old/recent price vintages are merged only where overlapping closes agree;
otherwise use the recent shard and leave long-history indicators missing.
Only public candidate securities are evaluated. Raw state/news stays encrypted, reports
are aggregate. The current public website, main and jev-prod are not modified.

Research run cap $0.20, <=32 HTTP requests, 3 runs per request, one request at a time.
Actual raw Gateway cost metadata is checked; missing cost metadata stops the run and
retains the reservation. No retries can invisibly multiply paid calls.

Run: `python -m pytest research/jev_forecast_validation/test_study.py -q`, then
`python research/jev_forecast_validation/study.py prepare`, `... run`, `... seal`.
Encrypted result format: JEVVAL01 + 16-byte salt + 12-byte nonce + AES256GCM ciphertext;
PBKDF2-HMAC-SHA256 600000 iterations. AAD is the 36-byte header. Plaintext is a gzipped
TAR of research request/response and scored JSON, NOT the source news/price archives.
Rollback: stop this research workflow; no production reversion or data deletion needed.
