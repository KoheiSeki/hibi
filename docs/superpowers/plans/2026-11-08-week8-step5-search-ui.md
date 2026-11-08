# Week 8 Step 5: 一覧の上の検索欄 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/captures` の日付の下に検索欄を置き、`GET /api/v1/captures/search` の結果を今の一覧行(`CaptureList`)でそのまま表示する。

**Architecture:** 検索状態は URL の `?q=&mode=` に持つ。検索欄は `GET` の素の `<form>` で、page が `searchParams` を読み、検索語があれば検索結果のサーバーコンポーネント、なければ今までの `CaptureListSection` を出す。client state と Server Action は足さない。結果は最大 20 件でカーソルが無いので、`CaptureListPager` は使わず `CaptureList` だけを使う。

**Tech Stack:** Next.js 16.3.6 (App Router, `searchParams` は Promise), React 19.3, `@hibi/api-client` の生成済み `searchCaptures`, vitest + `renderToStaticMarkup`。

**Spec:** `docs/architecture/26-week8-search.md` の「画面」「障害」「実装順 5」。見た目は `docs/architecture/21-capture-visual.md`。API 側は step 4 で完了済み(`f50c24b` で client 再生成済み)。

## Global Constraints

- 検索欄は日付の下、糸の上に置く。一覧の糸と節は残す
- 未入力の一覧は、今までの時刻順のまま
- 検索中は「検索しています」
- 0 件は糸の上に「見つかりませんでした」
- 結果の行は、今の一覧行と同じ。押すと詳細へ行く
- バッジと処理状態の色分けは足さない
- `q` は 1 文字以上 200 文字以下。`mode` は `keyword` または `semantic`、未指定は `keyword`
- 検索欄のラベルは「記録を検索」、方式は「キーワード / 意味」
- 色トークンは Field `#EEF3EF` / Ink `#15201A` / Moss `#1E6B43` / Leaf `#F7FBF8` / Dusk `#5A6A62` / Thread `#D5E3D9` だけを使う
- 新規ファイルのインデントは、同じディレクトリの新しいファイルに合わせてタブ。Prettier の設定はリポジトリに無いので、`just check` の `format:check` は使わない(既知の既存失敗)
- 検証コマンドは `corepack pnpm typecheck`, `corepack pnpm lint`, `corepack pnpm test`, `corepack pnpm build`

## Review Focus

1. 検索語が空白だけ(`?q=%20%20`)、または `q` なし: 検索せず、今までの一覧を出す → Task 2 のテスト
2. `q` が 201 文字以上の手書き URL: API を呼ばず(422 を避け)一覧を出す → Task 2 のテスト
3. `mode` が不正値、`q` が配列(`?q=a&q=b`): 例外にせず `keyword` / 先頭の値に倒す → Task 2 のテスト
4. API が未認証を返す: `/login` へ redirect。それ以外の失敗(意味検索で embedding API が落ちた 5xx など)は、画面全体を壊さず `ApiErrorMessage` を出す → Task 3 のテスト
5. 検索結果は `completed` だけなので処理中の行が無い。polling(`useCapturePolling`)を結果に付けない → Task 3 で `CaptureListPager` を使わないことをテストの「さらに表示が出ない」で固定

## File Structure

| ファイル | 責務 |
| --- | --- |
| `apps/web/src/lib/api/capture.ts` (変更) | `searchCapturesFromApi` を足す |
| `apps/web/src/features/capture/capture-search-params.ts` (新規) | `searchParams` を `{ q, mode } \| null` に正規化する純粋関数 |
| `apps/web/src/features/capture/capture-search-form.tsx` (新規) | 検索欄。GET の `<form>`。状態を持たない |
| `apps/web/src/features/capture/capture-search-results-section.tsx` (新規) | 検索 API を呼び、`CaptureList` か空状態かエラーを出す server component |
| `apps/web/src/features/capture/capture-search-empty-state.tsx` (新規) | 「見つかりませんでした」。`CaptureEmptyState` と同じ節の見た目 |
| `apps/web/src/features/capture/capture-page-frame.tsx` (変更) | `search` スロットを日付の下に足す |
| `apps/web/src/app/captures/page.tsx` (変更) | `searchParams` を読んで切り替える |

---

### Task 1: `searchCapturesFromApi`

**Files:**
- Modify: `apps/web/src/lib/api/capture.ts`
- Test: `apps/web/tests/capture-api.test.ts`

**Interfaces:**
- Consumes: `@hibi/api-client` の `searchCaptures`(`query: { q: string; mode?: "keyword" | "semantic" }`、200 は `{ data: CaptureResponse[] }`)
- Produces: `searchCapturesFromApi(params: { q: string; mode: "keyword" | "semantic" }): Promise<ApiResult<CaptureResponse[]>>`

- [ ] **Step 1: Write the failing tests** in `tests/capture-api.test.ts`

  先にこのファイルの `vi.mock("@hibi/api-client", ...)` に `searchCaptures: searchCapturesMock` を足す(`vi.hoisted` にも `searchCapturesMock` を足す)。足さないと `capture.ts` が import する `searchCaptures` が mock に無く、既存テストまで落ちる。

  ```ts
  describe("searchCapturesFromApi", () => {
  	it("passes q and mode with the bearer token and unwraps the data array", async () => {
  		// searchCapturesMock.mockResolvedValue({ data: { data: [capture] } })
  		// expect(result).toEqual({ ok: true, data: [capture] })
  		// expect(searchCapturesMock).toHaveBeenCalledWith({
  		//   baseUrl: "https://api.hibi.example",
  		//   auth: "access-token",
  		//   query: { q: "牛乳", mode: "keyword" },
  		// })
  	});

  	it("returns the classified error when the API responds with a problem", async () => {
  		// searchCapturesMock.mockResolvedValue({ error: {...401 problem}, response: new Response(null, { status: 401 }) })
  		// expect(result.ok).toBe(false)
  	});
  });
  ```
  失敗ケースの形は、同ファイルの既存の失敗テスト(`getCaptureFromApi` など)に合わせる。

- [ ] **Step 2: Run to verify it fails**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-api.test.ts`
  Expected: FAIL(`searchCapturesFromApi` が export されていない)

- [ ] **Step 3: Implement `searchCapturesFromApi`** in `src/lib/api/capture.ts`

  `getCaptureFromApi` と同じ形。`getServerApiContext()` が失敗ならそのまま返し、`searchCaptures({ baseUrl, auth, query: { q, mode } })` を呼び、`normalizeGeneratedResult` を通す(レスポンスは `{ data: [...] }` のエンベロープで meta が無いため、`listCapturesFromApi` の `normalizeGeneratedEnvelopeResult` ではない)。import に `searchCaptures` を足す。

- [ ] **Step 4: Run to verify it passes**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-api.test.ts`
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add apps/web/src/lib/api/capture.ts apps/web/tests/capture-api.test.ts
  git commit -m "feat(web): add the capture search API wrapper"
  ```

---

### Task 2: 検索パラメータの正規化

**Files:**
- Create: `apps/web/src/features/capture/capture-search-params.ts`
- Test: `apps/web/tests/capture-search-params.test.ts`

**Interfaces:**
- Produces:
  - `type CaptureSearchMode = "keyword" | "semantic"`
  - `type CaptureSearch = { q: string; mode: CaptureSearchMode }`
  - `const CAPTURE_SEARCH_MAX_LENGTH = 200`
  - `parseCaptureSearchParams(params: Record<string, string | string[] | undefined>): CaptureSearch | null`

- [ ] **Step 1: Write the failing tests** (`import { parseCaptureSearchParams } from "@/features/capture/capture-search-params"`)

  ```ts
  it("returns keyword mode by default", () => {
  	expect(parseCaptureSearchParams({ q: "牛乳" })).toEqual({ q: "牛乳", mode: "keyword" });
  });
  it("trims q and accepts semantic", () => {
  	expect(parseCaptureSearchParams({ q: "  ミルク ", mode: "semantic" })).toEqual({ q: "ミルク", mode: "semantic" });
  });
  it("returns null when q is missing or blank", () => {
  	expect(parseCaptureSearchParams({})).toBeNull();
  	expect(parseCaptureSearchParams({ q: "   " })).toBeNull();
  });
  it("accepts exactly 200 characters and rejects 201", () => {
  	expect(parseCaptureSearchParams({ q: "あ".repeat(200) })).not.toBeNull();
  	expect(parseCaptureSearchParams({ q: "あ".repeat(201) })).toBeNull();
  });
  it("falls back to keyword for an unknown mode", () => {
  	expect(parseCaptureSearchParams({ q: "牛乳", mode: "bogus" })?.mode).toBe("keyword");
  });
  it("uses the first value when a parameter is repeated", () => {
  	expect(parseCaptureSearchParams({ q: ["牛乳", "記事"], mode: ["semantic", "keyword"] })).toEqual({ q: "牛乳", mode: "semantic" });
  });
  ```

- [ ] **Step 2: Run to verify it fails**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-params.test.ts`
  Expected: FAIL(module not found)

- [ ] **Step 3: Implement `parseCaptureSearchParams`** in `capture-search-params.ts`

  配列なら先頭を取り、`q` は `trim()` してから長さを見る(0 または 200 超は `null`)。`mode` は `"semantic"` のときだけ `semantic`、それ以外は `keyword`。長さは `Array.from(q).length` ではなく `q.length` でよい(API 側も Python の `len` = コードポイント数だが、サロゲートペアを含む 200 文字ちょうどの境界は実用上無視する)。

- [ ] **Step 4: Run to verify it passes**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-params.test.ts`
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add apps/web/src/features/capture/capture-search-params.ts apps/web/tests/capture-search-params.test.ts
  git commit -m "feat(web): normalize capture search params"
  ```

---

### Task 3: 検索欄と検索結果

**Files:**
- Create: `apps/web/src/features/capture/capture-search-form.tsx`, `capture-search-results-section.tsx`, `capture-search-empty-state.tsx`
- Test: `apps/web/tests/capture-search-form.test.tsx`, `apps/web/tests/capture-search-results-section.test.tsx`

**Interfaces:**
- Consumes: Task 1 の `searchCapturesFromApi`、Task 2 の `CaptureSearch` / `CaptureSearchMode` / `CAPTURE_SEARCH_MAX_LENGTH`、既存の `mapCaptureResponsesToListItemViews`、`CaptureList`、`ApiErrorMessage`
- Produces:
  - `CaptureSearchForm({ defaultQuery, defaultMode }: { defaultQuery: string; defaultMode: CaptureSearchMode }): ReactNode`
  - `CaptureSearchResultsSection({ q, mode }: CaptureSearch): Promise<ReactNode>`
  - `CaptureSearchEmptyState(): ReactNode`

- [ ] **Step 1: Write the failing form tests** (`renderToStaticMarkup(<CaptureSearchForm defaultQuery="" defaultMode="keyword" />)`)

  ```ts
  it("renders a GET search form to /captures", () => {
  	// html contains 'role="search"', 'method="get"', 'action="/captures"'
  });
  it("renders the query input limited to 200 characters", () => {
  	// html contains 'name="q"', 'maxLength="200"', 'aria-label="記録を検索"'
  });
  it("offers keyword and semantic modes and checks the default", () => {
  	// html contains 'キーワード' and '意味', 'value="keyword"' checked, 'value="semantic"' not checked
  });
  it("reflects the current search", () => {
  	// defaultQuery="牛乳", defaultMode="semantic": value="牛乳" and semantic checked
  });
  ```

- [ ] **Step 2: Write the failing results tests**

  mock は `capture-list-section.test.tsx` と同じ形(`vi.mock("server-only")`, `vi.mock("next/navigation", () => ({ redirect: redirectMock }))`, `vi.mock("@/lib/api/capture", () => ({ searchCapturesFromApi: searchCapturesFromApiMock }))`)。

  ```ts
  it("renders hits with the same rows as the list and no pager", async () => {
  	// searchCapturesFromApiMock → { ok: true, data: [{ id: "capture-1", rawText: "牛乳を買う", status: "completed", createdAt: "2026-10-02T05:02:00Z", updatedAt: "2026-10-02T05:02:00Z" }] }
  	// html contains "牛乳を買う", "14:02", 'href="/captures/capture-1"', 'aria-label="記録の一覧"'
  	// html does not contain "さらに表示"
  	// expect(searchCapturesFromApiMock).toHaveBeenCalledWith({ q: "牛乳", mode: "keyword" })
  });
  it("renders 見つかりませんでした for an empty result", async () => {
  	// data: [] → html contains "見つかりませんでした", not 'aria-label="記録の一覧"'
  });
  it("redirects to /login when unauthenticated", async () => {
  	// { ok: false, error: { kind: "unauthenticated" } } → redirectMock toHaveBeenCalledWith("/login")
  });
  it("renders the API error message for other failures", async () => {
  	// 既存 capture-list-section.test.tsx の失敗ケースと同じ error を渡し、同じ表示を assert する
  	// html does not contain "見つかりませんでした"
  });
  ```
  `redirectMock` は例外を投げない mock なので、redirect の後続でクラッシュしないよう、実装は `redirect()` の後に `return` しなくてよい形(`redirect` の戻り値型は `never`)で既存 `CaptureListSection` と同じ構造にする。

- [ ] **Step 3: Run to verify they fail**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-form.test.tsx tests/capture-search-results-section.test.tsx`
  Expected: FAIL(module not found)

- [ ] **Step 4: Implement the three components**

  - `CaptureSearchForm`(server component、`"use client"` なし): `<form role="search" method="get" action="/captures">`。`<input type="search" name="q" maxLength={CAPTURE_SEARCH_MAX_LENGTH} defaultValue={defaultQuery} aria-label="記録を検索" placeholder="記録を検索">` は既存 `Input` を使い、枠は Thread `#D5E3D9`、面は Leaf `#F7FBF8`。方式は `<fieldset>` の中に radio 2 つ(`name="mode"`, `value="keyword"` / `"semantic"`, `defaultChecked` は `defaultMode` で決める)。ラベルは「キーワード」「意味」、`<legend className="sr-only">検索方法</legend>`。送信は既存 `Button` で「検索」。
  - `CaptureSearchResultsSection`: `CaptureListSection` と同じ構造。`searchCapturesFromApi({ q, mode })` → 失敗は `unauthenticated` なら `redirect("/login")`、他は `<ApiErrorMessage error={result.error} />`。0 件は `<CaptureSearchEmptyState />`。成功は `<CaptureList items={mapCaptureResponsesToListItemViews(result.data)} />`。
  - `CaptureSearchEmptyState`: `CaptureEmptyState` と同じ節の見た目(苔の点 + 文)で、見出しは「見つかりませんでした」、補助文は「言葉を変えるか、検索方法を切り替えてみてください。」(Dusk 色)。

- [ ] **Step 5: Run to verify they pass**

  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-form.test.tsx tests/capture-search-results-section.test.tsx`
  Expected: PASS

- [ ] **Step 6: Commit**

  ```bash
  git add apps/web/src/features/capture/capture-search-*.ts* apps/web/tests/capture-search-form.test.tsx apps/web/tests/capture-search-results-section.test.tsx
  git commit -m "feat(web): add the search form and result section"
  ```

---

### Task 4: page への組み込み

**Files:**
- Modify: `apps/web/src/features/capture/capture-page-frame.tsx`, `apps/web/src/app/captures/page.tsx`
- Test: `apps/web/tests/captures-page.test.tsx`(変更)、`apps/web/tests/capture-views.test.tsx` にフレームのテストがあれば合わせて更新

**Interfaces:**
- Consumes: Task 2 の `parseCaptureSearchParams`、Task 3 の `CaptureSearchForm` / `CaptureSearchResultsSection`
- Produces:
  - `CapturePageFrame` に `search: ReactNode` を追加(日付 `<header>` の直後、`children` の前)
  - `CapturePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> })`

- [ ] **Step 1: Write the failing page tests** in `tests/captures-page.test.tsx`

  既存の `vi.mock("@/features/capture/capture-list-section", ...)`(`timeline`)に並べて `vi.mock("@/features/capture/capture-search-results-section", () => ({ CaptureSearchResultsSection: ({ q, mode }) => <div>results:{q}:{mode}</div> }))` を足す。既存テストの呼び出しは `CapturePage({ searchParams: Promise.resolve({}) })` に直す。

  ```ts
  it("renders the search form and the timeline when there is no search", async () => {
  	// html contains 'role="search"', "timeline"; does not contain "results:"
  });
  it("renders the results instead of the timeline when q is given", async () => {
  	// searchParams: Promise.resolve({ q: "牛乳", mode: "semantic" })
  	// html contains "results:牛乳:semantic", 'value="牛乳"'; does not contain "timeline"
  });
  it("falls back to the timeline when q is blank", async () => {
  	// { q: "  " } → contains "timeline"
  });
  ```

- [ ] **Step 2: Run to verify it fails**

  Run: `corepack pnpm --filter web exec vitest run tests/captures-page.test.tsx`
  Expected: FAIL

- [ ] **Step 3: Implement**

  - `CapturePageFrame`: `search` を必須 prop にし、`<header>` の直下に `<div className="px-5 pb-2 sm:px-8">{search}</div>` を置く(コンポーザ領域は触らない)。
  - `CapturePage`: `await requireUser()` の後に `const search = parseCaptureSearchParams(await searchParams)`。`search` スロットに `<CaptureSearchForm defaultQuery={search?.q ?? ""} defaultMode={search?.mode ?? "keyword"} />`。`children` は、`search` があれば `<Suspense key={`${search.mode}:${search.q}`} fallback={<CaptureSearchPending />}><CaptureSearchResultsSection q={search.q} mode={search.mode} /></Suspense>`、なければ今の `<Suspense fallback={<CaptureListSkeleton />}><CaptureListSection /></Suspense>`。`CaptureSearchPending` は同ファイル内の小さな関数で、`<p role="status">検索しています</p>`(Dusk 色)を返す。`key` を付けるのは、検索語を変えたときに fallback を出し直すため。

- [ ] **Step 4: Run the full web gate**

  Run: `corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`
  Expected: すべて PASS(既存の `capture-views` などフレームを使うテストが `search` 必須化で落ちたら、その呼び出しに `search={null}` を足す)

- [ ] **Step 5: Manual check** (`docs/architecture/26-week8-search.md` の手動確認)

  API・worker・web を起動し、`牛乳を買う` を記録して `completed` を待つ。
  1. 検索欄に `牛乳` + キーワード → `牛乳を買う` の行が出る。行を押すと詳細へ行く
  2. `ミルク` + キーワード → 「見つかりませんでした」
  3. `ミルク` + 意味 → `牛乳を買う` が出る(fake embedder のとき、本文が完全一致の固定ベクトルだけ)
  4. 空のまま「検索」→ 今までの一覧に戻る
  5. 検索中に「検索しています」が一瞬出る(遅く見えなければ DevTools の Network throttling で確認)

  確認後、`git checkout apps/web/next-env.d.ts`(`next build` が書き換える)。

- [ ] **Step 6: Commit**

  ```bash
  git add apps/web/src/features/capture/capture-page-frame.tsx apps/web/src/app/captures/page.tsx apps/web/tests
  git commit -m "feat(web): search captures from the list screen"
  ```

---

## 判断メモ

- **URL 駆動にした理由:** Server Action + client state だと、検索中・0 件・エラー・一覧への復帰を `CaptureListPager` の state と両立させる必要がある。URL にすれば page が分岐するだけで、既存の server component とテスト方式(`renderToStaticMarkup`)をそのまま使え、リロードや戻るでも状態が保たれる。
- **`CaptureListPager` を使わない理由:** 検索結果は最大 20 件でカーソルが無く、`completed` だけなので polling も要らない。
- **`next/form` ではなく素の `<form>`:** 検索は頻度が低く、全画面遷移で足りる。client 遷移が欲しくなったら `Form` に差し替えるだけで済む。
- **意味検索の失敗:** embedding API が落ちたときの API 側の応答(5xx か)は未確認。画面側は `ApiErrorMessage` に任せ、検索欄は残るのでキーワードに切り替えて再検索できる。API 側の扱いは別途確認する。
- **このプランでやらないこと:** 検索結果の `scenario` 表示、結果のページング、日付や route の絞り込み(spec の「やらないこと」)。
