# 再点火凸 バックテスト

moomoo デモで動かしている「再点火凸」（2026-09-26 設計書）を、Massive 無料プランの約2年分で検証する。

## 期間（パラメータは開発期間だけで決める）

| 期間 | 範囲 | 使い方 |
|---|---|---|
| 開発 dev | 2024-10-01〜2025-09-30 | パラメータを決める。最初に全工程を通すのもここ |
| 検証 validation | 2025-10-01〜2026-03-31 | 開発で決めた値の確認 |
| 保留 holdout | 2026-04-01〜2026-09-04 | 最後に1回だけ開ける（`--open-holdout`、開けた日時を記録） |
| デモ demo | 2026-09-08〜2026-09-25 | ルールを作った期間なので別枠 |

## 動かし方

`MASSIVE_API_KEY` を環境変数か、リポジトリ直下の `.env` に入れる（画面にもログにも出さない）。

```
pip install pandas pyarrow matplotlib
cd backtest/reignite
python run.py fetch --period dev       # 途中で止めても再実行で続きから
python run.py backtest --period dev    # output/dev/summary.md ほか
```

無料プランは1分5回なので、1期間の取得に丸1日前後かかる見込み。有料プランなら
`MASSIVE_CALLS_PER_MIN=100` のように上げられる。

## 出力（output/<期間>/）

- `summary.md` … 監視網別・年別成績（スリッページ 0.5/1/2%）、9:30から判定した版との比較、IWM・SPY との相関、月別損益、本番とのズレの一覧
- `monthly_*.png` … 月別損益のグラフ
- `trades.csv` / `watchlist.csv` … 全取引と、毎日の監視リスト

## ファイル

- `config.py` … 設計書の数値（ここだけ変えればよい）
- `data.py` … Massive からの取得とキャッシュ
- `watchlist.py` … 監視リスト（D3S / 2日目 / 再点火 / アフター / プレ発）
- `sim.py` … 発火・約定・出口の1日シミュレーション
- `report.py` / `run.py` … 集計と実行
- `tests/` … `python -m pytest tests`
