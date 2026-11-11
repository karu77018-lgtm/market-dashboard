# ルールの追加・除外の検証（2026-11、手元での研究）

手元でだけ実行するもの（GitHub Actionsでは回さない）。V38（thanzo12wizu-stack/v38-watchlist）の機能をMC57に持ち込む価値があるかを調べた。あわせて、MC57の選定ルールと本番ルールに条件を足したり外したりして比べた。

**結論：足して良くなる条件はなかった。外すとどれも悪化した。現行ルールのまま。**

データ：nasdaqtraderに今上場している米国普通株5,860銘柄の、Yahoo日足（2013年〜2026-11-05）。過去EPSはYahooのReported EPS（`yfinance.get_earnings_dates`）。上場廃止の銘柄は入っていない（`setups-2026-10` と同じ条件）。

## 1. EPS加速（V38の `_eps_acceleration_from_dates` をそのまま使用）

- 時点：決算発表日の**翌営業日**から、その判定を使う
- 手仕舞い：`setups-2026-10` と同じ。シグナル日の終値で買い、−8%で損切り（窓は始値）、安値21EMA割れで手仕舞い、+10%・+20%で同額を買い増し
- 再現の確認：MUの判定はV38の画面と一致した（2026-06-24：4Q持続 +1214.7%）

**ルール選定の中**（TT・売買代金上位5%・RS189上位10%・QQQ>200日線）。基準の再現は1,436件・PF 1.50（`setups-2026-10` では1,425件・1.57。差は直近1か月分のデータ）

| EPSの状態 | 件数 | PF（買い増し込み） | 90%信頼区間 | 上位3件を除くと |
|---|---|---|---|---|
| 全体 | 1,436 | 1.50 | 1.19–1.87 | 1.31 |
| 加速確定（V38の主候補） | 125 | 1.02 | 0.19–2.26 | 0.10 |
| 加速確定以外 | 1,333 | 1.52 | 1.19–1.89 | 1.31 |
| 減速・減益 | 353 | 1.84 | 1.17–2.73 | 1.28 |
| 赤字・比較不能 | 434 | 1.83 | 1.22–2.57 | 1.35 |

- 加速確定の利益の90%は、MU・NVDA・METAの3件だけ
- 減速・赤字が高く見えるが、信頼区間が基準と重なっているので、良いとまでは言えない

**選定の外**（TT＋RS189≥80、2,522銘柄）

- 全体：PF 1.11
- 加速確定：1.14
- 決算後20日以内の加速確定：0.81

→ 中でも外でも、EPS加速は成績を上げない

## 2. 選定の段階で足し引きした場合（手仕舞いは同じ、`grid.py`・`grid2.py`）

- 外す：TT、RS189、売買代金上位5% は、どれを外してもPFが下がる（1.50→1.25、1.40、1.14）
- 閾値を変える：RS189≥95 は1.61、売買代金上位2% は1.78。ただし件数が半分になる
- 足す：52週高値に近いほどPFが上がる
  - −15%以内：1.59
  - −10%以内：1.71
  - −5%以内：1.88
  - −3%以内：1.95
- 翌日の寄りで約定させても、PFはほぼ同じ

## 3. 本番ルールで足し引きした場合（`prod_signals.py`・`prod_sim.py`・`prod_grid.py`）

**本命の作り方：** `scripts/swing_screener.py` のコードをそのまま使った（`_states`、`structure_detail`、`weekly_sar_state`、`buyable`、`tier`）。

**売買の仕方：** `track_portfolio.step` の現行の設定（v6）に合わせた。
- 6銘柄×1/6、株は合計80%まで、翌日の寄りで約定
- −8%で損切り、+10%・+20%で同額を買い増し（1銘柄40%まで）
- 安値21EMA割れ、または買ってからの最高値の−15%で、翌日の寄りで手仕舞い
- 余剰資金は現金

**再現の確認（2015-01〜2026-10-28）：** 個別株だけで年率**27.1%**・最大DD −25.4%・2022年 −8.7%。`backtest_summary.py` の 26.7%・−25.5%・−8.7% とほぼ一致。

| 変更 | 年率 | 最大DD | 2021–26 |
|---|---|---|---|
| 現行 | **27.1%** | −25.4% | 41.2% |
| 週足SAR・HL寄りを外す | 23.6% | −28.3% | 33.4% |
| HL寄りの除外だけ外す | 23.3% | −25.9% | 34.1% |
| ＋売買代金上位2% | 26.1% | −27.1% | 37.9% |
| ＋50日線乖離+25%以内 | 25.2% | −23.1% | 39.2% |
| ＋RS189≥95 | 23.1% | −36.1% | 32.7% |
| ＋RS63≥80 | 19.3% | −29.2% | 22.6% |
| ＋52週高値−15%以内 | 16.4% | −23.6% | 20.6% |
| ＋52週高値−5%以内 | 9.0% | −22.7% | 8.2% |
| ＋EPS加速確定を除外 | 27.0% | −25.0% | 40.7% |
| ＋EPS減速・減益を除外 | 23.3% | −30.9% | 33.2% |

- **52週高値の近さは、選定の段階ではPFを上げるのに、本番では年率を大きく下げる。** 「形」の条件とHL構造がすでに押し目や保ち合いの位置を選んでいて、それと打ち消し合うと考えられる。選定の段階だけの検証で条件を決めてはいけない、という例
- 約50通りを試したので偶然の当たりも混ざりうるが、今回はすべて現行より悪い側に出ている

## 実行の順番（作業フォルダで実行。生データはcommitしない）

```
python fetch_symbols.py && python fetch_bars.py fetch_list.json 4
python panel_sel.py                      # w_*.pkl, sel.pkl, sel_tickers.json
python fetch_eps.py sel_tickers.json
V38_BUILD_DASHBOARD=/path/to/v38-watchlist/build_dashboard.py \
  python eps_state.py sel.pkl sel_tickers.json eps_labels.pkl eps_detail.csv
python eps_groups.py && python trades.py sig_eps.pkl tr_eps.pkl
python fetch_eps.py out_tickers.json
python eps_state.py out_universe.pkl out_tickers.json eps_labels_out.pkl eps_detail_out.csv
python out_groups.py && python trades.py sig_out.pkl tr_out.pkl
python grid.py && python trades.py sig_grid.pkl tr_grid_close.pkl && python trades.py sig_grid.pkl tr_grid_open.pkl nextopen
python summarize.py tr_grid_close.pkl tr_grid_open.pkl results_selection_grid.csv
python grid2.py && python trades.py sig_grid2.pkl tr_grid2.pkl
python prod_signals.py && python prod_grid.py   # prod_grid.csv
```

`trades.py` の第3引数に `nextopen` を付けると、翌日の寄りで約定する。

結果：`results_*.csv`
