# Setups validation (2026-10, local research)

Run locally only (never on GitHub Actions). Data: Yahoo daily bars for the 5,372 US common
stocks listed on 2026-10-05 (nasdaqtrader symbol directory), 2013-2026. Current listings only:
delisted names are missing, which flatters every result (the IPO study bounds this below).

Common rules: QQQ above its 200-day line; entry at the signal close; stop -8% (gap -> open);
exit at the close below the 21-EMA of lows; same-amount adds at +10% and +20%. PF with adds is
computed on dollar P&L in units of the first stake.

| list (2015-2026) | trades | PF | PF with adds | PF 2015-20 | PF 2021-26 |
|---|---|---|---|---|---|
| any liquid stock (price >= $10, DV20 >= $20M), sampled | 196,344 | 1.09 | 1.09 | 1.29 | 0.98 |
| 発火前 | 5,853 | 1.11 | 1.13 | 1.30 | 0.99 |
| ポケットピボット | 15,854 | 1.11 | 1.12 | 1.62 | 0.90 |
| 21EMAタッチ | 23,149 | 1.16 | 1.14 | 1.50 | 0.96 |
| VCP (proxy) | 1,337 | 1.09 | 1.09 | 1.21 | 1.00 |
| Multi VWAP | 20,669 | 1.04 | 1.05 | 1.36 | 0.90 |
| 底打ち (proxy) | 6,062 | 1.12 | 1.22 | 1.74 | 0.94 |
| leader states ①-⑤ | 12k-20k each | 0.97-1.15 | 0.95-1.18 | | |
| rule selection (TT, DV top 5%, RS189 top 10%) | 1,425 | 1.40 | 1.57 | 2.26 | 1.36 |
| IPO base (listed < 2y, first bases) | 237 | 1.63 | 1.80 | 2.79 | 1.04 |

Inside the rule's selection the patterns do not improve it (発火前 0.94, PP 1.63, 21EMA 1.46,
VWAP 1.39 vs 1.57). Conclusion: Setups keeps IPO base (outside the rule's reach) and the
put-wall touch (no history; weekly forward validation); the rest moved to the archive tab.

IPO base robustness: PF 1.4-2.0 over volume 1.0-1.8x, base 10-40 days, depth 5-60%,
liquidity $10-50M, age 1-3 years. Survivorship: the edge disappears if delisted IPOs had added
losing breakouts equal to 44% of the trades found. Standalone 6-slot IPO portfolio: 8% a year
(15% with half the idle money in QQQ) vs QQQ 18% -> watch list, not a slot.

Scripts: fetch_meta.py, fetch_bars.py (data), study.py/stats.py/grid.py/portfolio.py (IPO),
panel.py, evaluate.py, trades_all.py, setup_stats.py, sel_check.py (setups).
