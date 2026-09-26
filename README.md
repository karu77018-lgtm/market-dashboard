# market-dashboard / source-mc57 recovery

This repository publishes the recovered `source-mc57.html` page independently.
The refresh workflow reconstructs the frozen source, acquires TradingView
fundamentals, Massive reference/grouped daily data, Yahoo daily history, and FRED
macro series, calculates the fixed-universe MC57, and commits only the source
page, independent candle shards, and an audit manifest.

The stock universe preserves the prior market-cap/price route and adds liquid,
volatile $50M-$200M common shares/ADRs only when Massive confirms the current
session, at least 10 recent sessions, median dollar volume of at least $20M, and
median ADR20 of at least 2.5%. Massive also supplies advance/decline and
up/down-volume internals and cross-checks Yahoo current closes. FRED supplies
Treasury yields, real yields, breakeven inflation, the 10Y-2Y curve, HY OAS, and
NFCI. Repository secrets are `FRED_API_KEY` and `MASSIVE_API_KEY` (legacy
`POLYGON_API_KEY` is also accepted).

The audited frozen runtime and 2026-09-16 seed inputs are stored together in
`bootstrap/recovery-assets.tar.xz`; the workflow restores them before building.

The workflow deliberately does not commit or replace V38, `index.html`, or
`data/*.json`.
