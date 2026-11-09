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
| `apps/web/src/lib/api/capture-search-mode.ts` (新規) | `CaptureSearchMode`。生成済み client の型から導く。`server-only` なし |
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

- Create: `apps/web/src/lib/api/capture-search-mode.ts`
- Modify: `apps/web/src/lib/api/capture.ts`
- Test: `apps/web/tests/capture-api.test.ts`

**Interfaces:**

- Consumes: `@hibi/api-client` の `searchCaptures`(`query: { q: string; mode?: "keyword" | "semantic" }`、200 は `{ data: CaptureResponse[] }`)
- Produces:
  - `type CaptureSearchMode = NonNullable<SearchCapturesData["query"]["mode"]>`(= `"keyword" | "semantic"`)を `@/lib/api/capture-search-mode` から export する。生成済み client の型から導き、web で union を二重定義しない。API の enum が変われば再生成で追従する。`server-only` を付けないので、どの層からも通常の `import` で読める
  - `searchCapturesFromApi(params: { q: string; mode: CaptureSearchMode }): Promise<ApiResult<CaptureResponse[]>>`

- [x] **Step 1: Write the failing tests** in `tests/capture-api.test.ts`
  このブロックはコメントではなく、そのまま貼って動くコード。先にこのファイルの `vi.mock("@hibi/api-client", ...)` に `searchCaptures: searchCapturesMock` を足す(`vi.hoisted` にも `searchCapturesMock` を足す)。足さないと `capture.ts` が import する `searchCaptures` が mock に無く、既存テストまで落ちる。
  import に `searchCapturesFromApi` を足し、ファイル末尾に追加する。
  ```ts
  describe("searchCapturesFromApi", () => {
  	beforeEach(() => {
  		vi.clearAllMocks();
  		getServerApiContextMock.mockResolvedValue({
  			ok: true,
  			baseUrl: "https://api.hibi.example",
  			accessToken: "access-token",
  		});
  	});

  	it("passes q and mode with the bearer token and unwraps the data array", async () => {
  		const capture = {
  			id: "capture-1",
  			rawText: "牛乳を買う",
  			status: "completed",
  			createdAt: "2026-10-04T09:00:00Z",
  			updatedAt: "2026-10-04T09:00:00Z",
  		};
  		searchCapturesMock.mockResolvedValue({ data: { data: [capture] } });

  		const result = await searchCapturesFromApi({ q: "牛乳", mode: "keyword" });

  		expect(searchCapturesMock).toHaveBeenCalledWith({
  			baseUrl: "https://api.hibi.example",
  			auth: "access-token",
  			query: { q: "牛乳", mode: "keyword" },
  		});
  		expect(result).toEqual({ ok: true, data: [capture] });
  	});

  	it("does not call the API without an authenticated context", async () => {
  		getServerApiContextMock.mockResolvedValue({
  			ok: false,
  			error: { kind: "unauthenticated", message: "Authentication is required." },
  		});

  		const result = await searchCapturesFromApi({ q: "牛乳", mode: "semantic" });

  		expect(searchCapturesMock).not.toHaveBeenCalled();
  		expect(result).toEqual({
  			ok: false,
  			error: { kind: "unauthenticated", message: "Authentication is required." },
  		});
  	});

  	it("returns a classified error when the API responds with a failure", async () => {
  		searchCapturesMock.mockResolvedValue({
  			error: { title: "Service Unavailable", status: 503 },
  			response: new Response(null, { status: 503 }),
  		});

  		const result = await searchCapturesFromApi({ q: "牛乳", mode: "keyword" });

  		expect(result.ok).toBe(false);
  	});
  });
  ```
- [x] **Step 2: Run to verify it fails**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-api.test.ts`
  Expected: FAIL(`searchCapturesFromApi` が export されていない)
- [x] **Step 3: Implement** `searchCapturesFromApi` in `src/lib/api/capture.ts`
  `getCaptureFromApi` と同じ形。`getServerApiContext()` が失敗ならそのまま返し、`searchCaptures({ baseUrl, auth, query: { q, mode } })` を呼び、`normalizeGeneratedResult` を通す(レスポンスは `{ data: [...] }` のエンベロープで meta が無いため、`listCapturesFromApi` の `normalizeGeneratedEnvelopeResult` ではない)。import に `searchCaptures` を足す。
  `capture-search-mode.ts` を新規に作り、`import type { SearchCapturesData } from "@hibi/api-client"` のうえで `export type CaptureSearchMode = NonNullable<SearchCapturesData["query"]["mode"]>` を定義する。`capture.ts` はそこから import して `searchCapturesFromApi` の `mode` 引数に使う。型を `capture.ts` に置かないのは、`capture.ts` が `server-only` で、型を読む側(params、form、results)に `import type` の縛りを持ち込むため。
- [x] **Step 4: Run to verify it passes**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-api.test.ts`
  Expected: PASS
- [x] **Step 5: Commit**
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

- Consumes: Task 1 の `CaptureSearchMode`(`@/lib/api/capture-search-mode`)
- Produces:
  - `type CaptureSearch = { q: string; mode: CaptureSearchMode }`
  - `const CAPTURE_SEARCH_MAX_LENGTH = 200`
  - `parseCaptureSearchParams(params: Record<string, string | string[] | undefined>): CaptureSearch | null`

- [x] **Step 1: Write the failing tests** (`import { parseCaptureSearchParams } from "@/features/capture/capture-search-params"`)
  ```ts
  import { describe, expect, it } from "vitest";

  import { parseCaptureSearchParams } from "@/features/capture/capture-search-params";

  describe("parseCaptureSearchParams", () => {
  	it("returns keyword mode by default", () => {
  		expect(parseCaptureSearchParams({ q: "牛乳" })).toEqual({
  			q: "牛乳",
  			mode: "keyword",
  		});
  	});

  	it("trims q and accepts semantic", () => {
  		expect(
  			parseCaptureSearchParams({ q: "  ミルク ", mode: "semantic" }),
  		).toEqual({ q: "ミルク", mode: "semantic" });
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
  		expect(parseCaptureSearchParams({ q: "牛乳", mode: "bogus" })?.mode).toBe(
  			"keyword",
  		);
  	});

  	it("uses the first value when a parameter is repeated", () => {
  		expect(
  			parseCaptureSearchParams({
  				q: ["牛乳", "記事"],
  				mode: ["semantic", "keyword"],
  			}),
  		).toEqual({ q: "牛乳", mode: "semantic" });
  	});
  });
  ```
- [x] **Step 2: Run to verify it fails**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-params.test.ts`
  Expected: FAIL(module not found)
- [x] **Step 3: Implement** `parseCaptureSearchParams` in `capture-search-params.ts`
  配列なら先頭を取り、`q` は `trim()` してから長さを見る(0 または 200 超は `null`)。`mode` は `"semantic"` のときだけ `semantic`、それ以外は `keyword`。長さは `Array.from(q).length` ではなく `q.length` でよい(API 側も Python の `len` = コードポイント数だが、サロゲートペアを含む 200 文字ちょうどの境界は実用上無視する)。
  型・定数・関数に次の JSDoc を付ける(日本語。Python 側の docstring と同じく全角括弧は使わない)。
  ```ts
  /** API の `q` の上限。サーバー側の検証(200 文字)と同じ値。 */
  export const CAPTURE_SEARCH_MAX_LENGTH = 200;

  /**
   * page の searchParams を、検索 API に渡せる形へ正規化する。
   *
   * 値が配列(`?q=a&q=b`)なら先頭を使う。`q` は前後の空白を除き、
   * 1 文字以上 CAPTURE_SEARCH_MAX_LENGTH 文字以下のときだけ有効とする。
   * `mode` は `"semantic"` のときだけ semantic、それ以外は keyword に倒す。
   * 不正な入力でも例外にはしない。
   *
   * @param params - `await searchParams` の結果。URL の生の値。
   * @returns 検索すべきなら `{ q, mode }`。`q` が無い、空白だけ、
   *   または長すぎるときは `null`(呼び出し側は通常の一覧を出す)。
   */
  ```
- [x] **Step 4: Run to verify it passes**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-params.test.ts`
  Expected: PASS
- [x] **Step 5: Commit**
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

- Consumes: Task 1 の `searchCapturesFromApi`、Task 2 の `CaptureSearch` / `CAPTURE_SEARCH_MAX_LENGTH`、Task 1 の `CaptureSearchMode`(`@/lib/api/capture-search-mode`)、既存の `mapCaptureResponsesToListItemViews`、`CaptureList`、`ApiErrorMessage`
- Produces:
  - `CaptureSearchForm({ defaultQuery, defaultMode }: { defaultQuery: string; defaultMode: CaptureSearchMode }): ReactNode`
  - `CaptureSearchResultsSection({ q, mode }: CaptureSearch): Promise<ReactNode>`
  - `CaptureSearchEmptyState(): ReactNode`

- [x] **Step 1: Write the failing form tests** (`renderToStaticMarkup(<CaptureSearchForm defaultQuery="" defaultMode="keyword" />)`)
  ```tsx
  import { renderToStaticMarkup } from "react-dom/server";
  import { describe, expect, it } from "vitest";

  import { CaptureSearchForm } from "@/features/capture/capture-search-form";

  describe("CaptureSearchForm", () => {
  	it("renders a GET search form to /captures", () => {
  		const html = renderToStaticMarkup(
  			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
  		);

  		expect(html).toContain('role="search"');
  		expect(html).toContain('method="get"');
  		expect(html).toContain('action="/captures"');
  	});

  	it("renders the query input limited to 200 characters", () => {
  		const html = renderToStaticMarkup(
  			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
  		);

  		expect(html).toContain('name="q"');
  		expect(html).toContain('maxLength="200"');
  		expect(html).toContain('aria-label="記録を検索"');
  	});

  	it("offers keyword and semantic modes and checks the default", () => {
  		const html = renderToStaticMarkup(
  			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
  		);

  		expect(html).toContain("キーワード");
  		expect(html).toContain("意味");
  		expect(html).toMatch(/<input[^>]*value="keyword"[^>]*checked/);
  		expect(html).not.toMatch(/<input[^>]*value="semantic"[^>]*checked/);
  	});

  	it("reflects the current search", () => {
  		const html = renderToStaticMarkup(
  			<CaptureSearchForm defaultQuery="牛乳" defaultMode="semantic" />,
  		);

  		expect(html).toContain('value="牛乳"');
  		expect(html).toMatch(/<input[^>]*value="semantic"[^>]*checked/);
  	});
  });
  ```
  radio の属性順は React の出力に依存する。正規表現が合わなければ、出力された HTML を見て `[^>]*` の並びだけを直す(検証内容は変えない)。
- [x] **Step 2: Write the failing results tests**
  mock は `capture-list-section.test.tsx` と同じ形(`vi.mock("server-only")`, `vi.mock("next/navigation", () => ({ redirect: redirectMock }))`, `vi.mock("@/lib/api/capture", () => ({ searchCapturesFromApi: searchCapturesFromApiMock }))`)。
  ```tsx
  import { renderToStaticMarkup } from "react-dom/server";
  import { beforeEach, describe, expect, it, vi } from "vitest";

  const { searchCapturesFromApiMock, redirectMock } = vi.hoisted(() => ({
  	searchCapturesFromApiMock: vi.fn(),
  	redirectMock: vi.fn(),
  }));

  vi.mock("server-only", () => ({}));
  vi.mock("next/navigation", () => ({ redirect: redirectMock }));
  vi.mock("@/lib/api/capture", () => ({
  	searchCapturesFromApi: searchCapturesFromApiMock,
  }));

  import { CaptureSearchResultsSection } from "@/features/capture/capture-search-results-section";

  describe("CaptureSearchResultsSection", () => {
  	beforeEach(() => {
  		vi.clearAllMocks();
  	});

  	it("renders hits with the same rows as the list and no pager", async () => {
  		searchCapturesFromApiMock.mockResolvedValue({
  			ok: true,
  			data: [
  				{
  					id: "capture-1",
  					rawText: "牛乳を買う",
  					status: "completed",
  					createdAt: "2026-10-02T05:02:00Z",
  					updatedAt: "2026-10-02T05:02:00Z",
  				},
  			],
  		});

  		const html = renderToStaticMarkup(
  			await CaptureSearchResultsSection({ q: "牛乳", mode: "keyword" }),
  		);

  		expect(searchCapturesFromApiMock).toHaveBeenCalledWith({
  			q: "牛乳",
  			mode: "keyword",
  		});
  		expect(html).toContain("牛乳を買う");
  		expect(html).toContain("14:02");
  		expect(html).toContain('href="/captures/capture-1"');
  		expect(html).toContain('aria-label="記録の一覧"');
  		expect(html).not.toContain("さらに表示");
  	});

  	it("renders 見つかりませんでした for an empty result", async () => {
  		searchCapturesFromApiMock.mockResolvedValue({ ok: true, data: [] });

  		const html = renderToStaticMarkup(
  			await CaptureSearchResultsSection({ q: "ミルク", mode: "keyword" }),
  		);

  		expect(html).toContain("見つかりませんでした");
  		expect(html).not.toContain('aria-label="記録の一覧"');
  	});

  	it("redirects to /login when unauthenticated", async () => {
  		searchCapturesFromApiMock.mockResolvedValue({
  			ok: false,
  			error: { kind: "unauthenticated", message: "Authentication is required." },
  		});
  		redirectMock.mockImplementation(() => {
  			throw new Error("NEXT_REDIRECT");
  		});

  		await expect(
  			CaptureSearchResultsSection({ q: "牛乳", mode: "keyword" }),
  		).rejects.toThrow("NEXT_REDIRECT");
  		expect(redirectMock).toHaveBeenCalledWith("/login");
  	});

  	it("renders the API error message for other failures", async () => {
  		searchCapturesFromApiMock.mockResolvedValue({
  			ok: false,
  			error: { kind: "network", message: "fetch failed" },
  		});

  		const html = renderToStaticMarkup(
  			await CaptureSearchResultsSection({ q: "ミルク", mode: "semantic" }),
  		);

  		expect(html).toContain("通信に失敗しました");
  		expect(html).not.toContain("見つかりませんでした");
  	});
  });
  ```
  redirect の mock は既存 `capture-list-section.test.tsx` と同じく例外を投げる。実装は `CaptureListSection` と同じ構造にする。
- [x] **Step 3: Run to verify they fail**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-form.test.tsx tests/capture-search-results-section.test.tsx`
  Expected: FAIL(module not found)
- [x] **Step 4: Implement the three components**
  - `CaptureSearchForm`(server component、`"use client"` なし): `<form role="search" method="get" action="/captures">`。`<input type="search" name="q" maxLength={CAPTURE_SEARCH_MAX_LENGTH} defaultValue={defaultQuery} aria-label="記録を検索" placeholder="記録を検索">` は既存 `Input` を使い、枠は Thread `#D5E3D9`、面は Leaf `#F7FBF8`。方式は `<fieldset>` の中に radio 2 つ(`name="mode"`, `value="keyword"` / `"semantic"`, `defaultChecked` は `defaultMode` で決める)。ラベルは「キーワード」「意味」、`<legend className="sr-only">検索方法</legend>`。送信は既存 `Button` で「検索」。
  - `CaptureSearchResultsSection`: `CaptureListSection` と同じ構造。`searchCapturesFromApi({ q, mode })` → 失敗は `unauthenticated` なら `redirect("/login")`、他は `<ApiErrorMessage error={result.error} />`。0 件は `<CaptureSearchEmptyState />`。成功は `<CaptureList items={mapCaptureResponsesToListItemViews(result.data)} />`。
  - `CaptureSearchEmptyState`: `CaptureEmptyState` と同じ節の見た目(苔の点 + 文)で、見出しは「見つかりませんでした」、補助文は「言葉を変えるか、検索方法を切り替えてみてください。」(Dusk 色)。
- [x] **Step 5: Run to verify they pass**
  Run: `corepack pnpm --filter web exec vitest run tests/capture-search-form.test.tsx tests/capture-search-results-section.test.tsx`
  Expected: PASS
- [x] **Step 6: Commit**
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

- [x] **Step 1: Write the failing page tests** in `tests/captures-page.test.tsx`
  既存の `vi.mock("@/features/capture/capture-list-section", ...)`(`timeline`)に並べて `vi.mock("@/features/capture/capture-search-results-section", () => ({ CaptureSearchResultsSection: ({ q, mode }) => <div>results:{q}:{mode}</div> }))` を足す。既存テストの `CapturePage()` 呼び出しも `CapturePage({ searchParams: Promise.resolve({}) })` に直す。
  mock の追加は次の形。
  ```tsx
  vi.mock("@/features/capture/capture-search-results-section", () => ({
  	CaptureSearchResultsSection: ({ q, mode }: { q: string; mode: string }) => (
  		<div>results:{q}:{mode}</div>
  	),
  }));
  ```
  ```tsx
  it("renders the search form and the timeline when there is no search", async () => {
  	const html = renderToStaticMarkup(
  		await CapturePage({ searchParams: Promise.resolve({}) }),
  	);

  	expect(html).toContain('role="search"');
  	expect(html).toContain("timeline");
  	expect(html).not.toContain("results:");
  });

  it("renders the results instead of the timeline when q is given", async () => {
  	const html = renderToStaticMarkup(
  		await CapturePage({
  			searchParams: Promise.resolve({ q: "牛乳", mode: "semantic" }),
  		}),
  	);

  	expect(html).toContain("results:牛乳:semantic");
  	expect(html).toContain('value="牛乳"');
  	expect(html).not.toContain("timeline");
  });

  it("falls back to the timeline when q is blank", async () => {
  	const html = renderToStaticMarkup(
  		await CapturePage({ searchParams: Promise.resolve({ q: "  " }) }),
  	);

  	expect(html).toContain("timeline");
  	expect(html).not.toContain("results:");
  });
  ```
  `capture-views.test.tsx` の `keeps the composer in a distinct bottom region` は `CapturePageFrame` に `search={<div>search</div>}` を足し、`expect(html).toContain("search")` を加える。
- [x] **Step 2: Run to verify it fails**
  Run: `corepack pnpm --filter web exec vitest run tests/captures-page.test.tsx`
  Expected: FAIL
- [x] **Step 3: Implement**
  - `CapturePageFrame`: `search` を必須 prop にし、`<header>` の直下に `<div className="px-5 pb-2 sm:px-8">{search}</div>` を置く(コンポーザ領域は触らない)。
  - `CapturePage`: `await requireUser()` の後に `const search = parseCaptureSearchParams(await searchParams)`。`search` スロットに `<CaptureSearchForm defaultQuery={search?.q ?? ""} defaultMode={search?.mode ?? "keyword"} />`。`children` は、`search` があれば `<Suspense key={`${search.mode}:${search.q}`} fallback={<CaptureSearchPending />}><CaptureSearchResultsSection q={search.q} mode={search.mode} /></Suspense>`、なければ今の `<Suspense fallback={<CaptureListSkeleton />}><CaptureListSection /></Suspense>`。`CaptureSearchPending` は同ファイル内の小さな関数で、`<p role="status">検索しています</p>`(Dusk 色)を返す。`key` を付けるのは、検索語を変えたときに fallback を出し直すため。
- [x] **Step 4: Run the full web gate**
  Run: `corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`
  Expected: すべて PASS
- [x] **Step 5: Manual check** (`docs/architecture/26-week8-search.md` の手動確認)
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
- `CaptureListPager` **を使わない理由:** 検索結果は最大 20 件でカーソルが無く、`completed` だけなので polling も要らない。
- `next/form` **ではなく素の** `<form>`**:** 検索は頻度が低く、全画面遷移で足りる。client 遷移が欲しくなったら `Form` に差し替えるだけで済む。
- **意味検索の失敗:** embedding API が落ちたときの API 側の応答(5xx か)は未確認。画面側は `ApiErrorMessage` に任せ、検索欄は残るのでキーワードに切り替えて再検索できる。API 側の扱いは別途確認する。
- **このプランでやらないこと:** 検索結果の `scenario` 表示、結果のページング、日付や route の絞り込み(spec の「やらないこと」)。
