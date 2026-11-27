# Git・ブランチ運用方針

## 基本方針

一人開発でもGitHub Flowを採用します。長期ブランチは`main`だけとし、`develop`、`release/*`は作りません。

- `main`は常にデプロイ可能な状態を維持する
- 原則として`main`へ直接pushしない
- すべての変更を短命なbranchとPull Requestで管理する
- Pull Requestを設計・CI・Preview確認の単位にする
- squash mergeで1 PRを1 commitにまとめる
- `main`へのmergeを本番リリースの入口にする

## ブランチ名

```text
feat/capture-inbox
fix/auth-token-refresh
refactor/capture-policy
docs/error-handling
chore/update-fastapi
security/rotate-auth-key
```

形式は`<type>/<short-kebab-case>`です。

許可するtype:

- `feat`: 利用者に見える機能
- `fix`: 不具合修正
- `refactor`: 動作を変えない構造改善
- `docs`: ドキュメントのみ
- `test`: テストのみ
- `chore`: 依存更新・設定・保守
- `security`: セキュリティ対応

branchは`main`から作り、数日以内にmergeまたは削除できる粒度を目標にします。

## Commit

Conventional Commitsを使用します。

```text
feat(captures): add capture creation endpoint
fix(auth): reject expired Supabase tokens
test(captures): cover duplicate idempotency key
docs(architecture): record outbox decision
```

規則:

- 命令形・現在形で書く
- 1 commitは1つの論理変更にする
- `wip`、`update`、`fix`だけの曖昧なmessageを残さない
- secret、生成キャッシュ、大容量データをcommitしない
- merge前の試行錯誤commitはsquashする

## Pull Request

PRには最低限次を記載します。

```text
Why:
- 解決する問題

What:
- 主要変更

Verification:
- 実行したテスト
- Preview URLまたは確認手順

Risk / Rollback:
- 想定リスク
- 戻し方

Migration:
- DB/API契約/環境変数への影響
```

一人開発でもセルフレビューを行います。

- PRのdiffを先頭から読む
- 不要ファイル・debug log・secretがないか確認する
- 仕様・実装・テストが一致しているか確認する
- migrationと旧コードの互換性を確認する
- UI変更はVercel Previewで確認する

## 必須CI

merge前に以下を成功させます。

Web:

- format check
- ESLint
- TypeScript type check
- unit/component tests
- Next.js production build

API:

- Ruff format/check
- static type check
- pytest unit/integration
- OpenAPI生成
- Docker build

共通:

- OpenAPI生成物の差分検出
- Supabase migration/RLS test
- secret scan
- dependency vulnerability scan
- 主要E2E

生成後にuncommitted diffが残る場合、契約更新漏れとしてCIを失敗させます。

## リリース

- VercelはPRごとにPreviewを作る
- Renderは`main` merge後にAPI/Workerをデプロイする
- production migrationは互換性を確認してから適用する
- releaseにはcommit SHAを付与し、Web/API/Sentryで共通化する
- rollbackはアプリの直前artifactへ戻す
- migrationは原則ロールフォワードで修正する

大きな変更は次の順序に分けます。

1. Expand: 新旧コードが動く追加的schema変更
2. Migrate: backfillと新コードへの切替
3. Contract: 利用されなくなった旧schemaの削除

破壊的migrationと、それを前提にするコードを同時に一発リリースしません。

## 緊急修正

1. `main`から`fix/`または`security/`branchを作る
2. 再現テストを追加する
3. 最小修正を行う
4. 必須CIを通す
5. PRをsquash mergeする
6. production確認後、原因と再発防止をissueまたはADRへ記録する

緊急時でも長期的な`hotfix`branchは作りません。

## バージョニング

初期段階はSemVerタグを必須にせず、`main`のcommit SHAをrelease識別子にします。外部利用者へAPIを公開する段階で`v1.0.0`からSemVerを開始します。
