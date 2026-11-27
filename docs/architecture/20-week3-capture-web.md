# Week 3 Step 7: Capture Web（入力・一覧）

[Capture 契約](./13-week3-capture-contract.md) の実装順 7。[Capture Router / OpenAPI](./19-week3-capture-router.md) の上に、モバイル前提の `/captures` と detail を載せる。色、書体、配置は [Capture 画面の見た目](./21-capture-visual.md) を正にする。

## このステップのゴール

ログイン済みユーザーが、片手で一文を残し、自分の Capture を時系列で見返し、編集・削除できる。業務ロジックは FastAPI のまま。Web は生成 client と Server Action だけを使う。

完了条件:

- 未ログインの `/captures` と `/captures/[captureId]` は `/login`（`getUser()`。アカウント画面と同じ）
- `unauthenticated` も `/login`。401 Problem と 5xx は redirect せず `ApiErrorMessage`（[12](./12-week2-auth-failure-contract.md)）
- `/captures` は入力 + 自分の一覧。empty / loading / error を必ず持つ
- 初回一覧は Server Component で取得し、「さらに表示」は Client Component が Server Action 経由で取得して既存行へ追記する
- `/captures/[captureId]` は本文・編集・削除。他者・不存在は `notFound()`
- 作成は生成 client の `createCapture`。`Idempotency-Key` は Client Component が **投稿意図ごとに** 1 つ
- 表示は生成型 `CaptureResponse`。手書きの Capture 型を作らない
- `rawText` は HTML として出さない
- `status` は描画しない
- 通常 CI の Web テストで [契約](./13-week3-capture-contract.md#web) の表を確認する

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 処理中 polling / retry / カテゴリ | Week 4 以降。契約 |
| 業務 table の直接操作 / 代替 Route Handler | [01](./01-architecture.md) |
| ログイン・アカウント画面の全面リデザイン | Capture の layout だけ変える |
| 無限スクロール / 検索 | `hasNextPage` なら「さらに表示」まで |
| profile.timezone の読込 | この週の表示は `Asia/Tokyo` 固定 |
| 専用の削除 modal | `window.confirm` でよい。後で差し替え可 |
| OpenAPI の手編集 | 生成物は触らない |

## 画面の仕事

対象: スマホで「いまの一文」を残し、自分のメモをすぐ見返す。

入力は **画面下（親指）** に固定する。一覧は上でスクロールする。Capture は時刻の列なので、番号ではなく **JST の時刻列** をリストの背骨にする。

```text
┌──────────────────────────┐
│  Hibi              アカウント │  低めのバー。root の py-16 は使わない
│  10月2日 木                 │  今日の日付（Asia/Tokyo）
├──────────────────────────┤
│  14:02   牛乳を買う          │  左: tabular 時刻 / 右: 本文 1〜2行
│  09:11   資料を送る          │  カードを重ねない。行全体が detail へ
│  …                         │
├──────────────────────────┤
│  [ 何を残しますか          ] │  min 44px。safe-area を足す
│  [            記録する ]   │  空なら disabled。送信中は disable
└──────────────────────────┘
```

空のときもコンポーザは出す。「最初の一文を書いてください」。API の loading / error は **一覧エリアだけ** 差し替える。入力欄は `page.tsx` に置き、一覧を Suspense で包む（失敗しても書きかけが残る）。`loading.tsx` はルート遷移の初回待ちだけに使う。

detail:

```text
時刻（JST）
本文の編集欄
保存する / 削除する
```

コピー:

- 送信: 「記録する」（送信中: 「記録しています」）
- 更新: 「保存する」
- 削除: 「削除する」
- 空一覧: 「最初の一文を書いてください」
- 422 の入力エラー: 入力欄の直下。API の `detail` を見出しにしない

## 見た目

色、書体、苔の糸、下段の入力面は [Capture 画面の見た目](./21-capture-visual.md)。この文書では繰り返さない。ログインとアカウントも同じトークンを使う。時刻の糸は記録の一覧だけに置く。

## 依存の流れ

```text
Browser
  → CaptureComposer（Client。Idempotency-Key）
    → createCaptureAction
      → session.access_token
      → createCapture({ auth, headers: { Idempotency-Key }, body })
        → FastAPI
  → captures/page.tsx（Server）
      → getUser() → 無ければ /login
      → Suspense
        → CaptureListSection（Server。初回だけ）
          → listCapturesFromApi({ limit: 20 })
          → CaptureResponse[] を CaptureListItemView[] へ変換
          → 失敗: unauthenticated → /login
                 401 Problem / 5xx / network → ApiErrorMessage
          → CaptureListPager（Client。items / nextCursor / hasNextPage）
            → 「さらに表示」
              → listCapturesAction({ cursor: nextCursor })
                → server 側で limit = 20
              → 取得行を既存 items へ追記
```

```text
Web は RFC 9457 を ApiResult にする
FastAPI は業務ルールを変えない
手書きの Capture 型は作らない
```

## 作成・変更ファイル

### 新規

| ファイル | 要点 |
| --- | --- |
| `apps/web/src/app/captures/layout.tsx` | Paper 背景、Noto Sans JP、低めのバー（Hibi / アカウント）。`py-16` を打ち消す |
| `apps/web/src/app/captures/page.tsx` | 日付見出し、一覧、下段コンポーザ。empty / error |
| `apps/web/src/app/captures/loading.tsx` | `/captures` への遷移待ち。一覧の再取得は page 内 Suspense にし、コンポーザは残す |
| `apps/web/src/app/captures/error.tsx` | セグメントの想定外。再試行 |
| `apps/web/src/app/captures/[captureId]/page.tsx` | getCapture。404 → `notFound()` |
| `apps/web/src/app/captures/[captureId]/loading.tsx` | detail の待ち |
| `apps/web/src/features/capture/actions.ts` | `listCapturesAction` / `createCaptureAction` / `updateCaptureAction` / `deleteCaptureAction` |
| `apps/web/src/features/capture/capture-composer.tsx` | Client。key 発行、textarea、記録する |
| `apps/web/src/features/capture/capture-list-section.tsx` | Server。初回一覧取得、エラー・empty、表示型への変換、Pager への初期値 |
| `apps/web/src/features/capture/capture-list-pager.tsx` | Client。items / nextCursor / hasNextPage を保持し、取得結果を追記 |
| `apps/web/src/features/capture/capture-list.tsx` | 表示専用。時刻列 + 本文。cursor や API を知らない |
| `apps/web/src/features/capture/capture-detail-editor.tsx` | Client。保存・削除確認 |
| `apps/web/src/features/capture/format-jst.ts` | UTC → `Asia/Tokyo`。日付見出しと `HH:mm` |
| `apps/web/src/lib/api/capture.ts` | server-only。`listCapturesFromApi` / `getCaptureFromApi`。meta を落とさない |
| `apps/web/tests/captures-page.test.tsx` | 未ログイン redirect、empty、500 で login へ飛ばない |
| `apps/web/tests/capture-list-pager.test.tsx` | cursor の再利用、既存行への追記、次 cursor への更新 |
| `apps/web/tests/capture-composer.test.tsx` | 同一意図では key を再利用する |

小さい feature では `hooks/` や `mappers/` を先に作らない。時刻フォーマットと Action の戻りが複数の変更理由を持ち始めたら分ける。

### 変更

| ファイル | 要点 |
| --- | --- |
| `apps/web/src/app/globals.css` | Paper / Ink / Moss / Dusk / Hairline をトークンにする。既存 `--color-hibi-*` を Capture では使わない |
| `apps/web/src/lib/api/request-api.ts` | 204 成功と `{ data, meta }` を落とさない unwrap（専用関数でも可） |
| `apps/web/src/app/login/actions.ts` | ログイン後の行き先を `/captures` にしてよい（アカウントはバーから） |
| `docs/architecture/README.md` | この文書への項目 |

`components/ui/` に Capture ドメイン名を入れない。`FormSubmitButton` / `Textarea` / `Button` / `ApiErrorMessage` を使う。

## 実装要点

### 認証

`page.tsx` 先頭で `createClient().auth.getUser()`。無ければ `redirect("/login")`。

一覧・単体の API 呼び出しで `unauthenticated` なら同じく `/login`。`kind === "problem"` の 401 は `ApiErrorMessage`（再ログインリンクは既存の `shouldOfferReLogin`）。

`page.tsx` と `CaptureListSection` は Server Component とする。分割目的は pagination の状態保持ではなく、次の責務分離と Suspense 境界である。

- `page.tsx`: 認証確認と `CapturePageFrame` / composer / 一覧の画面合成
- `CaptureListSection`: 初回一覧取得、API エラー・empty、`CaptureListItemView` への変換
- `CaptureListPager`: ブラウザ上の追記状態と cursor の保持

### 生成 client

token の渡し方は `getCurrentUserFromApi` と同じ（`baseUrl` + `auth: accessToken`）。

```text
createCapture({
  baseUrl,
  auth: accessToken,
  body: { rawText },
  headers: { "Idempotency-Key": key },
})

listCaptures({ baseUrl, auth, query: { limit, cursor } })
getCapture({ baseUrl, auth, path: { capture_id } })
updateCapture({ baseUrl, auth, path: { capture_id }, body: { rawText } })
deleteCapture({ baseUrl, auth, path: { capture_id } })
```

`baseUrl` と access token は公開引数にせず、server-only の `listCapturesFromApi` 内で取得する。呼び出し側は `{ limit, cursor }` だけを渡す。

`normalizeGeneratedResult` は `result.data.data` だけを返す。次の 2 つは別関数にする。

- 一覧: `normalizeGeneratedEnvelopeResult` で `{ data, meta }` の両方を返す（`nextCursor` / `hasNextPage` を捨てない）
- 削除 204: `data` が無くても `error` が無ければ成功。既存 unwrap に通すと `invalid-response` になる

### Idempotency-Key

`CaptureComposer` だけが key を持つ。

- マウント時に `crypto.randomUUID()` を 1 つ
- 二重送信・リトライは同じ key
- 成功後、またはユーザーが本文を空にして次の文を書き始めたときに新しい key
- Action 側で毎回 UUID を振らない

送信中は button を `disabled`。失敗は toast だけにせず、コンポーザ近くに出す。422 は `errors` の `pointer === "/rawText"` を textarea に結びつける。

### 時刻

API の `createdAt` は UTC。表示は `Asia/Tokyo`。

- 一覧左列: `HH:mm`（tabular）
- ページ見出し: `M月d日` + 曜日
- 日をまたぐ行は、その日の最初の行の上に日付を 1 行入れてよい（番号リストにはしない）

### 一覧と cursor

`limit` は `CAPTURE_PAGE_SIZE = 20` の固定値とし、Client state にはしない。

初回は `CaptureListSection` が `listCapturesFromApi({ limit: 20 })` を呼ぶ。成功時に次を `CaptureListPager` の初期値として渡す。

```text
initialItems
initialNextCursor = meta.nextCursor
initialHasNextPage = meta.hasNextPage
```

`CaptureListPager` は Client Component とし、次を state に持つ。

```text
items
nextCursor
hasNextPage
```

「さらに表示」は `listCapturesAction({ cursor: nextCursor })` を呼ぶ。`limit=20` は Action 側で固定し、ブラウザから受け取らない。成功時は新しい行を既存 `items` の末尾へ追記し、`nextCursor` / `hasNextPage` を新しい meta で置き換える。同じ cursor を同時に送らないよう、取得中は button を disable する。

Server Component や module 変数に cursor を保持しない。URL の `searchParams` だけで次ページへ遷移すると一覧が置き換わるため、このステップの「さらに表示」には使わない。不正 cursor の 400 はボタン近くの `ApiErrorMessage`。

`CaptureList` は表示専用とし、`loadMoreHref` や API 呼び出しを持たない。

### 削除

`window.confirm` のあと `deleteCaptureAction`。成功したら `/captures` へ。失敗は detail 上に `ApiErrorMessage`。

### XSS

本文はテキストノード。`dangerouslySetInnerHTML` 禁止。

## テスト方針（このステップ）

決定的テストは vitest。実ブラウザの見た目合わせはこのステップの完了条件にしない。

`captures-page.test.tsx`（アカウント画面と同じく `getUser` / API を mock）:

1. 未ログイン → `redirect("/login")`
2. 一覧 empty → 「最初の一文を書いてください」
3. 一覧 500 / network → `ApiErrorMessage`。`redirect` しない
4. 一覧 401 Problem → `ApiErrorMessage`。`redirect` しない
5. 自分の行の `rawText` が出る。HTML タグはエスケープされたテキスト
6. 他者 ID の detail は `notFound()`（`getCaptureFromApi` が 404 problem のとき）

`capture-composer.test.tsx`:

7. 同じ本文の連続 submit では `Idempotency-Key` が変わらない（Action または fetch mock の header を assert）
8. 成功後の次の入力では key が変わる

`capture-list-pager.test.tsx`:

9. 初回の items と `nextCursor` を表示する
10. 「さらに表示」は現在の `nextCursor` を `listCapturesAction` へ渡し、Action が固定 `limit=20` を使う
11. 成功時は既存 items を残して新しい items を末尾へ追記する
12. 成功時は `nextCursor` / `hasNextPage` を新しい meta へ更新する
13. 取得中は二重送信を防ぎ、失敗時は既存 items を消さずボタン近くにエラーを出す

Action の単体は、生成 client を mock して 422 の `/rawText` と 204 成功を確認してよい。

Playwright のログイン〜作成は [縦切り](./13-week3-capture-contract.md) の手動確認でよい。このステップの CI 必須にしない。

既存の `account-page.test.tsx` / `auth-failure-contract.test.ts` は壊さない。

## 実装順

1. 表示用 TSX と `capture-views.test.tsx`。layout / loading / composer view / list view / detail view
2. failing `captures-api.test.ts`。`listCapturesFromApi`（server-only、meta 付き）と `normalizeGeneratedEnvelopeResult`
3. failing `captures-page.test.tsx`。`page.tsx` は認証と画面合成、`CaptureListSection` は初回取得・empty / error・表示型変換
4. `format-jst.ts` と時刻列。変換が増えた場合だけ mapper を分ける
5. `CaptureComposer` + `createCaptureAction` + Idempotency-Key テスト
6. failing `capture-list-pager.test.tsx`。`CaptureListPager` + `listCapturesAction` で cursor を保持し、一覧へ追記
7. detail + update / delete。404 → `notFound()`、204 成功を専用 normalizer で扱う
8. 422 の `/rawText` を composer / detail の入力欄直下へ出す
9. ログイン後 redirect を `/captures` にする場合は `signInAction` とログインテストを更新
10. Web test / typecheck / lint を GREEN。見た目の微調整は実装後

## 次ステップ（縦切り確認）

ログイン済みで作成 → 一覧 → 編集 → 削除。別ユーザーの URL は 404。同じ Idempotency-Key の二重 submit は 1 件。

## 関連

- [Capture 画面の見た目](./21-capture-visual.md)
- [Week 4 Capture の非同期処理](./22-week4-async-capture.md)
- [Capture 契約](./13-week3-capture-contract.md)
- [Capture Router / OpenAPI](./19-week3-capture-router.md)
- [Week 2 認証失敗契約](./12-week2-auth-failure-contract.md)
- [プロジェクト構成](./02-project-structure.md)
- [命名規約](./03-naming-conventions.md)
- [エラーハンドリング](./04-error-handling.md)
