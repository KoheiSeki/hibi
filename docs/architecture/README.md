Phase 14 設計方針

Hibi（日常コパイロット）を別リポジトリで実装するための設計基準です。個別機能ではなく、React 19・Next.js・FastAPI・Supabaseを使う中小規模プロダクトにも再利用できる方針を示します。

決定事項

製品名: Hibi

推奨リポジトリ名: hibi

同一オーナー内で衝突する場合は hibi-copilot

リポジトリ方式: FE/BEを1つにまとめるモノレポ

アーキテクチャ: モジュラーモノリス、デプロイ単位はWeb・API・Worker

Web: Next.js 16 App Router、React 19、TypeScript strict、Vercel

API/Worker: Python 3.14、FastAPI、arq、Render

データ基盤: Supabase PostgreSQL、pgvector、Auth、Storage

API契約: FastAPI OpenAPIを唯一の正とし、TypeScriptクライアントを生成

AI責務: Jevは分類・スコア・ルーティング、LLMは生成・要約・構造化抽出

パッチバージョンはリポジトリ作成時点の最新安定版を採用し、lockfileで固定します。2026年9月時点のPython最新安定版は3.14系です。

リポジトリ名

第一候補はhibiです。製品名と一致し、FE/BEやホスティング構成が変わっても
名前が陳腐化しません。

hibi: 推奨。短く、製品全体を表せる

hibi-copilot: 同一オーナー内の名前衝突時の代替

hibi-app: 用途が曖昧なため採用しない

hibi-web / hibi-api: モノレポ全体を表さないため採用しない

npm/Pythonの公開package名はリポジトリ名と分離し、公開予定がなければ
private packageとして扱います。

ドキュメント一覧

アーキテクチャ方針

プロジェクト構成

命名規約

エラーハンドリング

Git・ブランチ運用

API・データ契約

認証・セキュリティ

テスト・品質管理

運用・監視・依存更新

公式リファレンス

実装スケジュール

ADRテンプレート

規約の強さ

MUST: 原則として例外を認めない

SHOULD: 合理的な理由がある場合のみ例外を認める

MAY: 状況に応じて選択できる

MUST/SHOULDから外れる判断は、コードコメントではなくADRに理由と影響を記録します。

スコープ外

初期リリースでは以下を採用しません。

マイクロサービス

Kubernetes

GraphQL

Next.jsからの業務テーブル直接操作

独自JWT発行

複数のスキーマ管理ツール

AI判定だけに依存した認可・削除・課金等の不可逆操作

規模・チーム・独立スケール要件が発生した時点で、計測結果とADRに基づいて見直します。
