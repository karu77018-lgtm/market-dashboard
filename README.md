# market-dashboard / source-mc57 recovery

This repository publishes the recovered `source-mc57.html` page independently.
The refresh workflow reconstructs the frozen source, acquires a current TradingView
universe and Yahoo daily prices, calculates the fixed-universe MC57, and commits
only the source page, independent candle shards, and an audit manifest.

The audited frozen runtime and 2026-09-16 seed inputs are stored together in
`bootstrap/recovery-assets.tar.xz`; the workflow restores them before building.

The workflow deliberately does not commit or replace V38, `index.html`, or
`data/*.json`.
