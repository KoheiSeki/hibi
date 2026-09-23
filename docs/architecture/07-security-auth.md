# 認証・セキュリティ方針

## 認証の唯一化

Supabase Authを唯一の認証基盤とします。FastAPI独自のaccess/refresh tokenは発行しません。

1. Next.jsが`@supabase/ssr`でPKCE sessionを管理する
2. Next.js `proxy.ts`はsession更新と軽量なroute保護を行う
3. FastAPI呼び出し時にSupabase access tokenをBearer tokenとして送る
4. FastAPIがSupabase JWKSを使って署名・issuer・expiry・algorithmを検証する
5. 検証済み`sub` UUIDからPrincipalを構築する
6. 業務認可はFastAPIで実行する

Next.jsのroute保護はUX改善であり、認可境界ではありません。FastAPIはすべての保護endpointで独立して検証します。

## JWT検証

- asymmetric signing keyを使用する
- SupabaseのJWKS endpointを使用し、自作暗号処理を行わない
- `kid`に従ってkey rotationへ対応する
- `iss`、`exp`、`sub`、許可algorithmを検証する
- audienceを設定している場合は`aud`も検証する
- 未検証tokenのpayloadを認可に使用しない
- JWKS cacheはkey rotation方針に合わせ、明示的に破棄可能にする
- `user_metadata`を認可に使用しない
- role/permissionはDBまたは管理された`app_metadata`で扱い、JWTの鮮度を考慮する

## 認可

- 認証と認可を分ける
- Principalは`user_id`と明示的な権限だけを持つ
- Repository queryは所有者条件を必須とする
- 別ユーザーresourceへのアクセスは原則404として存在を秘匿する
- 管理操作は専用permissionで保護する
- AIの出力を認可判断に使わない
- Web側の非表示制御だけで保護しない

## Supabase key

- Browserへ公開可能なのはpublishable keyだけ
- secret keyまたはservice role keyを`NEXT_PUBLIC_*`へ設定しない
- secret keyは必要なサーバー処理に限定し、通常の業務DBアクセスには使用しない
- Web、API、Workerで環境変数を最小権限に分ける
- dev/staging/prodでSupabase projectとsecretを分離する

## Database

- 業務tableをprivate schemaに置き、Data APIへ露出させない
- exposed schemaのtableを利用する場合はRLSを必須にする
- `TO authenticated`だけを認可とみなさず、所有者条件を追加する
- UPDATE policyには`USING`と`WITH CHECK`を設定する
- RLSで使う列へindexを付ける
- viewは必要に応じ`security_invoker = true`を指定する
- `SECURITY DEFINER`は非公開schema、権限検査、限定GRANTがある場合だけ使用する
- migration roleとruntime roleを分ける
- productionで日常的に管理者接続を使わない

## Web

- Server/Client Component境界でsecretをClientへ渡さない
- `NEXT_PUBLIC_*`は完全公開情報として扱う
- CSP、HSTS、`X-Content-Type-Options`、適切な`Referrer-Policy`を設定する
- user入力をHTMLとして描画しない
- やむを得ずHTMLを扱う場合は信頼できるsanitizerとTrusted Typesを検討する
- cookieは`Secure`、`HttpOnly`、適切な`SameSite`を使う
- Server Action/Route Handlerも通常APIと同様に認証・認可する
- redirect先をallowlistまたは相対pathに限定する

## API

- CORSはVercel production/preview等の明示的originだけを許可する
- wildcard originとcredentialを組み合わせない
- body size、file size、MIME type、request timeoutを制限する
- 公開/高コストendpointへrate limitを設定する
- Webhookはraw bodyで署名検証し、timestampとidempotencyを確認する
- OpenAPI docsのproduction公開範囲を決める
- health endpointへsecretや詳細例外を返さない

## Storage

- bucketはprivateを基本とする
- pathに検証済みuser IDを含める
- APIが所有権、MIME、容量を検証して短命な署名付きURLを発行する
- Browserへ恒久的な管理keyを渡さない
- upload完了後にmetadataを確定し、未確定objectを定期削除する
- OCRやparserへ渡すfileを信頼せず、サイズ・形式・malware対策を行う

## AI・プライバシー

- providerへ送信するデータを必要最小限にする
- prompt・ログからtoken、password、住所等の不要なPIIを除く
- providerごとの学習利用、retention、regionを確認する
- system promptやtool権限をuser入力から分離する
- prompt injectionを認可境界で防ごうとせず、tool側で権限検査する
- 外部操作はallowlist、schema validation、確認画面を通す
- userデータ削除時にembedding、file、AI関連metadataも削除する

## Secret管理

- `.env`をcommitしない
- `.env.example`には値ではなく用途・公開可否・取得元を書く
- Vercel、Render、Supabaseのsecret storeを使用する
- secretをログ、exception、Sentry breadcrumbへ載せない
- 漏洩時のrotation手順をrunbookに記載する
- GitHub secret scanningとpush protectionを有効にする

## 最低限の脅威モデル

実装開始前に次を洗い出します。

- 認証回避・IDOR/BOLA
- token盗難・session固定
- prompt injection・過剰なtool権限
- file upload攻撃
- SSRF
- webhook replay
- queue/jobの重複実行
- secret漏洩
- tenant間のvector検索漏洩
- 個人データの過剰保存

重大な機能追加時は脅威モデルを更新します。
