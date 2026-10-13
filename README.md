# market-dashboard / source-mc57

The existing dashboard, colors, typography, tabs and trading calculations are
preserved. Operation is the swing rule (Rules tab) with idle money in the TQQQ
rule (Rules tab 9, `scripts/tqqq_rule.py`, ledger `track-record/tqqq-rule.json`):
signals on QQQ, execution in TQQQ, today's target in the card at the top of the
page. The NQ trend signal, SOXL leverage card and emergency brake are archived
(アーカイブ tab, `scripts/legacy_archive.py`) and no longer set exposure.

## Acquisition and session identity

The main refresh remains 21:45 UTC weekdays. Delayed Massive confirmation is
probed once at 05:30, 07:30, …, 19:30 UTC Tuesday–Saturday. An unavailable or
already confirmed session does not run the full acquisition or Jev evaluation.
An available probe triggers the existing refresh. Probe times are not a promise
of free-tier availability. Code pushes run verification rather than market
acquisition; a full refresh is explicitly dispatched or scheduled. Display-adapter
changes may run a lightweight verified display publication using existing data,
without provider acquisition or Drive archives.

Each session freezes its first selected ticker list and selection metadata in
private `work/universes/YYYY-MM-DD.json`. The public `universe-snapshots/` ledger
contains ticker membership, capture time and a hash, never raw fundamentals.
Reruns reuse this exact snapshot for both Yahoo provisional and Massive confirmed
publications. If the private cache is lost after publication, restore the Drive
snapshot before rerunning; reselection is refused. Scanner fundamentals are not
historically point-in-time verified, and late first captures are explicitly
marked and excluded from point-in-time backtests. This does not retroactively
repair pre-existing historical universes. `latest-manifest.json` records adopted
count, current missing count, coverage and provisional/confirmed state.

## Published files

GitHub Pages publishes `source-mc57.html`, `assets/`, `chart-data/`,
`market-history/`, `latest-manifest.json`, `data/mc57.json`,
`data/jev-ranking.json`, `universe-snapshots/`, `research-hashes/`, and
`research-snapshot-index/`. The general `data/` directory and vendor raw inputs
remain private. V38, `index.html`, and Jev engine rules are not replaced.

Jev updates only `data/jev-ranking.json`; the page loads it through
`assets/jev-ranking.js`. The ranking includes its session and source-page SHA256
(excluding the independent Jev section and hash/loader metadata to avoid a
circular hash). A mismatch displays **前回分**. Acquisition builds the page shell
without rebinding an old ranking. Evaluation binds only freshly written results.

## Preservation and corrections

Private snapshots retain provisional, confirmed and corrected content. Drive
uses a SHA256 of normalized content (ignoring specified acquisition timestamps,
not trading dates or correction reasons) to reuse identical archives. A reused
archive does not receive a new misleading hash record. Full and delta modes
remain distinct for reliable recovery; archives are never overwritten.

Same-session MC57 retains its published value by default. For an intentional
recalculation correction, dispatch the refresh with `mc57_correction_reason`
(or pass `--mc57-correction-reason` locally). The previous full calculation is
archived privately; the correction records reason, publication time, old/new
value and versions. All MC57 windows use the corrected calculation, and the
MC57 reading details show the latest correction. The formula is unchanged.

## Verification

`python -m pytest` runs deterministic provider, preservation and display tests.
`node tests/market_history_ui.cjs` verifies all 13 tabs at desktop and 375/390/430px,
including whole-page overflow, mobile Jev scores, manual NQ labels, and history
controls. Optional `CHROMIUM_EXECUTABLE_PATH` selects a local Chromium binary.

The audited frozen runtime and seed inputs are restored from
`bootstrap/recovery-assets.tar.xz`. Required repository secrets remain
`FRED_API_KEY`, `MASSIVE_API_KEY` (legacy `POLYGON_API_KEY` accepted) and existing
Drive/Jev credentials. No credentials are embedded in published outputs.

## Normal-swing allocation and the 成績 tab (2026-10-12)

`scripts/swing_allocation.py` defines the current allocation: at most six names,
first buy 1/6 of total equity (`swing-v5-max6-tqqq-sleeve`). The 5 x 20% rule used
from 2026-10-09 was withdrawn: it rested on a backtest that bought at the
signal-day close, while a 本命 is published after the close and can only be
bought at the next open. With next-open fills (the production engine,
`track_portfolio.step`, fed with the research signals) 6 x 1/6 is as good or better
in both halves of 2015-2026.

`scripts/backtest_summary.py` is the single source of the backtest figures on the
Rules and 成績 tabs (next-open fills, HY OAS with its publication lag): the current
rule 53.4% a year, max DD -36.3% (2015-01 .. 2026-08), plus the alternatives
(idle-cash share, TQQQ-rule variants, position size).

`track-record/signals.json` keeps one current model (`modeled_portfolio`): the
frozen 本命 since 2026-10-05 replayed under the current rule with the published
chart OHLC through 2026-10-09, then advanced by the daily refresh. Earlier models
(the QQQ-sleeve ledger and the 5 x 20% model) stay unchanged in
`portfolio_history` / `portfolio` and are shown folded as 旧ルールの記録.

## Review fixes (2026-10-13)

- The frozen dashboard source reads twelve diagnostic macro series (credit HYG/IEI·LQD, MOVE/TLT, VVIX, SKEW, JPY, 30Y, SQQQ/SOXS, SOXX/SMH) that the live market-input route never fetched; they are now in `MACRO_DIAGNOSTIC_SYMBOLS` (never required for publication).
- `build_exact_source_mc57_clone.DISPLAY_PATCHES`: wording-only patches to the frozen source (RS21/63/189 label; no stale FTD failure reason or "戻り売り" warning outside a correction).
- Swing/Rules/Breakout-health comparison figures were re-run on the production engine with next-open fills (stock-only 本命 28.7% vs all setups 24.8%, regime 26.1%→28.7%, 好位置 mix 53.6%/51.9%, QQQ sleeve 35.0%/39.0%/36.9%). Figures not re-run are marked 旧計算.

## Rule v6 (2026-10-13): stock cap 80% and sleeve 60%

`swing_allocation.STOCK_CAP = 0.80`: from the 2026-10-13 publication, new buys and adds never take the swing stocks above 80% of total assets at the open (nothing is sold to get under it); `SLEEVE_NORMAL = 60` (was 50) of the idle money goes to the TQQQ-rule sleeve, 100% when breakout health is weak and QQQ is above its 200-day line. Next-open backtest 2015-01..2026-08: 55.0% / max DD -35.9% (v5: 53.4% / -36.3%), not worse in either half; worst year 2022 -15.4% (v5 -12.3%). A running v5 model continues under v6 (`PREVIOUS_RULE_IDS`). Figures: `scripts/backtest_summary.py`.
