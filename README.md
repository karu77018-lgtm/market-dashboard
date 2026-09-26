# market-dashboard / source-mc57 recovery

This repository publishes the recovered `source-mc57.html` page independently.
The refresh workflow reconstructs the frozen source, acquires TradingView
fundamentals, Massive reference/grouped daily data, Yahoo daily history, and FRED
macro series, calculates the fixed-universe MC57, and commits only the source
page, independent candle shards, and an audit manifest.

The stock universe preserves the prior market-cap/price route and adds every
TradingView symbol that Massive confirms as an active US common share/ADR with
a current-session bar. Price, market-cap, history, median-dollar-volume, and
ADR20 thresholds are retained as per-symbol buy-selection annotations; they do
not restrict the research/measurement universe. Massive also supplies
advance/decline and up/down-volume internals and cross-checks Yahoo current
closes. FRED supplies
Treasury yields, real yields, breakeven inflation, the 10Y-2Y curve, HY OAS, and
NFCI. Repository secrets are `FRED_API_KEY` and `MASSIVE_API_KEY` (legacy
`POLYGON_API_KEY` is also accepted).

The audited frozen runtime and 2026-09-16 seed inputs are stored together in
`bootstrap/recovery-assets.tar.xz`; the workflow restores them before building.

The workflow deliberately does not commit or replace V38, `index.html`, or
`data/*.json`.
