# プロンプト監査レポート（market-dashboard / MC57）

監査日: 2026-10-03 / 対象コミット: `7db3aab`

## 前提（ここが違っていたら範囲を指定して再実行してください）

- **範囲**: リポジトリ内でエージェントに届くテキストすべて。`git ls-files` と `find` で確認した結果、**`CLAUDE.md`・`.claude/`（スキル・サブエージェント・カスタムコマンド）・`SKILL.md`・`.mcp.json` はどれも存在しません。**
  実際の対象は次の3つだけです。
  - `AGENTS.md`（13行。Codex 向けだが、Claude Code もこのセッションでプロジェクト指示として読み込んでいる）
  - `tools/jev_mcp.py` の MCP ツール定義（`jev_evaluate` の description とパラメータ説明、サーバーの `instructions`）
  - `.codex/config.toml`（MCP 登録の行だけ確認。秘密情報がありうるため全文は読んでいない）
- **対象外**: ユーザー単位の設定（`~/.claude/` など）と、このクラウドセッション自体のシステムプロンプト（リポジトリから編集できない）。
- **想定モデル**: Claude Opus 5.5 / Sonnet 5.5（依頼どおり）。`AGENTS.md` は Codex（Anthropic 以外）も読み、Jev は Vercel AI Gateway 経由の別モデルです。これらを Anthropic SDK に切り替える提案はしていません。
- **Claude API の呼び出しコード**: なし（`anthropic|claude-|openai` の grep で 0 件）。そのためグループ4（リクエスト設定）は該当なしです。

## 依頼された重点チェックの結果

| # | チェック項目 | 結果 |
|---|---|---|
| 1 | 過剰な指示（「必ず詳しく」「念のため全部確認」など） | **0件**。`MUST/ALWAYS/NEVER/CRITICAL/必ず/念のため/詳しく` は指示ファイルに出てこない。ただし範囲の広いトリガー文が1件ある（中-1） |
| 2 | 存在しないパス・古いファイル名 | **壊れた参照は0件**。`source-mc57.html`、`chart-data/*.json`（`index.json` と shard 33個）、`latest-manifest.json`、`data/jev-ranking.json`、`assets/jev-ranking.js`、`tools/jev_mcp.py` はすべて存在。ただし `AGENTS.md` はこれらに一切触れておらず、Claude からは使えない MCP ツールを前提にしている（高-1） |
| 3 | データ取得ルールの矛盾 | **矛盾なし**。コード（`scripts/refresh_mc57.py:613,724`）・ワークフロー（`refresh-source-mc57.yml:11-12`、21:45 UTC＝JST 06:45 に yfinance で provisional を出し、05:30–19:30 UTC の Massive プローブで confirmed に差し替え）・README の三者が一致している。ただし**ルールがどの指示ファイルにも書かれていない**（中-3） |
| 4 | GitHub への書き込みを増やす指示 | **指示ファイルには0件**。一方、ワークフロー側は方針から外れている：研究用バックフィルが GitHub Actions 上で動いており（低-1）、1セッションごとに main へ2回コミットしている（低-2）。方針自体も文書化されていない（中-3） |
| 5 | ルール同士の矛盾・重複 | `AGENTS.md` とツール定義の重複（質問タイプ、`boolean` の扱い）は内容が一致しているため問題なし。ただし「Jev」という名前が、別々の2つのシステムを区別せずに指している（中-2） |

---

## 高

### 高-1 `jev_evaluate` は Codex にしか登録されていないが、Claude にも使う前提で書かれている
- **場所**: `AGENTS.md:1,5,7`（参照する側）／`.codex/config.toml:1-3`（唯一の登録先）
- **なぜ問題か**: このツールを登録しているのは `.codex/config.toml` だけで、`.mcp.json` はありません。このセッションで検索しても `jev_evaluate` は見つかりませんでした。そのため Claude は、存在しないツールを使えという指示を受けた状態になります。結果として、呼び出しに失敗するか、「キーがない」という誤った報告につながります。
- **修正案（rewrite）**: このツールは Codex 専用で、他のエージェントでは使えないと1文で明記する → `prompt-audit/02-agents-codex-scope.patch`

### 高-2 ツール説明に、コードが必須にしている項目が書かれていない（書き足しが必要）
- **場所**: `tools/jev_mcp.py:111-129`（説明）と `:49-55`（検証処理）
- **なぜ問題か**: コードは `instructions`（空でない文字列）を必須にし、`choice` 型には `criteria` を2つ以上要求しています。しかしスキーマの説明にはどちらも書かれていません。説明と実装がずれていると、モデルは送信してから ValueError を受け取るまで気づけず、呼び出しが無駄になります。ツール説明で一番多い失敗は「説明不足」です。
- **修正案（add）**: 必須フィールド、30秒のタイムアウト、外部ネットワークへのアクセスであること、返り値とエラーの形を説明に追加する → `prompt-audit/01-jev-tool-contract.patch`

## 中

### 中-1 Jev を使う条件が広すぎる（「verification」まで含んでいる）
- **場所**: `AGENTS.md:7`
- **なぜ問題か**: Opus 5.5 / Sonnet 5.5 は指示を文字どおりに強く守ります。「判定・分類・検証に役立つときは使う」という書き方だと、コーディング作業のほぼすべてが当てはまり、外部 API を必要以上に呼ぶことになります。
- **修正案（rewrite）**: 「作業そのものが Jev の判断を求めているときだけ使う。通常のコード確認やテストの検証には不要」に絞る → `prompt-audit/03-agents-jev-trigger.patch`

### 中-2 「Jev」が別々の2つのシステムを指しているのに区別されていない
- **場所**: `AGENTS.md:3-13` と、`scripts/run_jev_live_shadow.py:27`、`scripts/jev_backfill.py:180`、`.github/workflows/refresh-jev-shadow.yml:45`
- **なぜ問題か**: `AGENTS.md` が説明しているのは MCP 経由の TypeSafe System One（`JEV_API_KEY` を使用）だけです。しかし公開されているランキングとバックフィルは、別サービスの jev-investment-engine（`JEV_API_URL`、`JEV_API_SECRET` を使用）が作っています。このままでは、エージェントがランキングを修正しようとして MCP 側を触ったり、キーを取り違えたりするおそれがあります。
- **修正案（add）**: 2つのシステムの違いを1項目で書き分ける → `prompt-audit/04-agents-two-jev.patch`

### 中-3 運用方針（データ取得、GitHub への書き込みは最小限、バックテストはローカル）がどこにも書かれていない
- **場所**: `AGENTS.md`（該当する記述なし）。方針から外れた実例として `.github/workflows/jev-backfill.yml`（#46 で追加）
- **なぜ問題か**: この方針を知っているのは作者だけで、エージェントが推測できる情報ではありません。実際に、書かれていないために研究用の評価が Actions 上に作られました（#46）。朝の速報は yfinance、確定は Massive というルールも README とコードにしかなく、エージェントが「Yahoo は異常時の代替だから直そう」と誤解する余地があります。
- **修正案（add）**: `AGENTS.md` の先頭に3項目の方針セクションを追加する → `prompt-audit/05-agents-operating-policy.patch`

## 低（報告のみ・パッチには含めていない）

### 低-1 研究用バックフィルが GitHub Actions 上で動いている
- **場所**: `.github/workflows/jev-backfill.yml:1-53`（最長345分、成果物を30日保存）
- **なぜ問題か**: 「バックテストはローカルで行う」という方針と合いません。ただし `contents: read` なので、リポジトリへの書き込みはしていません。ワークフローはプロンプトではないため、この監査の範囲外として報告だけにしています。
- **修正案**: ローカルで `python scripts/jev_backfill.py ...` を実行する手順に切り替え、ワークフローを削除するかどうかを判断してください。

### 低-2 1セッションごとに main へ2回コミットしている
- **場所**: `refresh-source-mc57.yml:448` と `refresh-jev-shadow.yml:128`（`git log` では 2026-10-02 分が2コミットずつ）
- **なぜ問題か**: 書き込みを最小限にする方針からすると、1回にまとめられます。ただし、ソースのページと Jev の評価は意図的に分けて公開する設計（README:38-42）なので、これは判断が必要な点です。
- **修正案**: まとめるなら、shadow の評価結果を refresh ジョブの中で書き込んで1コミットにする。分けたままにするなら現状維持で構いません。

### 低-3 マニフェストのラベル `FALLBACK_YAHOO` が、予定どおりの朝の yfinance 更新を「代替」と呼んでいる
- **場所**: `scripts/refresh_mc57.py:694,721`
- **なぜ問題か**: 21:45 UTC の時点では、yfinance を使うのが通常の動作です。それを fallback と呼ぶと、マニフェストを読んだエージェントが異常と判断するおそれがあります。ただしこれはプロンプトではなくコードの命名です。
- **修正案**: 中-3 の方針セクションで意味を補えば十分です。値そのものを変える場合は、テストと UI への影響を確認してから行ってください。

---

## パッチ（未適用）

`prompt-audit/` 以下に、指摘1件につき1ファイルで置いています。どれも HEAD に対して単独で `git apply --check` が通ることを確認済みです。`all.patch` は5件をまとめたもので、こちらもチェック済みです。

| ファイル | 対応する指摘 | 対象 |
|---|---|---|
| `01-jev-tool-contract.patch` | 高-2 | `tools/jev_mcp.py`（文字列だけの変更。構文チェック済み） |
| `02-agents-codex-scope.patch` | 高-1 | `AGENTS.md` |
| `03-agents-jev-trigger.patch` | 中-1 | `AGENTS.md` |
| `04-agents-two-jev.patch` | 中-2 | `AGENTS.md` |
| `05-agents-operating-policy.patch` | 中-3 | `AGENTS.md` |
| `all.patch` | 上の5件をまとめたもの | — |

02〜05 はすべて `AGENTS.md` を変更するため、複数を順番に当てるとずれが出ることがあります。まとめて当てる場合は `git apply prompt-audit/all.patch` を使ってください。

## 今すぐ直すべき上位3つ

1. **高-1（02）**: `jev_evaluate` が Codex 専用であることを明記する。いま Claude は、使えないツールを使えという指示を受けています。
2. **中-3（05）**: 運用方針（朝＝yfinance で速報、引け後＝Massive で確定、GitHub への書き込みは最小限、バックテストはローカル）を `AGENTS.md` に書く。方針が書かれていないことが、#46 のように Actions 上で研究を動かす変更につながっています。
3. **高-2（01）**: `jev_evaluate` のスキーマ説明に、必須の `instructions` と `criteria` を書き足す。説明とコードが食い違っているせいで、呼び出しの失敗が起きる状態です。
