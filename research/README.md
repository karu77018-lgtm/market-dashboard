# Research index (all run locally; nothing here runs on GitHub Actions)

Kept = held in both halves of the history (and on the second index where one exists) and is shown on the site.
Not kept = tried and dropped; listed so it is not tested again without a new idea.

| study | kept (shown on the site) | not kept |
|---|---|---|
| `decline-anatomy-2026-11` | decline types, look-alike periods, margin debt and CAPE with further falls, horizon table (今回の下げの分解) | most single gauges as forecasts |
| `record-context-2026-11` | where a live record sits among past fresh starts, loss split (運用記録) | |
| `ftd-fakes-2026-11` | day count, next day and distribution days as fake odds; headwinds (Day4-7/16+, bonds down, dollar up) for next-open entries; stop at the FTD-day low (FTDの騙しチェック) | ~55 FTD-day factors, combined scores, waiting for confirmation, early exits on warnings, gating stock entries |
| `regime-lamps-2026-11` | F3 high under the 200-day line = volatile bottom zone, F3 recovery, all lamps calm = late; F1-F3 history and long view (レジーム警戒灯) | F1 and F2 levels, fast rises, F2 low for swing entries, TQQQ sleeve changes |
| `phase-starts-2026-11` | rally starts: above the 50-day line, not rushed, no violent day; S&P 500 -5% with VIX 23+; financial conditions not tightening (NFCI, 4 weeks) as a fourth sign; credit-type declines bounce less (局面チェック) | rally types as forecasts; FTD inside the signs; F3 recovery at rally starts (too few); TQQQ sleeve by the signs (cut returns 66.5% -> 50.1% a year); net liquidity, jobless claims, the yen, CFTC positioning, option expiry week, presidential cycle, Sep-Oct; breadth of the local panel (promising for rally starts but only 2013-, ~30 events) |

| `scripts-2026-11` | UD ratio < 1.4 on 本命; TQQQ sleeve rises at most 25% a session (both from 2026-11-24) | GreenStar HUD, Stage 4 trendline, Squeeze, Vix Fix, Chandelier / UT Bot / Supertrend exits, faster entry gates (50-day, 21EMA, distribution days, VIX term, SPHB/SPLV, stop clusters), weak-market sleeve brakes |
| `minervini-2026-11` | close >= 2x the 52-week low on 本命 (from 2026-11-27); net liquidity 13-week change and QQQ distribution days as market gauges (results page only) | VCP rules as entry conditions, 200-day up 3 months, new high within 6 months, more slots, structure / S/R / volume profile / AVWAP / pocket pivots as stock signals |
| `swing-context-2026-11` | (none yet) | pausing entries by the market phase; earnings timing. Candidate: skipping signals from the hottest sectors (better in both halves per signal and 11 of 13 years; in the engine beats random drops in 2021-26 only) |

Also tried in `phase-starts-2026-11`: S&P 500 share above the 50-day line (TradingView S5FI, weekly from 2007) at
the starts: for Nasdaq-100 rally starts breadth not collapsing over 4 weeks 58% / 54% vs 31% / 31% real bottoms,
inside the 1-2 sign band 53% vs 11%, but about 50 events; S&P 500 starts flip or are tiny. Not kept.

Live check of the stated odds: `seed/prediction-log.json` (予測の答え合わせ on the Market tab), from 2026-11-16.

`lead-alerts-2026-11/lead.py`: what came before the entry gate closing (QQQ under its 200-day average), 2014-2019 /
2020-2026, 6 closings each. Kept on the share card 地合いと本命 as 先行アラート: SPHB/SPLV -5% in 20 sessions (hit 38% /
33% vs any day 17% / 14%, caught 83% / 83%, 16-29 sessions ahead; same at -4%..-7%), F3 at 警戒 (caught 83% in
2020-2026, weak before), NFCI +0.05 in 4 weeks (hit 60% / 75%, few cases), market score under 30 (hit 50% / 57%),
and two or more lit within 10 sessions (hit 50% / 33%, caught 83% / 67%; with NFCI in the pair 75% / 100% on 7 cases).
Not kept: breakout health 不調, F1, F2, S&P -5% with VIX 23+ (only 2-9 sessions ahead).
