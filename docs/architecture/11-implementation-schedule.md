# Phase 14 Hibi 実装スケジュール

## 前提

- 稼働: 週10時間（実装8時間、テスト・文書化・セルフレビュー2時間）
- 本体: 12週間、約120時間
- バッファ: 2週間、約20時間
- 完了条件: 14-A〜14-G、3シナリオ以上、クラウド公開、比較計測
- 実装者: 一人
- リポジトリ: `hibi`

設計基準:

- [Phase 14 設計方針](./README.md)
- [アーキテクチャ方針](./01-architecture.md)
- [プロジェクト構成](./02-project-structure.md)
- [API・データ契約](./06-api-data-contracts.md)
- [テスト・品質管理](./08-testing-quality.md)

## Week 1: リポジトリと品質基盤

- `hibi`モノレポを作成する
- `apps/web`、`apps/api`、`packages/api-client`、`supabase`を作成する
- Next.js 16、React 19、Python 3.14、FastAPIを導入する
- pnpm、uv、Docker、Supabase localを起動可能にする
- Ruff、型検査、ESLint、pytest、Webテスト、buildを設定する
- GitHub Actionsで最小構成のCIを通す
- Python 3.14とarq、DB driver、Jev SDKの互換性を検証する

完了条件:

- clean checkoutからローカル環境を構築できる
- WebとAPIのhealth checkが成功する
- CIがGREENになる

## Week 2: 認証・API契約・エラー基盤

- Supabase Authを設定する
- Next.jsでSSR sessionを管理する
- FastAPIでSupabase JWTをJWKS検証する
- 認証済みPrincipalを実装する
- Global Exception Handlerを実装する
- RFC 9457 Problem Detailsへエラー形式を統一する
- `ApiResponse[T]`と`ApiResult<T>`を実装する
- FastAPI OpenAPIからTypeScript clientを生成する
- private schema、runtime role、migration workflowを確立する

完了条件:

- login/logoutが動作する
- 保護APIが未認証リクエストを拒否する
- 別ユーザーのresourceへアクセスできない
- エラーがProblem Details形式で返る
- 認証失敗が401 Problem Detailsとしてテスト固定されている（[12-week2-auth-failure-contract.md](./12-week2-auth-failure-contract.md)）
- OpenAPI clientを再生成できる

## Week 3: Captureドメインの同期縦切り

- ER図とOpenAPIを確定する（[13-week3-capture-contract.md](./13-week3-capture-contract.md)、[14-er.md](./14-er.md)）
- Capture schemaとmigrationを作成する
- Repository、Service、Routerを実装する
- Captureの作成・単一取得・一覧・更新・削除を実装する
- モバイル向け入力画面と一覧画面を実装する
- `Idempotency-Key`と所有者条件を組み込む

完了条件:

- AIなしでCapture CRUDがFEからPostgreSQLまでE2Eで動作する
- 同一冪等キーによる重複作成が発生しない
- 別ユーザーのCaptureが取得できない

## Week 4: 非同期処理基盤

方針は [22-week4-async-capture.md](./22-week4-async-capture.md)。

- Transactional Outboxを実装する
- arq queueとWorkerを実装する
- retry回数とfailed状態を実装する
- Capture処理状態のpolling UIを実装する。見た目は [21-capture-visual.md](./21-capture-visual.md) の苔の糸の上に足し、一覧を別デザインにしない。処理中は status バッジを新設せず、節の動きと短い文言で表す
- Capture保存とoutbox作成を同一transactionにする
- jobをat-least-once前提で冪等化する。Week 3 の `Idempotency-Key` は作成APIの入口に残し、Worker の重複実行防止とは別に扱う

完了条件:

- Capture作成APIが`202 Accepted`を返す
- Worker完了まで状態を追跡できる
- jobが重複実行されても結果が壊れない
- 一時障害時のretryと上限到達後のfailed遷移を確認できる

## Week 5: Jev System One

方針は [23-week5-jev-system-one.md](./23-week5-jev-system-one.md)。

- `docs/ai/jev-questions.md`を作成する
- route、category、urgency、confidenceを設計する
- policy versionを定義する
- Jev portとadapterを実装する
- timeout、fake、結果保存を実装する
- 基礎評価datasetを作成する

完了条件:

- shopping、reminder、expense、note、chatを分類できる
- confidence閾値境界をテストできる
- mockを利用して課金なしでCIを実行できる
- 評価結果を再現できる

## Week 6: LLM System Twoとハイブリッド分岐

方針は [24-week6-llm-system-two.md](./24-week6-llm-system-two.md)。

- LLM portとadapterを実装する
- structured outputを実装する
- timeout、rate limit、invalid outputを処理する
- 低confidence時の聞き返しを実装する
- 高confidence時の確定処理を実装する
- 定型応答とLLM生成の使い分けを実装する

完了条件:

- LLMが不要な処理では呼び出されない
- 曖昧な入力だけLLMへfallbackする
- LLM呼び出し回数をmetricで確認できる
- provider障害時のエラーとretry方針をテストできる

## Week 7: 3つの日常シナリオ

方針は [25-week7-daily-scenarios.md](./25-week7-daily-scenarios.md)。

- shoppingシナリオを縦切り実装する
- reminder/appointmentシナリオを縦切り実装する
- expenseシナリオを縦切り実装する
- AI判定後の不可逆操作に決定論的policyを適用する
- 必要な操作に確認UIを追加する

完了条件:

- 3シナリオが認証済みE2Eで動作する
- ユーザー分離を確認できる
- loading、empty、error、failed状態を確認できる

## Week 8: 検索

方針は [26-week8-search.md](./26-week8-search.md)。

- pgvector embeddingとRAGを実装する
- embedding modelとversionを記録する
- ユーザー条件付きvector検索を実装する
- TF-IDFキーワード検索を実装する
- 検索APIとUIを実装する

完了条件:

- 過去のメモやレシートを意味検索できる
- キーワード検索が動作する
- 別ユーザーの検索結果が混入しない
- vector検索とTF-IDFの違いをテストで確認できる

## Week 9: Today優先度

方針は [27-week9-today-priority.md](./27-week9-today-priority.md)。

- Jev urgencyと決定論的補正から優先度を計算する
- Today Top N APIを実装する
- Today画面を実装する
- timezone、期限、完了状態を考慮する
- 同点時の順序を固定する

完了条件:

- 「今日やること」が安定した順序で返る
- 日付境界とtimezoneをテストできる
- 対象がない場合のempty stateを表示できる

## Week 10: 朝ダイジェスト・週次レビュー

方針は [28-week10-digest-and-review.md](./28-week10-digest-and-review.md)。

- arq cronを実装する
- ユーザーtimezoneとDSTを考慮する
- ダイジェストを冪等upsertする
- LLM週次要約を実装する
- queue/outboxの再試行とfailed再実行を整備する
- 通知は余力がある場合だけ追加する

完了条件:

- cronを複数回実行してもデータが重複しない
- ダイジェストAPIとUIが動作する
- failed jobを安全に再実行できる

## Week 10.5: デプロイ前の拡張(4 週)

Week 10 のあと、本番化の前に挟む。新しい AI 機能は増やさず、品質を測る仕組みと、画面の構成を固める。デプロイ後の改善を、すべて数字で比べられるようにするため。

- 分類と route の評価データを、`docs/ai/evals/capture-route-v1.jsonl` の 7 件から 50〜100 件に増やす
- 評価の runner(`just eval`)を作る。指標、model と prompt の version、トークン数と費用をレポートに残す。通常の CI は fake のまま、実モデルは手で実行する
- LLM の接続先(OpenAI 互換)を切り替えて、手元の open-weight モデルも同じ方法で測れるようにする
- 検索の評価データを作り、キーワード、意味、hybrid(RRF)を Recall@5、MRR、latency で比べる。結果がよければ hybrid を既定にする
- 画面の構成を整理する。将来のチャット(「聞く」)と興味の設定まで含めて、ナビゲーションを決める
- UI のデザインを詰める

完了条件:

- 現行の分類と route の baseline レポートがある
- 検索の 3 方式の比較レポートがあり、既定の方式を数字で説明できる
- 画面の構成と見た目が、デプロイしてよい状態になっている

## Week 11: 本番運用品質とデプロイ

- JSON構造化ログを実装する
- request IDとtrace IDを伝播する
- SentryをWeb、API、Workerへ導入する
- `/health/live`と`/health/ready`を実装する
- rate limitとAIコスト上限を設定する
- WebをVercelへデプロイする
- APIとWorkerをRenderへデプロイする
- Supabase productionを構築する
- migration、deploy、rollback手順を検証する

完了条件:

- productionで主要フローが動作する
- Preview環境がproduction DBへ接続しない
- release SHAからログとエラーを追跡できる

## Week 12: 卒業判定・計測・文書化

- Playwrightで主要E2Eを実行する
- 認証・認可・API契約・migration・AI評価を全実行する
- Jev導入前後のp50を比較する
- LLM呼び出し回数、fallback率、コストを比較する
- `docs/ai/metrics.md`を作成する
- ER図、OpenAPI、runbook、脅威モデル、READMEを最終化する

完了条件:

- 14-A〜14-Gを証拠付きで判定できる
- 3つ以上の日常生活シナリオがproductionで動作する
- JevとLLMの責務分担を説明できる
- CIとE2EがGREENになる

## Week 13–14: バッファ

次の遅延・品質問題だけに使用します。

- Jev分類精度
- Supabase接続・権限
- Python 3.14依存関係
- Vercel/Render連携
- UIの重大な操作性問題
- 性能・セキュリティ・回帰不具合

新機能は追加しません。

## マイルストーン

- M1（Week 2）: 本番品質の土台と認証済みAPI契約
- M2（Week 4）: AIなしの非同期Capture MVP
- M3（Week 7）: Jev×LLMと3シナリオのE2E
- M4（Week 10）: 検索・優先度・ダイジェスト完成
- M4.5（Week 10.5）: 評価の baseline、hybrid 検索、画面の構成
- M5（Week 12）: 本番公開・計測・卒業判定

## Phase 14 の後

Phase 14 の完了後は、次の順で拡張する。各段階の前に、週の文書(spec)と plan を作る。

| 順 | 内容 | 主な技術 |
| --- | --- | --- |
| 1 | 「Hibi に聞く」チャット。自分の記録について答える。根拠の記録へのリンクを付け、データを変える操作は確認を挟む | tool calling、SSE streaming、会話の保存、AI コスト上限、prompt injection 対策、task success rate の評価 |
| 2 | Memory Engine の最小構成。記録から事実・予定・好みを抽出し、重複を統合して、チャットの道具にする | 抽出、統合の job、reranking、検索の評価 |
| 3 | 推論の serving の比較。open-weight モデルを OpenAI 互換サーバーで動かし、商用モデルと比べて、処理ごとにモデルを選ぶ | 品質・latency・費用の計測、model routing |
| 4 | レシートの写真から支出を記録する | VLM、構造化抽出、Storage の署名付き URL |
| 5 | 興味のカテゴリと、ニュースのダイジェスト | 推薦、要約の正確さの評価、好みの学習、外部の文章の扱い |

## 週次の進め方

毎週、次の順番で進めます。

1. 週の完了条件を確認する
2. feature branchを作成する
3. failing testを先に作成する
4. 最小実装でテストを通す
5. lint、型検査、test、buildを実行する
6. Pull Requestをセルフレビューする
7. Previewまたはローカル環境で動作確認する
8. squash mergeする
9. 成果物、テスト結果、残リスク、次週スコープを記録する

## 遅延時に削る順序

2週間連続で遅延した場合は、次の順でスコープを削ります。

1. 任意の通知機能
2. 週次レビューの高度化
3. UI装飾と追加animation
4. 検索UIの高度なfilter

次は削りません。

- 認証・認可
- ユーザー分離
- 自動テストとCI
- クラウド公開
- Jev/LLM比較計測
- データ保護とエラーハンドリング
