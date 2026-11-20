# Week 10 朝ダイジェスト・週次レビュー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ユーザーの timezone の朝 7 時に、daily のダイジェストと、月曜の週次レビューを、冪等に作り、API と画面で読めるようにする。失敗した行の再実行と、止まった処理の回復を整備する。

**Architecture:** 作る時刻の判定と中身の組み立ては、時計を引数で受ける純粋関数に置く。cron は 15 分ごとに、足りない期間の `pending` の行を、`ON CONFLICT DO NOTHING` で 1 件だけ作り、outbox 経由で job に渡す。job は `pending` のときだけ中身を作り、`ready` か `failed` にする。週次の要約だけ LLM を使う。

**Tech Stack:** FastAPI + SQLAlchemy 2 async, arq(cron と job), Python 3.14(`zoneinfo`)、Supabase migration、OpenAI SDK、Next.js 16、vitest。

**Spec:** `docs/architecture/28-week10-digest-and-review.md`

## Global Constraints

- 作る時刻は、ユーザーの現地時刻の 7 時(`DIGEST_HOUR = 7`)以降。daily はその日、weekly は月曜だけ。止まっていても前の日の分は作らない
- 日付の境界は暦日の加算で決める。24 時間を足さない。不正な timezone 名は `UTC`(`hibi.core.timezone.zone_for`)
- 冪等の正本は `app.digest_reports` の `unique (user_id, kind, period_start)`。arq の `_job_id` は補助
- job の引数は `report_id` だけ。`max_tries = 3`。3 回目の失敗で `failed`
- daily の `items` は Week 9 の `rank_today` を、そのまま呼んで求める。優先度の計算は変えない
- LLM に渡すのは、集計と完了にしたシナリオの title だけ。本文(`raw_text`)は送らない。LLM の prompt には、`json_object` モードの条件として、`JSON` の語を入れる
- 週次の要約は 500 文字以内。不正な出力は再試行せず、定型文で `ready`。Capture が無い週は LLM を呼ばない
- 通常の pytest は LLM を呼ばない。`HIBI_OPEN_AI_API_KEY` が空なら fake を使う
- docstring は日本語の Google style(全角括弧を使わない)。router と schema は `Args:` と `Returns:` を付けない(CLAUDE.md)。TypeScript は JSDoc
- 新しい path は、`/{id}` より前に静的な path を登録する。`Query` の既定値は `Annotated[int, Query(...)] = ...`(ruff B008)
- 検証は `uv run --project apps/api pytest apps/api/tests -m 'not integration'`、`ruff check`、`ruff format --check`、`ty check apps/api/src`、`corepack pnpm typecheck|lint|test|build`。`format:check` は設定が無く既知の失敗のため使わない
- 実装の Step 3 は、layer ごとに、メソッド名と概要を箇条書きで書く(このプランの形式)

## Review Focus

1. 夏時間の日(`America/New_York` の 2026-03-08 と 2026-11-01)に、現地の 7 時を過ぎてからだけ作る → Task 1
2. 月曜より前、月曜の 7 時前、火曜以降は weekly を作らない。月曜は先週(月〜日)の月曜を指す → Task 1
3. cron を 2 回続けて、または同時に 2 つ実行しても、行が 1 件のまま、outbox も 1 件 → Task 3
4. Capture が無い週は LLM を呼ばず、定型の要約で `ready` → Task 5
5. `failed` の retry は、所有者だけができ、`failed` 以外は 409、他人の行は 404 → Task 6
6. `processing` のまま止まった Capture を回復しても、古い世代の job は何も変えない → Task 7
7. capture を削除したとき、その outbox 行が残らない(outbox の FK を外すため) → Task 3

## File Structure

| ファイル | 責務 |
| --- | --- |
| `apps/api/src/hibi/modules/digests/schedule.py` (新規) | 作る時刻の判定。純粋関数 |
| `apps/api/src/hibi/modules/digests/content.py` (新規) | daily の内容と、週次の集計の組み立て。純粋関数 |
| `apps/api/src/hibi/modules/digests/{types,models,repository,service,schemas,router}.py` (新規) | ダイジェストの永続化、生成、API |
| `apps/api/src/hibi/ai/review_summary.py`、`fake_review_summary.py`、`llm_review_summary.py` (新規) | 週次の要約の port、fake、実 adapter |
| `apps/api/src/hibi/jobs/run_daily_digest.py`、`generate_digest_report_job.py`、`recover_stalled_work.py` (新規) | cron と job |
| `apps/api/src/hibi/jobs/main.py`、`relay_outbox_events.py` (変更) | cron の登録、outbox の配送先を種類で分ける |
| `apps/api/src/hibi/modules/captures/repository.py` (変更) | 止まった `processing` の回復、`updated_at` の更新 |
| `supabase/migrations/<ts>_digest_reports.sql` (新規) | `digest_reports` と、outbox の check と FK |
| `apps/web/src/lib/api/digest.ts`、`apps/web/src/features/digest/*`、`apps/web/src/app/captures/digest/page.tsx` (新規) | ダイジェストの画面 |

---

### Task 1: 作る時刻の判定(純粋関数)

**Files:**

- Create: `apps/api/src/hibi/modules/digests/schedule.py`
- Test: `apps/api/tests/test_digest_schedule.py`

**Interfaces:**

- Consumes: `hibi.core.timezone.to_local(now: datetime, *, timezone: str) -> datetime`
- Produces:
  - `DIGEST_HOUR = 7`
  - `daily_period_start(now: datetime, *, timezone: str) -> date | None` — 現地時刻が 7 時以降なら、その日の暦日。前なら None
  - `weekly_period_start(now: datetime, *, timezone: str) -> date | None` — 月曜の 7 時以降なら、先週の月曜。それ以外は None
  - (`local_day_start` と `to_local` は `hibi.core.timezone` にある。Week 9 の `local_day_end` と重複していたため、共有の場所に置いた)

- [x] **Step 1: Write the failing tests** in `tests/test_digest_schedule.py`

```python
from datetime import UTC, date, datetime

import pytest

from hibi.modules.digests.schedule import (
    daily_period_start,
    weekly_period_start,
)

JST = "Asia/Tokyo"
NY = "America/New_York"


@pytest.mark.parametrize(
    ("now", "timezone", "expected"),
    [
        # JST 06:59 と 07:00
        (datetime(2026, 11, 10, 21, 59, tzinfo=UTC), JST, None),
        (datetime(2026, 11, 10, 22, 0, tzinfo=UTC), JST, date(2026, 11, 11)),
        # 夏時間の開始日(23 時間の日)。EDT の 07:00 は 11:00 UTC
        (datetime(2026, 3, 8, 10, 59, tzinfo=UTC), NY, None),
        (datetime(2026, 3, 8, 11, 0, tzinfo=UTC), NY, date(2026, 3, 8)),
        # 夏時間の終了日(25 時間の日)。EST の 07:00 は 12:00 UTC
        (datetime(2026, 11, 1, 11, 59, tzinfo=UTC), NY, None),
        (datetime(2026, 11, 1, 12, 0, tzinfo=UTC), NY, date(2026, 11, 1)),
        # 不正な名前は UTC として扱う
        (datetime(2026, 11, 10, 7, 0, tzinfo=UTC), "Not/AZone", date(2026, 11, 10)),
    ],
)
def test_daily_period_start(now: datetime, timezone: str, expected: date | None) -> None:
    assert daily_period_start(now, timezone=timezone) == expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # 2026-11-09 は月曜。JST 06:59 と 07:00
        (datetime(2026, 11, 8, 21, 59, tzinfo=UTC), None),
        (datetime(2026, 11, 8, 22, 0, tzinfo=UTC), date(2026, 11, 2)),
        # 月曜の夜でも、その日のうちは作る
        (datetime(2026, 11, 9, 14, 0, tzinfo=UTC), date(2026, 11, 2)),
        # 火曜以降は作らない
        (datetime(2026, 11, 9, 22, 0, tzinfo=UTC), None),
        (datetime(2026, 11, 13, 0, 0, tzinfo=UTC), None),
    ],
)
def test_weekly_period_start(now: datetime, expected: date | None) -> None:
    assert weekly_period_start(now, timezone=JST) == expected


def test_weekly_period_start_uses_the_local_weekday() -> None:
    # UTC では日曜 23:00 だが、JST では月曜 08:00
    assert weekly_period_start(datetime(2026, 11, 8, 23, 0, tzinfo=UTC), timezone=JST) == date(
        2026, 11, 2
    )
```

- [x] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_schedule.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.modules.digests.schedule`)

- [x] **Step 3: Implement**

**domain**(`modules/digests/schedule.py`、純粋関数。時計と timezone は引数で受ける)

- `daily_period_start(now, *, timezone)`: `now` をユーザーの timezone に直し、時が `DIGEST_HOUR` 以降ならその暦日を、前なら None を返す
- `weekly_period_start(now, *, timezone)`: 現地の曜日が月曜で、時が 7 時以降なら、`今日 - 7 日` の暦日(先週の月曜)を返す。それ以外は None。日の引き算は `date` で行う
- `to_local(now, *, timezone)`(`core/timezone.py`): `now` を現地時刻に直す。Task 1 より前に、Week 9 の `local_day_end` と共有する形で `core/timezone.py` に置く
- `DIGEST_HOUR`: 7

docstring は、3 つとも日本語の Google style で付ける。

- [x] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_schedule.py -v` と `ruff check`、`ty check apps/api/src`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add apps/api/src/hibi/modules/digests/schedule.py apps/api/tests/test_digest_schedule.py
git commit -m "feat(digests): decide when a digest is due in the user timezone"
```

---

### Task 2: daily の内容と、週次の集計(純粋関数)

**Files:**

- Create: `apps/api/src/hibi/modules/digests/content.py`
- Test: `apps/api/tests/test_digest_content.py`

**Interfaces:**

- Consumes: Week 9 の `TodayCandidate`、`local_day_end(now, *, timezone)`、`rank_today(...)`
- Produces:
  - `@dataclass(frozen=True, slots=True) class DigestItem: capture_id: UUID; title: str; due_at: datetime | None`
  - `@dataclass(frozen=True, slots=True) class DeadlineCounts: overdue_count: int; due_today_count: int`
  - `count_deadlines(candidates: Sequence[TodayCandidate], *, now: datetime, timezone: str) -> DeadlineCounts`
  - `build_daily_content(*, items: Sequence[DigestItem], deadline_counts: DeadlineCounts, done_yesterday_count: int) -> dict[str, object]`
  - `DAILY_ITEM_LIMIT = 5`、`DAILY_CONTENT_VERSION = "daily-digest-v1"`

- [x] **Step 1: Write the failing tests** in `tests/test_digest_content.py`

```python
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from hibi.modules.captures.today import TodayCandidate
from hibi.modules.digests.content import (
    DeadlineCounts,
    DigestItem,
    build_daily_content,
    count_deadlines,
)

NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 15:00 JST
JST = "Asia/Tokyo"


def _candidate(n: int, due: datetime | None) -> TodayCandidate:
    return TodayCandidate(
        capture_id=UUID(int=n), urgency_score=Decimal("0.50"), due_at=due, created_at=NOW
    )


def test_count_deadlines_separates_overdue_from_due_today() -> None:
    candidates = [
        _candidate(1, datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),  # 超過
        _candidate(2, datetime(2026, 11, 10, 11, 0, tzinfo=UTC)),  # 今日
        _candidate(3, datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),  # 明日は数えない
        _candidate(4, None),  # 期限なしは数えない
    ]
    assert count_deadlines(candidates, now=NOW, timezone=JST) == DeadlineCounts(
        overdue_count=1, due_today_count=1
    )


def test_build_daily_content_uses_camel_case_keys_and_iso_times() -> None:
    items = [
        DigestItem(UUID(int=1), "起こして", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
        DigestItem(UUID(int=2), "牛乳", None),
    ]
    content = build_daily_content(
        items=items, deadline_counts=DeadlineCounts(1, 2), done_yesterday_count=3
    )
    assert content == {
        "items": [
            {"captureId": str(UUID(int=1)), "title": "起こして", "dueAt": "2026-11-11T00:00:00Z"},
            {"captureId": str(UUID(int=2)), "title": "牛乳", "dueAt": None},
        ],
        "overdueCount": 1,
        "dueTodayCount": 2,
        "doneYesterdayCount": 3,
    }


def test_build_daily_content_for_no_items_is_still_valid() -> None:
    content = build_daily_content(
        items=[], deadline_counts=DeadlineCounts(0, 0), done_yesterday_count=0
    )
    assert content["items"] == []
```

- [x] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_content.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.modules.digests.content`)

- [x] **Step 3: Implement**

**domain**(`modules/digests/content.py`、純粋関数)

- `DigestItem`(dataclass): `capture_id`、`title`、`due_at`。daily の 1 行
- `DeadlineCounts`(dataclass): `overdue_count`、`due_today_count`
- `count_deadlines(candidates, *, now, timezone)`: 期限が `now` より前なら超過、`now` 以降で `local_day_end` より前なら今日が期限として数える。期限なしと明日以降は数えない
- `build_daily_content(*, items, deadline_counts, done_yesterday_count)`: JSON に保存できる辞書にする。キーは camelCase、時刻は UTC の ISO 8601(`Z` 表記)。空の `items` も正常
- `DAILY_ITEM_LIMIT`(5)、`DAILY_CONTENT_VERSION`(`daily-digest-v1`): 定数

docstring は、日本語の Google style。

- [x] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_content.py -v` と `ruff check`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add apps/api/src/hibi/modules/digests/content.py apps/api/tests/test_digest_content.py
git commit -m "feat(digests): build the daily digest content from today candidates"
```

---

### Task 3: digest_reports の永続化と、冪等な claim

**Files:**

- Create: `supabase/migrations/<timestamp>_digest_reports.sql`、`apps/api/src/hibi/modules/digests/{types,models,repository}.py`
- Modify: `apps/api/src/hibi/modules/captures/{models,types,repository}.py`、`apps/api/src/hibi/jobs/relay_outbox_events.py`、`apps/api/src/hibi/jobs/job_logging.py`
- Test: `apps/api/tests/integration/test_digest_repository.py`(新規)、`apps/api/tests/integration/test_capture_repository.py`、`apps/api/tests/test_relay_outbox_events.py`

**Interfaces:**

- Produces:
  - `DigestReport`(`types.py`、dataclass): `id`、`user_id`、`kind`、`period_start`、`timezone`、`status`、`content`、`content_version`、`summary_model`、`error_code`、`generated_at`、`created_at`、`updated_at`
  - 定数: `DIGEST_KIND_DAILY`、`DIGEST_KIND_WEEKLY`、`DIGEST_STATUS_PENDING`、`DIGEST_STATUS_READY`、`DIGEST_STATUS_FAILED`、`DIGEST_AGGREGATE_TYPE = "digest_report"`、`DIGEST_GENERATION_REQUESTED = "digest_report.generation_requested"`
  - `OutboxEvent` に `aggregate_type: str` を足す
  - `DigestRepository.claim_report(*, report_id, user_id, kind, period_start, timezone, content_version, outbox_id) -> bool` — 行を入れた処理だけ True
  - `DigestRepository.get_report(report_id) -> DigestReport | None`
  - `DigestRepository.complete_report(report_id, *, content, summary_model) -> bool`、`fail_report(report_id, *, error_code) -> bool` — どちらも `pending` のときだけ更新する

- [x] **Step 1:** Write the failing tests

`tests/integration/test_digest_repository.py`(`integration`。`session` fixture は `test_profile_repository.py` と同じ形で用意する)

```python
@pytest.mark.integration
async def test_claim_report_inserts_one_row_and_one_outbox_event(session) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    kwargs = dict(user_id=user_id, kind="daily", period_start=date(2026, 11, 10),
                  timezone="Asia/Tokyo", content_version="daily-digest-v1")

    first = await repo.claim_report(report_id=uuid7(), outbox_id=uuid7(), **kwargs)
    second = await repo.claim_report(report_id=uuid7(), outbox_id=uuid7(), **kwargs)

    assert (first, second) == (True, False)
    assert await _count(session, "app.digest_reports", user_id) == 1
    assert await _count(session, "app.outbox_events", user_id) == 1   # 2 回目は outbox も足さない


@pytest.mark.integration
async def test_complete_and_fail_only_update_a_pending_report(session) -> None: ...
    # complete → ready、generated_at が入る。もう一度 complete は False。fail は ready に対して False


@pytest.mark.integration
async def test_claim_report_rejects_an_unknown_kind(session) -> None: ...   # check 制約で IntegrityError
```

`tests/integration/test_capture_repository.py` に追加する。

```python
@pytest.mark.integration
async def test_delete_capture_also_deletes_its_outbox_events(session) -> None:
    # create_capture は outbox を 1 行作る。delete_capture のあと、aggregate_id の outbox 行が 0 件
```

`tests/test_relay_outbox_events.py` に追加する。

```python
@pytest.mark.asyncio
async def test_relay_enqueues_a_digest_event_with_only_the_report_id() -> None:
    # aggregate_type="digest_report" の event → enqueue_job("generate_digest_report_job", aggregate_id, _job_id=...)
    # aggregate_type="capture" の event は従来どおり (aggregate_id, processing_generation)
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_relay_outbox_events.py -v` と `supabase db reset` 後に integration
Expected: FAIL(`DigestRepository` が無い、relay が種類を区別しない)

- [x] **Step 3: Implement**

**migration**(`supabase/migrations/<timestamp>_digest_reports.sql`)

- `app.digest_reports`: 列と check は方針文書の「契約」のとおり。`unique (user_id, kind, period_start)`、index `(user_id, kind, period_start desc)`。権限は `app.captures` と同じ
- `app.outbox_events`: `aggregate_id → app.captures(id)` の FK を外す(`ON DELETE CASCADE` が効かなくなるので、削除は repository が行う)。`ck_outbox_events__aggregate_type` と `ck_outbox_events__event_type` を、digest の値を許す形に作り直す
- 方針文書の「契約」に、outbox の FK を外すことを 1 行足す

**model / types**

- `digests/models.py`: `DigestReportModel`(`app.digest_reports`)
- `captures/models.py`: `OutboxModel` の `aggregate_type`、`event_type` の既定は capture のまま
- `captures/types.py`: `OutboxEvent.aggregate_type`

**repository**

- `DigestRepository.claim_report(...)`: `INSERT ... ON CONFLICT (user_id, kind, period_start) DO NOTHING RETURNING id`。行が入ったときだけ、同じ transaction で outbox(`digest_report`、`aggregate_id = report_id`)を足して True
- `DigestRepository.get_report(report_id)`: 所有者を問わず読む(Worker 用)
- `DigestRepository.complete_report(...)`、`fail_report(...)`: `status = 'pending'` を条件にした UPDATE。`complete` は `generated_at` を入れ、`content` と `summary_model` を保存する
- `CaptureRepository.list_pending_outbox_events`: `aggregate_type` も返す。`_to_outbox_event` を直す
- `CaptureRepository.delete_capture`: 削除の前に、`aggregate_type = 'capture'` と `aggregate_id` が一致する outbox を消す

**job**

- `relay_outbox_events`: `aggregate_type` が `digest_report` なら `enqueue_job("generate_digest_report_job", aggregate_id, _job_id=f"outbox:{event.id}")`、それ以外は従来どおり
- `log_outbox_enqueue_failure`: `target_job` を引数で受ける

- [x] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q`、`supabase db reset` 後に `pytest apps/api/tests/integration -m integration`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add supabase/migrations apps/api/src apps/api/tests
git commit -m "feat(digests): claim one digest report per user, kind and period"
```

---

### Task 4: daily の生成と cron

**Files:**

- Create: `apps/api/src/hibi/modules/digests/service.py`、`apps/api/src/hibi/jobs/run_daily_digest.py`、`apps/api/src/hibi/jobs/generate_digest_report_job.py`
- Modify: `apps/api/src/hibi/modules/digests/repository.py`、`apps/api/src/hibi/jobs/main.py`
- Test: `apps/api/tests/test_digest_service.py`(新規)、`apps/api/tests/test_run_daily_digest.py`(新規)、`apps/api/tests/test_generate_digest_report_job.py`(新規)、`apps/api/tests/test_worker_settings.py`

**Interfaces:**

- Consumes: Task 1 の `daily_period_start`、`weekly_period_start`、Task 2 の `build_daily_content` ほか、Task 3 の `claim_report` ほか、Week 9 の `rank_today`
- Produces:
  - `ActiveUser(user_id: UUID, timezone: str)`(`types.py`)
  - `DigestRepository.list_active_users(*, active_since: datetime, limit: int) -> list[ActiveUser]`
  - `DigestRepository.count_done_between(user_id, *, start, end) -> int` — `done_at` が `[start, end)` のシナリオの数
  - `DIGEST_GENERATION_MAX_ATTEMPTS = 3`(`types.py`)
  - `DigestService(digests: DigestRepository, captures: CaptureRepository, *, clock=_utc_now)` — `session` は持たない(commit は job の `session_scope`)。`summarizer: ReviewSummarizer` は Task 5 で足す
  - `DigestService.schedule_due_reports() -> int` — 新しく claim した行の数
  - `DigestService.generate_report(report_id: UUID) -> None`
  - `run_daily_digest(ctx) -> None`(cron)、`generate_digest_report_job(ctx, report_id) -> None`(arq entry)

- [x] **Step 1: Write the failing tests**

`tests/test_digest_service.py`(17 件。`FakeDigestRepository` と `FakeCaptureRepository`。`clock=lambda: now` を渡す)

```python
# schedule_due_reports
async def test_schedule_claims_daily_only_after_seven_in_the_user_timezone() -> None:
    # JST と America/New_York の利用者。22:00 UTC → 東京は翌日 07:00、NY は 17:00 で、どちらも daily が due
async def test_schedule_skips_a_user_before_seven_in_the_user_timezone() -> None: ...   # 21:59 UTC → 東京は 06:59 で対象外
async def test_schedule_does_not_claim_weekly_on_a_tuesday() -> None: ...
async def test_schedule_claims_weekly_on_monday_with_last_monday_as_the_period() -> None:
    # 2026-11-09 00:00 UTC(東京の月曜 09:00)→ daily 11-09 と weekly 11-02(content_version は weekly-review-v1)
async def test_schedule_claims_nothing_on_monday_before_seven() -> None: ...
async def test_schedule_counts_only_the_reports_that_were_newly_claimed() -> None: ...   # claim が False の行は数えない
async def test_schedule_reads_only_users_active_in_the_last_14_days() -> None: ...       # active_since == now - 14 日
async def test_schedule_issues_distinct_ids_for_each_report_and_outbox_event() -> None: ...

# generate_report
async def test_generate_daily_report_completes_with_ranked_items() -> None:
    # 候補 3 件(期限なし、超過、今日)→ items が [超過, 今日, 期限なし]、dueAt は Z 表記、
    # overdueCount=1、dueTodayCount=1、doneYesterdayCount は count_done_between の結果、summary_model は None
async def test_generate_daily_report_never_puts_the_raw_text_in_the_content() -> None: ...
async def test_generate_daily_report_limits_the_items_to_five() -> None: ...
async def test_generate_daily_report_counts_yesterday_in_the_report_timezone() -> None:
    # period_start=11-10、Asia/Tokyo → count_done_between(start=11-09 00:00 JST, end=11-10 00:00 JST)
async def test_generate_daily_report_without_candidates_completes_with_an_empty_digest() -> None: ...   # captures を読まない
async def test_generate_report_does_nothing_unless_pending(status) -> None: ...   # ready と failed
async def test_generate_report_does_nothing_for_a_missing_report() -> None: ...
```

`tests/test_run_daily_digest.py`(2 件。`session_scope`、`DigestRepository`、`CaptureRepository`、`DigestService` を monkeypatch する)

```python
async def test_run_daily_digest_commits_the_schedule_in_one_session() -> None: ...
async def test_run_daily_digest_rolls_back_and_raises_when_the_schedule_fails() -> None: ...   # cron は max_tries=1
```

`tests/test_generate_digest_report_job.py`(5 件。`DigestRepository` の fake が、`fail_report` を呼んだ session を記録する)

```python
async def test_job_commits_a_successful_generation() -> None: ...
async def test_job_schedules_a_retry_before_the_final_attempt(attempt) -> None: ...   # job_try=1、2 → Retry、failed にしない
async def test_job_marks_failed_on_the_final_attempt_in_a_separate_session() -> None:
    # job_try=3 → 別 session で fail_report、例外を再送出。error_code は理由の種類だけで、例外のメッセージを含まない
async def test_job_does_nothing_after_the_final_attempt() -> None: ...   # job_try=4
```

`tests/test_worker_settings.py`(関数と cron が 2 つずつになるので、名前と coroutine で探す形に書き換える)

```python
def test_worker_registers_the_digest_job_and_the_daily_digest_cron() -> None:
    # generate_digest_report_job(max_tries=3)、run_daily_digest(minute={0,15,30,45}、second=0、unique=True、max_tries=1)
```

- [x] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_service.py apps/api/tests/test_run_daily_digest.py apps/api/tests/test_generate_digest_report_job.py apps/api/tests/test_worker_settings.py -v`
Expected: FAIL(module not found)

- [x] **Step 3: Implement**

**repository**(`digests/repository.py`、`captures/repository.py`)

- `DigestRepository.list_active_users(*, active_since, limit)`: 直近に Capture がある `user_id` と、`profiles.timezone` を返す。`limit` 件まで
- `DigestRepository.count_done_between(user_id, *, start, end)`: `done_at` が `[start, end)` のシナリオの数
- `CaptureRepository.list_open_scenario_candidates` と `list_captures_by_ids`: Week 9 のものを、変更せずに使う。候補は `rank_today`(`items`)と `count_deadlines`(期限の件数)に渡し、title と期限は `list_captures_by_ids` の `scenario` から読む。期限の絞り込みを SQL に足さない(`overdueCount` が崩れる)。docstring だけ、Today とダイジェストの両方が読むことを書く

**service**(`digests/service.py`)

- `DigestService.schedule_due_reports()`: `list_active_users`(直近 14 日)を読み、ユーザーごとに `daily_period_start` と `weekly_period_start` を求め、due なものだけ `claim_report` する。新しく claim した数を返す
- `DigestService.generate_report(report_id)`: 行を読み、`pending` でなければ何もしない。daily なら、`rank_today`(`DAILY_ITEM_LIMIT` 件)と `count_deadlines`、前日の完了数から `build_daily_content` を作り、`complete_report` する。weekly は Task 5
- `_utc_now()`: 現在時刻を UTC の aware な `datetime` で返す

**job**

- `run_daily_digest(ctx)`(`jobs/run_daily_digest.py`): `session_scope` で `DigestService.schedule_due_reports` を呼ぶ。cron の本体
- `generate_digest_report_job(ctx, report_id)`(`jobs/generate_digest_report_job.py`): `process_capture_job` と同じ形。引数は `report_id` だけ。`job_try` で試行を数え、最終試行の失敗では、別の session で `fail_report` してから例外を再送出する。`error_code` は理由の種類(例外のクラス名など)だけで、例外のメッセージは入れない。最終試行より後(`job_try` が `DIGEST_GENERATION_MAX_ATTEMPTS` を超える)は、何もしない。再試行の待ち時間は `process_capture_job` と同じ指数バックオフで、共有するときは private 名を import せず `job_logging.py` などへ移す
- `WorkerSettings`(`jobs/main.py`): `generate_digest_report_job` を `max_tries=3` で登録し、`cron(run_daily_digest, minute={0, 15, 30, 45}, second=0, unique=True, max_tries=1)` を足す

- [x] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add apps/api/src apps/api/tests
git commit -m "feat(digests): generate the daily digest from a quarter-hour cron"
```

---

### Task 5: 週次レビューと LLM の要約

**Files:**

- Create: `apps/api/src/hibi/ai/review_summary.py`、`fake_review_summary.py`、`llm_review_summary.py`
- Modify: `apps/api/src/hibi/ai/classifier_factory.py`、`apps/api/src/hibi/modules/digests/{content,repository,service}.py`、`apps/api/src/hibi/jobs/{run_daily_digest,generate_digest_report_job}.py`
- Test: `apps/api/tests/test_digest_weekly.py`(新規)、`apps/api/tests/test_llm_review_summary.py`(新規)、`apps/api/tests/test_fake_review_summary.py`(新規)、`apps/api/tests/digest_helpers.py`(新規)、`apps/api/tests/test_digest_content.py`、`apps/api/tests/test_classifier_factory.py`、`apps/api/tests/integration/test_digest_repository.py`、Task 4 の `test_digest_service.py`、`test_run_daily_digest.py`、`test_generate_digest_report_job.py`

**Interfaces:**

- Consumes: Task 4 の `DigestService`、`count_done_between`、`count_deadlines`、`list_open_scenario_candidates`
- Produces:
  - `WeeklyStats(captured_count: int, done_count: int, open_count: int, overdue_count: int)`(`content.py`)
  - `WeeklyReviewInput(stats: WeeklyStats, done_titles: Sequence[str])`(`review_summary.py`)。本文を持たない
  - `ReviewSummarizer`(port): `model_name: str`、`summarize_week(review: WeeklyReviewInput) -> str`。service は `model_name` を `summary_model` に記録する
  - `ReviewProviderError`、`REVIEW_SUMMARY_MODEL_FAKE`(`review_summary.py`)
  - `FakeReviewSummarizer`、`LlmReviewSummarizer(client: ReviewModelClient | None = None)`、`SdkReviewClient.complete_json(*, review: WeeklyReviewInput) -> str`、`build_review_summarizer() -> ReviewSummarizer`
  - `build_weekly_content(*, stats: WeeklyStats, summary: str) -> dict[str, object]`
  - `WEEKLY_SUMMARY_MAX_LENGTH = 500`、`EMPTY_WEEK_SUMMARY`(Capture が無い週の定型文)、`SUMMARY_FALLBACK_TEXT`(要約が不正なときの定型文)、`normalize_summary(text: str) -> str`(`content.py`。`WEEKLY_CONTENT_VERSION` は Task 4 で足した)
  - `DigestRepository.count_captured_between(user_id, *, start, end) -> int`、`list_done_titles_between(user_id, *, start, end, limit) -> list[str]`
  - `DigestService(digests, captures, summarizer, *, clock=utc_now)`

- [x] **Step 1: Write the failing tests**

共有の fake は `tests/digest_helpers.py` に置く(`FakeDigestRepository`、`FakeCaptureRepository`、`FakeSummarizer`、`make_report` ほか)。Task 4 の `test_digest_service.py` はここから import し、`_service` に `summarizer` を渡す。job のテストの `FakeService` も `summarizer` を受け取る。

`tests/test_digest_weekly.py`(8 件。現在時刻は 2026-11-09 00:00 UTC、行は weekly、`period_start=11-02`、Asia/Tokyo)

```python
async def test_weekly_report_calls_the_summarizer_once_with_titles_only() -> None:
    # captured=5、done=3、題 2 件、未完了 2 件(超過 1)→ WeeklyStats(5, 3, 2, 1) と題だけを渡す
    # list_captures_by_ids は呼ばない。content は {"stats": {camelCase}, "summary": ...}、summary_model は model_name
async def test_weekly_report_reads_the_week_in_the_report_timezone() -> None:
    # count_captured_between、count_done_between、list_done_titles_between の範囲が [11-02 0 時 JST, 11-09 0 時 JST)
async def test_weekly_report_for_an_empty_week_does_not_call_the_summarizer() -> None:
    # captured=0 → 呼び出し 0 回、summary は EMPTY_WEEK_SUMMARY、summary_model は None
async def test_weekly_report_uses_the_fallback_for_an_invalid_summary(summary) -> None: ...   # ""、空白、501 文字。再試行しない
async def test_weekly_report_keeps_a_summary_at_the_maximum_length() -> None: ...           # 500 文字は残す
async def test_weekly_report_reraises_a_provider_error_for_the_job_to_retry() -> None:
    # ReviewProviderError は呼び出し側へ。complete_report も fail_report も呼ばない
async def test_weekly_report_does_nothing_unless_pending() -> None: ...
def test_the_review_input_carries_stats_and_titles_only() -> None: ...   # WeeklyReviewInput の項目は stats と done_titles だけ
```

`tests/test_llm_review_summary.py`(11 件。`test_llm_clarification.py` と同じ形で、`AsyncOpenAI` を monkeypatch する)

```python
async def test_llm_summarizer_returns_the_summary_and_counts_the_call() -> None: ...
async def test_llm_summarizer_returns_an_empty_summary_for_an_invalid_output(raw) -> None:
    # "not-json"、"{}"、summary が数値や null → ""。定型文に直すのは service の normalize_summary
async def test_llm_summarizer_reraises_a_provider_error() -> None: ...
def test_llm_summarizer_reports_the_configured_model() -> None: ...   # model_name は open_ai_model
async def test_sdk_client_maps_transient_errors_to_review_provider_error(error) -> None: ...   # timeout、接続失敗、429、5xx
async def test_sdk_client_does_not_map_non_transient_errors() -> None: ...
async def test_sdk_client_returns_message_content() -> None: ...
async def test_sdk_client_prompt_mentions_json_for_json_mode() -> None: ...
async def test_sdk_client_sends_only_the_stats_and_the_done_titles() -> None: ...   # system と user の 2 通。user に題と件数
```

`tests/test_fake_review_summary.py`(3 件): 呼び出しを数える、集計から決まる固定の短文で `normalize_summary` を通る、`model_name` は `REVIEW_SUMMARY_MODEL_FAKE`

`tests/test_digest_content.py` に追加する(4 件): `build_weekly_content` の camelCase、`normalize_summary` の正しい値と不正な値(空、空白、501 文字)、定型文が 500 文字以内で互いに違う

`tests/test_classifier_factory.py` に追加する(3 件): キーが空か空白なら `FakeReviewSummarizer`、あれば `LlmReviewSummarizer`

`tests/integration/test_digest_repository.py` に追加する(2 件)

```python
async def test_count_captured_between_counts_a_half_open_range_of_the_owner(session) -> None: ...
async def test_list_done_titles_between_returns_the_titles_done_in_the_range_in_order(session) -> None:
    # 完了にした順。範囲の外、未完了、他人は入らない。limit で切る
```

- [ ] **Step 2: Run to verify they fail**

Run: `just test-api` と、`supabase db reset` 後に `cd apps/api && uv run pytest -m integration tests/integration/test_digest_repository.py`
Expected: FAIL(`hibi.ai.review_summary` などの module not found、`DigestService` が `summarizer` を取らない、repository のメソッドが無い)

- [ ] **Step 3: Implement**

**port / adapter**(`ai/`)

- `review_summary.py`: `WeeklyReviewInput`(dataclass)、`ReviewSummarizer`(Protocol。`model_name` と `summarize_week`)、`ReviewProviderError`(`ClarificationProviderError` と同じ形)、`REVIEW_SUMMARY_MODEL_FAKE`
- `fake_review_summary.py`: `FakeReviewSummarizer.summarize_week`: `record_llm_call()` を呼び、集計から決まる固定の短文を返す。network しない。`model_name` は `REVIEW_SUMMARY_MODEL_FAKE`
- `llm_review_summary.py`: `SdkReviewClient.complete_json(*, review)`: `AsyncOpenAI`(`max_retries=0`)で `json_object` モード。system プロンプトに `JSON` の語と `{"summary":"..."}` の形、500 文字以内を書く。user には集計と題だけを入れる。timeout、接続失敗、429、5xx は `ReviewProviderError`。`LlmReviewSummarizer`: `record_llm_call()` を呼び、JSON の `summary` を取り出す。不正なら `""` を返す(定型文に直すのは service。`ai/` が `modules/digests/` を import しないため)。`model_name` は `open_ai_model`
- `classifier_factory.py`: `build_review_summarizer()`: `open_ai_api_key` が空か空白なら fake、あれば `LlmReviewSummarizer`

**domain**(`digests/content.py`)

- `WeeklyStats`(dataclass)と `build_weekly_content(*, stats, summary)`: キーは camelCase
- `normalize_summary(text)`: 空、空白だけ、または 500 文字超なら `SUMMARY_FALLBACK_TEXT` を返す。正しければそのまま返す

**repository**(`digests/repository.py`)

- `count_captured_between(user_id, *, start, end)`: `created_at` が `[start, end)` の Capture の数。状態は問わない
- `list_done_titles_between(user_id, *, start, end, limit)`: `done_at` が `[start, end)` のシナリオの題を、完了にした順に `limit` 件
- 未完了の件数は `count_open` を作らず、`list_open_scenario_candidates` の件数で数える。期限超過の数は `count_deadlines` を再利用する。完了の件数は Task 4 の `count_done_between`

**service**(`digests/service.py`)

- `DigestService.__init__` に `summarizer: ReviewSummarizer` を足す
- `generate_report(report_id)`: weekly なら `_build_weekly_content(report)` を足す。期間は `[local_day_start(period_start), local_day_start(period_start + 7 日))`(行の timezone)。`captured_count` が 0 なら LLM を呼ばず `EMPTY_WEEK_SUMMARY` で、`summary_model` は None。それ以外は `summarizer.summarize_week` を 1 回呼び、`normalize_summary` を通して、`summary_model=summarizer.model_name` で `complete_report`。`ReviewProviderError` は握りつぶさず、job の retry に任せる

**job**

- `run_daily_digest`、`generate_digest_report_job`: `DigestService` に `summarizer=build_review_summarizer()` を渡す
- `generate_digest_report_job._error_code`: `ReviewProviderError` なら `DIGEST_ERROR_REVIEW_PROVIDER`、それ以外は `DIGEST_ERROR_GENERATION_FAILED`

- [ ] **Step 4: Run to verify they pass**

Run: `just test-api`、integration、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src apps/api/tests
git commit -m "feat(digests): summarize the previous week with a fake or LLM adapter"
```

---

### Task 6: 一覧 API と retry API

**Files:**

- Create: `apps/api/src/hibi/modules/digests/{schemas,router,errors}.py`
- Modify: `apps/api/src/hibi/modules/digests/{repository,service,types}.py`、`apps/api/src/hibi/api/main.py`
- Test: `apps/api/tests/test_digest_api.py`(新規)、`apps/api/tests/test_digest_service.py`、`apps/api/tests/integration/test_digest_repository.py`

**Interfaces:**

- Produces:
  - `ListDigestReportsQuery(user_id, kind: str | None, from_date: date | None, limit: int)`(`types.py`)
  - `DigestReportNotFoundError`、`DigestReportNotRetryableError`(409)(`errors.py`)
  - `DigestRepository.list_reports(user_id, *, kind, from_date, limit) -> list[DigestReport]`
  - `DigestRepository.requeue_failed_report(user_id, *, report_id, outbox_id) -> DigestReport | None`
  - `DigestService.list_reports(query) -> list[DigestReport]`、`retry_report(user_id, report_id) -> DigestReport`
  - `GET /api/v1/digest-reports`(`operation_id="listDigestReports"`)、`POST /api/v1/digest-reports/{report_id}/retry`(`operation_id="retryDigestReport"`)

- [ ] **Step 1: Write the failing tests**

`tests/test_digest_api.py`(`test_capture_api.py` と同じく fake service を差し込む)

```python
def test_list_returns_the_data_array_newest_first_with_default_limit() -> None:
    # GET /api/v1/digest-reports → 200、data が配列、service に limit=7
def test_list_passes_kind_and_from_date() -> None: ...      # ?kind=weekly&fromDate=2026-11-01
@pytest.mark.parametrize("params", [{"limit": "0"}, {"limit": "31"}, {"kind": "bogus"}, {"fromDate": "x"}])
def test_list_rejects_invalid_parameters(params) -> None: ...   # 422、errors[0].pointer が該当の項目
def test_list_does_not_return_other_owners() -> None: ...
def test_retry_returns_202_for_a_failed_report() -> None: ...
def test_retry_returns_409_for_a_report_that_is_not_failed() -> None: ...   # type が /digest-report-not-retryable
def test_retry_returns_404_for_a_missing_or_foreign_report() -> None: ...   # type が /digest-report-not-found
def test_digest_endpoints_require_a_token() -> None: ...    # 401
def test_response_content_is_passed_through_as_json() -> None: ...   # content の camelCase のキーがそのまま出る
```

`tests/integration/test_digest_repository.py` に追加する。

```python
@pytest.mark.integration
async def test_list_reports_is_owner_scoped_newest_first_and_filtered(session) -> None: ...
@pytest.mark.integration
async def test_requeue_failed_report_moves_it_to_pending_and_adds_one_outbox_event(session) -> None:
    # failed → pending。outbox が 1 件増える。ready に対しては None。別ユーザーは None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_digest_api.py -v`
Expected: FAIL(module not found)

- [ ] **Step 3: Implement**

**repository / service**

- `DigestRepository.list_reports(user_id, *, kind, from_date, limit)`: 所有者の行を `period_start` の降順で読む。`kind` と `from_date`(`period_start` の下限)は任意
- `DigestRepository.requeue_failed_report(user_id, *, report_id, outbox_id)`: `status = 'failed'` と所有者を条件に `pending` へ戻し、同じ transaction で outbox を足す。対象でなければ None
- `DigestService.list_reports(query)`: そのまま読む
- `DigestService.retry_report(user_id, report_id)`: `requeue_failed_report` が None のとき、行が無い、または別ユーザーなら `DigestReportNotFoundError`、`failed` でなければ `DigestReportNotRetryableError`

**schema / router**(`schemas.py`、`router.py`、`api/main.py`)

- `DigestReportResponse`: `id`、`kind`、`periodStart`、`timezone`、`status`、`content`(辞書)、`contentVersion`、`errorCode`、`generatedAt`。docstring は API の利用者向けで、`content` が `ready` のときだけ入ることを書く
- `list_digest_reports`(`GET /digest-reports`): `limit` は `Annotated[int, Query(ge=1, le=30)] = 7`、`kind` は `daily` か `weekly`、`fromDate` は `date`。`/{report_id}` より前に登録する
- `retry_digest_report`(`POST /digest-reports/{report_id}/retry`): 成功は 202。docstring に、`failed` 以外は 409、他人の行は 404 を書く
- `api/main.py`: `digests_router` を `captures_router` と同じ形で登録する

**contract**

- `just openapi` で、OpenAPI と client を同じ変更で再生成する

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q`、`ruff check`、`ty check apps/api/src`、`just openapi`
Expected: PASS。`listDigestReports` と `retryDigestReport` が `sdk.gen.ts` に出る

- [ ] **Step 5: Commit**

```bash
git add apps/api contracts packages/api-client
git commit -m "feat(digests): list digest reports and retry a failed one over HTTP"
```

---

### Task 7: 止まった処理の回復

**Files:**

- Create: `apps/api/src/hibi/jobs/recover_stalled_work.py`
- Modify: `apps/api/src/hibi/modules/captures/repository.py`、`apps/api/src/hibi/modules/digests/repository.py`、`apps/api/src/hibi/jobs/main.py`
- Test: `apps/api/tests/integration/test_capture_repository.py`、`apps/api/tests/integration/test_digest_repository.py`、`apps/api/tests/test_recover_stalled_work.py`(新規)、`apps/api/tests/test_worker_settings.py`

**Interfaces:**

- Produces:
  - `CaptureRepository.recover_stalled_captures(*, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]) -> int` — 回復した件数
  - `DigestRepository.requeue_stalled_reports(*, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]) -> int`
  - `STALLED_AFTER = timedelta(minutes=10)`
  - `recover_stalled_work(ctx) -> None`(cron)

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_capture_repository.py` に追加する。

```python
@pytest.mark.integration
async def test_update_processing_status_touches_updated_at(session) -> None:
    # pending → processing で updated_at が進む(止まりの判定に使う)

@pytest.mark.integration
async def test_recover_stalled_captures_resets_old_processing_rows_to_the_next_generation(session) -> None:
    # processing で updated_at が 11 分前の行 → pending、世代 +1、outbox が 1 件増える。件数は 1
    # processing で updated_at が 9 分前の行、pending、completed の行は変えない

@pytest.mark.integration
async def test_a_job_of_the_previous_generation_changes_nothing_after_recovery(session) -> None:
    # 回復後、古い世代で update_processing_status を呼ぶと False
```

`tests/integration/test_digest_repository.py` に追加する。

```python
@pytest.mark.integration
async def test_requeue_stalled_reports_adds_an_outbox_event_for_old_pending_rows_only(session) -> None:
    # updated_at が 11 分前の pending は outbox が 1 件増え、9 分前の pending と ready は増えない
    # 同じ行に pending の outbox が既にあるときは、重ねて足さない
```

`tests/test_recover_stalled_work.py`

```python
async def test_recover_stalled_work_calls_both_recoveries_with_the_cutoff_and_logs_counts() -> None:
    # clock 固定。stalled_before = now - 10 分で、両方が呼ばれ、件数が構造化ログに出る
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_recover_stalled_work.py -v` と integration
Expected: FAIL

- [ ] **Step 3: Implement**

**repository**

- `CaptureRepository.update_processing_status`: `updated_at = func.now()` も更新する。止まりの判定は `updated_at` で行うため
- `CaptureRepository.recover_stalled_captures(*, stalled_before, outbox_id_factory)`: `status = 'processing'` かつ `updated_at < stalled_before` の行を、`pending` に戻し、`processing_generation` を 1 増やす。行ごとに、新しい世代の outbox を同じ transaction で足す。件数を返す。`retry_failed_capture` と同じ仕組みをシステムが使う
- `DigestRepository.requeue_stalled_reports(*, stalled_before, outbox_id_factory)`: `status = 'pending'` かつ `updated_at < stalled_before` で、未配送の outbox が無い行に、outbox を足す。件数を返す

**job**

- `recover_stalled_work(ctx)`(`jobs/recover_stalled_work.py`): `stalled_before = now - STALLED_AFTER` で、2 つの回復を呼び、件数を `stuck_capture_recovered` などの構造化ログに出す。本文やユーザーの内容は出さない
- `WorkerSettings`: `cron(recover_stalled_work, minute=set(range(0, 60, 5)), second=0, unique=True, max_tries=1)` を足す

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q`、`supabase db reset` 後に integration、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api apps/api/tests
git commit -m "feat(jobs): recover stalled captures and pending digest reports"
```

---

### Task 8: ダイジェストの画面

**Files:**

- Create: `apps/web/src/lib/api/digest.ts`、`apps/web/src/features/digest/{digest-section.tsx,digest-report-card.tsx,digest-empty-state.tsx,use-digest-polling.ts,actions.ts}`、`apps/web/src/app/captures/digest/page.tsx`
- Modify: `apps/web/src/app/captures/layout.tsx`
- Test: `apps/web/tests/digest-api.test.ts`、`digest-actions.test.ts`、`digest-section.test.tsx`、`digest-report-card.test.tsx`、`captures-digest-page.test.tsx`、`captures-layout.test.tsx`

**Interfaces:**

- Consumes: Task 6 の生成関数 `listDigestReports`、`retryDigestReport`
- Produces:
  - `listDigestReportsFromApi({ kind, limit }?)`: `Promise<ApiResult<DigestReportResponse[]>>`
  - `retryDigestReportFromApi(reportId)`: `Promise<ApiResult<DigestReportResponse>>`
  - `retryDigestReportAction(reportId)`、`getDigestReportsAction()`(polling 用): `Promise<ActionState<...>>`
  - `DigestSection()`(server)、`DigestReportCard({ report })`(client)、`DigestEmptyState()`

- [ ] **Step 1: Write the failing tests**

`digest-api.test.ts`(`capture-api.test.ts` と同じ mock の形。`@hibi/api-client` に `listDigestReports`、`retryDigestReport` を足す)

```ts
it("passes kind and limit and unwraps the data array", async () => { /* query: { kind: "daily", limit: 2 } */ });
it("does not call the API without an authenticated context", async () => { /* … */ });
it("retries a report by id", async () => { /* path: { report_id: "report-1" } */ });
```

`digest-actions.test.ts`

```ts
it("retryDigestReportAction revalidates /captures/digest and returns the report", async () => { /* … */ });
it("rejects an empty id without calling the API", async () => { /* … */ });
it("redirects unauthenticated failures to login", async () => { /* … */ });
```

`digest-section.test.tsx`(`today-section.test.tsx` と同じ形)

```tsx
it("renders the latest daily digest with its items and counts", async () => {
	// 「起こして」「牛乳」、「期限が過ぎた 1 件」「昨日 3 件完了」
});
it("renders the latest weekly review with its summary and stats", async () => { /* … */ });
it("renders the empty state when there are no reports", async () => { /* 「ダイジェストは毎朝 7 時に作ります」 */ });
it("redirects to /login when unauthenticated", async () => { /* … */ });
it("renders the API error message for other failures", async () => { /* 「通信に失敗しました」 */ });
```

`digest-report-card.test.tsx`(jsdom)

```tsx
it("shows 作っています for a pending report", () => { /* … */ });
it("shows the reason and a retry button for a failed report", () => { /* … */ });
it("calls retryDigestReportAction and shows 作っています after success", async () => { /* … */ });
it("shows the failure in an alert and keeps the retry button", async () => { /* … */ });
```

`captures-digest-page.test.tsx`: `requireUser` を 1 回呼び、`DigestSection` の出力を出す。`captures-layout.test.tsx`: ヘッダーに `/captures/digest`(文言は「ダイジェスト」)を足したリンクを確かめる。

- [ ] **Step 2: Run to verify they fail**

Run: `corepack pnpm --filter web exec vitest run`
Expected: FAIL(module not found)

- [ ] **Step 3: Implement**

**API wrapper**(`lib/api/digest.ts`)

- `listDigestReportsFromApi({ kind, limit }?)`: 生成関数 `listDigestReports` を呼び、`DigestReportResponse[]` を返す。`getCaptureFromApi` と同じ形
- `retryDigestReportFromApi(reportId)`: 生成関数 `retryDigestReport` を呼ぶ
- どれも日本語の JSDoc を付ける

**action**(`features/digest/actions.ts`)

- `retryDigestReportAction(reportId)`: 空の id はエラー。成功したら `/captures/digest` を revalidate。404 は画面全体を 404 にせず、エラーとして返す。未認証は `/login`
- `getDigestReportsAction()`: polling 用に、最新の一覧を返す

**component**(`features/digest/`)

- `DigestSection()`(server): `daily` と `weekly` の最新を、1 回の `listDigestReportsFromApi` で読み、種類ごとに最初の行を選ぶ。未認証は `/login`、失敗は `ApiErrorMessage`、0 件は `DigestEmptyState`
- `DigestReportCard({ report })`(client): `status` で出し分ける。`ready` は、daily なら items(title、期限は `formatJstDueLabel`)と、期限超過、今日が期限、昨日の完了の件数。weekly なら集計と要約。`pending` は「作っています」。`failed` は理由の一言と「もう一度作る」。ボタンは `useTransition` で `retryDigestReportAction` を呼ぶ。items の行は、押すと詳細へ行く
- `DigestEmptyState()`: 「ダイジェストは毎朝 7 時に作ります」。糸の最初の節の見た目
- `useDigestPolling`(`use-digest-polling.ts`): `pending` の行があるときだけ、3 秒おきに `getDigestReportsAction` を呼ぶ。`useCapturePolling` と同じ流儀で、失敗したら止める

**page / layout**

- `DigestPage()`(`app/captures/digest/page.tsx`): `await requireUser()` のあと、見出し「ダイジェスト」と、`Suspense` で包んだ `DigestSection`
- `CapturesLayout`: ヘッダーの `<nav>` に「ダイジェスト」(`/captures/digest`)を足す

新しい export には、日本語の JSDoc を付ける(CLAUDE.md の方針)。

- [ ] **Step 4: Run the web gate**

Run: `corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`
Expected: すべて PASS。`git checkout apps/web/next-env.d.ts`

- [ ] **Step 5: Manual check**(`docs/architecture/28-week10-digest-and-review.md` の手動確認)

`just dev-api`、`just dev-worker`、`just dev-web` を起動する。worker は 15 分ごとの cron を持つので、確認のときは、`run_daily_digest` を一度手で呼ぶ(`uv run --project apps/api python -c ...` で `DigestService.schedule_due_reports` を実行する)。

1. 記録のあるユーザーで、7 時を過ぎたあとに実行すると、daily が 1 件できる。もう一度実行しても増えない
2. `/captures/digest` に、今日やることの上位と、件数が出る
3. 月曜に、先週の weekly ができる(確認のため、`now` を月曜にして実行してよい)
4. LLM のキーを空にして fake の要約が出る。キーを設定すると、実際の要約が出る
5. `failed` の行(job を失敗させて作る)に「もう一度作る」が出て、押すと「作っています」になり、再び `ready` になる
6. `processing` のまま止まった Capture(DB で `updated_at` を 11 分前にする)が、5 分以内に、`pending` に戻り、完了する

- [ ] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat(web): show the daily digest and the weekly review"
```

---

### Task 9: 全ゲート

- [ ] **Step 1: Run every gate**

Run: `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`、`ruff check`、`ty check apps/api/src`、`uv run --project apps/api pytest apps/api/tests`、`supabase db reset` 後に `-m integration`、`corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`、`just openapi` で差分が出ない
Expected: すべて GREEN(`format:check` は対象外。`test_auth_supabase_local.py` の 2 件は、テスト用ユーザーの認証情報が合わないことによる既存の失敗)

- [ ] **Step 2: Commit the plan and spec**

```bash
git add docs/architecture/28-week10-digest-and-review.md docs/architecture/11-implementation-schedule.md docs/superpowers/plans/2026-11-15-week10-digest-and-review.md
git commit -m "docs: add the week 10 digest and review spec and plan"
```

---

## 判断メモ

- **outbox を使い回す理由:** 再実行(retry)は、状態の更新と job の投入を同じ transaction で行う必要があり、Week 4 の outbox がそれを担う。作り直すと、2 つの配送の仕組みが並ぶ。代わりに、`aggregate_id` の FK を外す必要が出る(Task 3)。capture の削除では、repository が outbox を明示的に消す。
- **cron を 15 分ごとにする理由:** ユーザーごとの予定表を持たずに、timezone と夏時間を、`daily_period_start` の判定に閉じ込められる。配信は最大 15 分遅れるが、朝 7 時の目安としては足りる。分を細かくすると、ユーザー数に比例して、毎回の走査が増える。
- `ON CONFLICT DO NOTHING` **の claim を正本にする理由:** arq の `unique` や `_job_id` は、Redis の状態に依存し、再起動やキーの期限で崩れる。DB の unique なら、worker が何台でも、行は 1 件になる。
- `pending` **の重複実行を許す理由:** 回復の再投入と、元の job が重なると、同じ `pending` の行を 2 つの job が処理しうる。`complete_report` は `pending` を条件にした UPDATE なので、書き込みは 1 回だけになる。weekly の LLM は、まれに 2 回呼ばれうるが、重複を避ける錠(列の追加)は、頻度に見合わないので入れない。
- `updated_at` **を** `update_processing_status` **で更新する理由:** 止まった `processing` の判定を、`updated_at` で行うため。今は `status` だけを更新しているので、`created_at` 近くの古い値のまま残る。
- **要確認(方針文書で決めた前提):** 配信時刻の固定(7 時)、週の起点(月曜)、対象ユーザー(直近 14 日)、LLM への入力(集計と title だけ)、通知の見送り。
