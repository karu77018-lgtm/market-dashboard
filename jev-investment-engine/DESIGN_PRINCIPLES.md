# Jev Investment Engine 設計思想
更新日: 2026-09-28

## 1. 目的

Jev Investment Engine は、価格予測や売買指示を直接出すためのエンジンではなく、
既存の数値ベースの市場・個別株選定ロジックに対して、
企業開示・ニュース・IR・SEC等のテキスト情報を構造化特徴量として追加する
「意味理解レイヤー」として運用する。

Jev の役割は以下に限定する。

- Red Flag の検出
- Catalyst の検出
- Management Tone の評価
- Margin Pressure の評価
- Primary Theme の分類
- 将来の研究用テキスト特徴量の蓄積

Jev 単独で BUY / SELL / HOLD を決めない。
Jev の結果を直ちに Hard Gate やランキング加点へ使用しない。
まず Shadow 運用で実績を蓄積し、未使用期間を含む検証後に採否を決める。

---

## 2. 現在の本番構成

### 本番
Vercel:
- `jev-investment-engine`

役割:
- `/api/jev` で Jev を実行
- `jev-text-v1` の質問セットを Neon から取得
- 3-run を並列実行
- 平均値・標準偏差・不一致率を集計
- Neon に評価結果を保存

### データベース
Neon:
- Project: `jev-investment-engine`
- Question Set: `jev-text-v1`
- 15問を管理
- Jev raw runs / aggregated features / research history を保存

### 実行端末
iPhone Shortcut:
- POST `/api/jev`
- `runs = 3`
- `persist = true`
- `questionSetVersion = jev-text-v1`
- `questions` は送らない
- `ticker`
- `state`
- `asofTimestamp`

質問を Shortcut 側へ埋め込まず、Neon 側を Single Source of Truth とする。

---

## 3. 15問 Question Set

### Red Flags
- RF01 dilution
- RF02 going concern
- RF03 accounting
- RF04 management change
- RF05 legal / regulatory
- RF06 guidance cut

### Catalysts
- CAT01 guidance raise
- CAT02 demand acceleration
- CAT03 major contract
- CAT04 new product
- CAT05 regulatory approval
- CAT06 company-specific catalyst

### Text / Tone
- TXT01 management tone improved
- TXT02 margin pressure

### Theme
- THEME01 primary theme

Theme choices:
- ai_infrastructure
- semiconductors
- cloud_software
- consumer_internet
- biotech_healthcare
- industrial_energy
- financials
- other

---

## 4. 3-run 原則

Jev は完全決定論ではないため、1回の回答をそのまま採用しない。

同一 state / 同一 question set に対して 3-run を行い、

- mean
- standard deviation
- disagreement rate
- raw responses

を保存する。

研究・将来のルール採否では、
「平均スコア」だけでなく「3-run の安定性」も評価対象とする。

---

## 5. Point-in-Time 原則

過去時点の検証では、未来情報混入を防ぐ。

最低限以下を区別する。

- published_at
- available_at
- tradable_at
- asofTimestamp

Jev へ渡す state は、その時点までに市場参加者が取得可能だった情報だけで構成する。

過去日時を `asofTimestamp` に設定するだけでは不十分であり、
state 本文自体も Point-in-Time でなければならない。

---

## 6. GitHub の位置づけ

GitHub は本番実行基盤ではなく、
コードのバックアップ・履歴・復旧元として使う。

### 残すもの
`karu77018-lgtm/market-dashboard/jev-investment-engine/`

これは削除しない。

### 本番とGitHubを疎結合にする理由

Jev 本番は小さく安定させたい一方、
`market-dashboard` リポジトリでは別研究・別ブランチ・Claude作業など
Jev と無関係な変更が多数発生する。

GitHub と Vercel の自動Deployを常時直結したままにすると、

- Jevと無関係なcommitでもDeploymentが増える
- Preview Deploymentが大量に作られる
- 意図しない変更が本番候補へ入りやすくなる
- 「現在の本番コードが何か」の追跡が難しくなる
- Jev研究基盤と他研究の変更履歴が混ざる
- 安定稼働中の本番を不用意に触る機会が増える

という問題がある。

したがって、
「GitHubのコードを消す」のではなく
「GitHubの更新がJev本番へ自動反映される関係を切る」
のが設計意図。

---

## 7. トークンとの関係

GitHub更新を切る主目的はトークンではない。

`VERCEL_DEPLOY_TOKEN` は、
GitHubを使わずVercelへ直接Deployする更新経路を作る場合に使う認証手段。

つまり関係は、

GitHub自動Deployを切る理由
= 本番の安定性・責務分離・不要Deployment防止

VERCEL_DEPLOY_TOKEN
= GitHubを使わない更新経路を作るための手段

であり、目的と手段を分ける。

現時点では、
GitHub非依存の自動Deploy経路は完成確認前なので、
トークンに依存した運用へ完全移行したとは扱わない。

---

## 8. 現在確認済みの動作

2026-09-25 時点 NVDA を使用して実運用テストを実施。

確認結果:
- ticker: NVDA
- asofTimestamp: 2026-09-25T20:15:00Z
- questionSetVersion: jev-text-v1
- run_count: 3
- feature_count: 15
- status: success
- Vercel POST /api/jev: HTTP 200
- Neon persistence: success

これを「15問 × 3-run の最初の正常系基準」とする。

---

## 9. タイムアウト

15問フルセット実行時、
旧設定の 20秒 timeout では失敗した。

現在は Jev API 内の timeout を 60秒へ変更済み。

この値は無闇に増やさず、
将来は実測 latency を蓄積して必要に応じて調整する。

---

## 10. 本番変更原則

本番変更では以下を守る。

1. 既存 Production を壊さない
2. 変更は最小単位
3. Jev質問セット・DB schema・APIコードを同時に大変更しない
4. 変更後に `/api/health` を確認
5. 実POSTを1回確認
6. Neon保存を確認
7. `feature_count = 15` を確認
8. 旧状態へ戻せるバックアップを保持
9. 秘密値をチャットやGitHubへ出さない

---

## 11. バックアップ方針

最低3層を保持する。

1. Vercel Production
   - 現在動いている本番

2. GitHub
   - ソース履歴・復旧元
   - 自動Deploy元にはしない

3. Neon Release Backup
   - `engine_releases`
   - `engine_release_files`
   - GitHub非依存の復元元として保持

`jev-investment-engine-direct` は当面削除せず、
予備プロジェクトとして保持する。

---

## 12. 今後の完成形

Market / Company Data
↓
Data preparation
↓
Vercel `jev-investment-engine`
↓
Jev 15 questions × 3-run
↓
Neon
↓
Shadow features
↓
市場ダッシュボード / 個別株選定ロジック
↓
Forward validation
↓
採用 / 棄却判断

Jev は「予言機」ではなく、
テキスト情報を再現可能な研究特徴量へ変換する部品として扱う。
