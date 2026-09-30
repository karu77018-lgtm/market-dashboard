# Universal Expectation Gap v1 — 2026-10-01

Status: **DETERMINISTIC CORE RESEARCH / NOT ADOPTED**

MC57/V38 production rules are unchanged.

## Architecture

- Core signal: deterministic only.
- Python owns Expectation Load, fundamental/price features, calibration, ranking, and every backtest.
- Backtests run in the assistant's local Python runtime, not GitHub Actions.
- GitHub stores code, frozen inputs/outputs, and audit notes only.
- Jev is optional and isolated from the core. It may be tested later only as an incremental semantic overlay.
- Massive supplies raw evidence/data where entitled.
- No direct Jev price forecast and no production dependency on Jev.

## Deterministic core first

The core research question is whether simple, point-in-time expectation measures separate future returns:

1. 20D stock run-up.
2. 20D excess return versus QQQ.
3. RS change only if it adds held-out value.
4. High/extension measures only if they add held-out value.
5. Event-specific magnitude/risk layers are separate.

Do not add semantic complexity before the simple baseline is validated.

## Jev policy

Jev is **not required** for Universal Expectation Gap.

The optional English-only Jev workflow is manual-only and writes to separate
`jev-overlay-*` outputs. It cannot overwrite the deterministic-core artifacts.
Jev is kept only if a frozen A/B ablation shows incremental out-of-sample lift
over the deterministic model.

## Backtest policy

- No GitHub Actions backtests.
- Use local Python.
- Freeze calibration windows before holdout scoring.
- Compare against simpler baselines, not only against zero.
- Preserve point-in-time timing and reject look-ahead.
- No production adoption from one partial-month holdout.

## Current local evidence

The earnings Expectation Load event set was re-scored locally with July-August
as calibration and September as a frozen holdout. The local calculation
reproduced the stored OOS split exactly:

- Core <60: n=44, 5D median -2.60%, mean -3.22%, P(5D<0)=61.4%.
- Core >=60: n=12, 5D median -11.10%, mean -12.51%, P(5D<0)=83.3%.

A simpler 20D QQQ-excess baseline was at least as strong in this holdout:
n=12 above the same research threshold, 5D median -11.41%, mean -13.25%,
P(5D<0)=91.7%.

Therefore model simplification is the current priority, not adding Jev.

## Decision

Keep researching the deterministic signal. Do not promote it to MC57/V38 yet.
