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

## Normal-swing allocation transition (2026-10-09)

The constants in `scripts/swing_allocation.py` define the current five-name,
20%-of-total-equity initial target (`swing-v4-max5-tqqq-sleeve`). Available funds
and the unchanged 40% per-name add cap can limit fills. The residual TQQQ-rule
sleeve keeps its 50%/100% allocation; signal selection, adds, stops, exits and the
separate three-name theme sleeve are unchanged.

The first newly frozen current-rule signal session on or after 2026-10-09 starts
an independent forward simulation at NAV 1 with no positions. An existing
same-session signal is never relabelled. The previous saved portfolio (including
all positions, pending orders and equity marks) is copied intact to
`portfolio_history`, with a transition marker. This is not an actual account
liquidation or a continuous return series. No historical results are restated
using five-name sizing. Old research tables retain their original values and
are labelled as six-name research, not verified results of the new allocation.

The prior published six-name/TQQQ display is also retained verbatim in
`track-record/legacy-v3.1-tqqq-display.json`, identified by its source commit and
page SHA256. It remains visible separately from the original saved QQQ ledger.
A six-name TQQQ reconstruction is available only as an additional comparison
when the original saved price and NAV inputs exist; display never saves it.
